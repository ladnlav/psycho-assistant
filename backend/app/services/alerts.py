"""Алертинг: правила → алерты и предложения врачу → доставка врачу по WebSocket.

Время доставки — техметрика кейса: у каждого алерта есть created_at → delivered_at → acknowledged_at.
TODO (если успеем): внешний канал (Telegram/почта); эскалация при отсутствии подтверждения — после хакатона.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.kb import KnowledgeBase
from app.models import Alert, DoctorPatientLink, Recommendation, utcnow
from app.services.audit import audit
from app.services.context import build_context
from app.services.rules import evaluate

log = logging.getLogger(__name__)

# «Направить к …» — дательный падеж специальности из kb/rules (propose.to)
REFERRAL_TO_RU = {"psychiatrist": "психиатру", "psychotherapist": "психотерапевту", "neurologist": "неврологу"}


@dataclass
class RulesOutcome:
    new_alert_ids: list[uuid.UUID] = field(default_factory=list)
    show_safety_screen: bool = False


def lead_doctor_id(db: Session, patient_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(DoctorPatientLink.doctor_id).where(
            DoctorPatientLink.patient_id == patient_id, DoctorPatientLink.active.is_(True)
        )
    )


def apply_rules(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID, trigger: str) -> RulesOutcome:
    """Вычисляет правила по свежим данным пациента. Повторный алерт по тому же правилу не создаётся,
    пока врач не подтвердил предыдущий. Коммит — на вызывающей стороне."""
    outcome = RulesOutcome()
    doctor_id = lead_doctor_id(db, patient_id)
    context = build_context(db, kb, patient_id)
    for rule in evaluate(kb.rules.values(), context):
        if "patient_safety_screen" in rule.actions:
            outcome.show_safety_screen = True
        if doctor_id is None or "notify_doctor" not in rule.actions:
            continue
        open_alert = db.scalar(
            select(Alert.id).where(
                Alert.patient_id == patient_id, Alert.rule_id == rule.id, Alert.acknowledged_at.is_(None)
            )
        )
        if open_alert:
            continue
        alert = Alert(
            patient_id=patient_id,
            doctor_id=doctor_id,
            rule_id=rule.id,
            level=rule.level,
            title=rule.title_ru,
            details={"trigger": trigger, "rule_status": rule.status},
            sources=rule.sources,
        )
        db.add(alert)
        db.flush()
        outcome.new_alert_ids.append(alert.id)
        for p in rule.propose:
            db.add(
                Recommendation(
                    patient_id=patient_id,
                    kind=p.kind,
                    title=f"Направить к {REFERRAL_TO_RU.get(p.to, p.to)}",
                    payload={"to": p.to, "level": p.level, "reason_ru": p.reason_ru},
                    sources=rule.sources,
                    rule_id=rule.id,
                )
            )
        audit(db, None, "alert.created", "alert", alert.id, {"rule": rule.id, "level": rule.level})
    return outcome


def alert_to_dict(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "patient_id": str(alert.patient_id),
        "rule_id": alert.rule_id,
        "level": alert.level,
        "title": alert.title,
        "sources": alert.sources,
        "created_at": alert.created_at.isoformat(),
        "delivered_at": alert.delivered_at.isoformat() if alert.delivered_at else None,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }


class AlertHub:
    """Активные WebSocket-подключения врачей (в памяти одного процесса)."""

    def __init__(self) -> None:
        self._sockets: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, doctor_id: uuid.UUID, ws: WebSocket) -> None:
        self._sockets[doctor_id].add(ws)
        with SessionLocal() as db:  # при подключении досылаем недоставленные алерты
            pending = db.scalars(
                select(Alert.id).where(Alert.doctor_id == doctor_id, Alert.delivered_at.is_(None))
            ).all()
        await self.push(list(pending))

    def disconnect(self, doctor_id: uuid.UUID, ws: WebSocket) -> None:
        self._sockets[doctor_id].discard(ws)

    async def push(self, alert_ids: list[uuid.UUID]) -> None:
        if not alert_ids:
            return
        with SessionLocal() as db:
            for alert in db.scalars(select(Alert).where(Alert.id.in_(alert_ids))):
                sent = False
                for ws in list(self._sockets.get(alert.doctor_id, ())):
                    try:
                        await ws.send_json({"type": "alert", "alert": alert_to_dict(alert)})
                        sent = True
                    except Exception:
                        self.disconnect(alert.doctor_id, ws)
                if sent and alert.delivered_at is None:
                    alert.delivered_at = utcnow()
                    log.info("alert %s delivered in %s", alert.id, alert.delivered_at - alert.created_at)
            db.commit()


hub = AlertHub()
