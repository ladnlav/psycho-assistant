"""Алертинг: правила → алерты и предложения врачу → доставка врачу по WebSocket.

Правила проверяются при каждой записи пациента и по расписанию (rules_schedule): «нет записей N дней»
наступает как раз тогда, когда пациент ничего не пишет.

Время доставки — техметрика кейса: у каждого алерта есть created_at → delivered_at → acknowledged_at.
Дальше: внешний канал уведомлений (мессенджер или почта) и эскалация, если алерт долго не подтверждён.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.kb import KnowledgeBase, Proposal, Rule
from app.models import Alert, DoctorPatientLink, utcnow
from app.services.audit import audit
from app.services.context import build_context
from app.services.referrals import propose_referral
from app.services.rules import TIME_ANCHORS, evaluate, evidence, referenced_names

log = logging.getLogger(__name__)


@dataclass
class RulesOutcome:
    new_alert_ids: list[uuid.UUID] = field(default_factory=list)
    updated_alert_ids: list[uuid.UUID] = field(default_factory=list)  # открытые алерты, в которые пришли новые данные
    show_safety_screen: bool = False

    @property
    def push_ids(self) -> list[uuid.UUID]:
        """Что отправить врачу: новые алерты и обновлённые открытые."""
        return self.new_alert_ids + self.updated_alert_ids


def lead_doctor_id(db: Session, patient_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(DoctorPatientLink.doctor_id).where(
            DoctorPatientLink.patient_id == patient_id, DoctorPatientLink.active.is_(True)
        )
    )


def apply_rules(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID, trigger: str,
                rules: Iterable[Rule] | None = None, now: datetime | None = None) -> RulesOutcome:
    """Вычисляет правила по свежим данным пациента и реагирует только на новые данные.

    Правило смотрит на состояние, поэтому срабатывает при каждой записи пациента. У алерта хранится отпечаток
    данных (rules.evidence): с тем же отпечатком нет ни нового алерта, ни экрана безопасности. Пока алерт
    не подтверждён, новые данные дописываются в него, а не порождают второй, и алерт отправляется врачу заново
    (outcome.updated_alert_ids). Предложение направить к специалисту появляется только с новым алертом, если
    пациент к этому специалисту не направлен и предложение к нему ещё не ждёт решения (services/referrals).
    Коммит — на вызывающей стороне.
    """
    outcome = RulesOutcome()
    proposals: list[tuple[Alert, Rule, Proposal]] = []
    doctor_id = lead_doctor_id(db, patient_id)
    context = build_context(db, kb, patient_id, now)
    for rule in evaluate(kb.rules.values() if rules is None else rules, context):
        ev = evidence(rule, context)
        last = db.scalar(
            select(Alert).where(Alert.patient_id == patient_id, Alert.rule_id == rule.id)
            .order_by(Alert.created_at.desc()).limit(1)
        )
        if last is not None and (last.details or {}).get("evidence") == ev:
            continue  # те же данные, о которых врач уже знает
        if "patient_safety_screen" in rule.actions:
            outcome.show_safety_screen = True
        if doctor_id is None or "notify_doctor" not in rule.actions:
            continue
        if last is not None and last.acknowledged_at is None:
            # Второго алерта не создаём, но врач должен увидеть новые данные: алерт уходит ему заново.
            details = last.details or {}
            last.details = {**details, "evidence": ev, "updated_at": utcnow().isoformat(),
                            "updates": details.get("updates", 0) + 1}
            outcome.updated_alert_ids.append(last.id)
            audit(db, None, "alert.updated", "alert", last.id, {"rule": rule.id, "trigger": trigger})
            continue
        alert = Alert(
            patient_id=patient_id,
            doctor_id=doctor_id,
            rule_id=rule.id,
            level=rule.level,
            title=rule.title_ru,
            details={"trigger": trigger, "rule_status": rule.status, "evidence": ev},
            sources=rule.sources,
        )
        db.add(alert)
        db.flush()
        outcome.new_alert_ids.append(alert.id)
        proposals += [(alert, rule, p) for p in rule.propose]
        audit(db, None, "alert.created", "alert", alert.id, {"rule": rule.id, "level": rule.level})
    # Предложения — после всех алертов и сначала «обязательно»: «желательно» к тому же специалисту
    # из этого же вызова тогда не нужно. Алерт без предложения хранит, почему его нет.
    for alert, rule, p in sorted(proposals, key=lambda x: x[2].level != "mandatory"):
        if (skipped := propose_referral(db, patient_id, rule, p)) is not None:
            note = {"to": p.to, "reason": skipped}
            alert.details = {**alert.details, "no_proposal": [*alert.details.get("no_proposal", []), note]}
    return outcome


def patient_reminders(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID) -> list[tuple[str, str]]:
    """Напоминания пациенту от сработавших правил с remind_patient: (id правила, текст). Пока правило
    срабатывает, напоминание видно в приложении; новая запись пациента снимает его сама."""
    rules = [r for r in kb.rules.values() if "remind_patient" in r.actions]
    return [(r.id, r.remind_ru) for r in evaluate(rules, build_context(db, kb, patient_id))]


def timed_rules(kb: KnowledgeBase) -> list[Rule]:
    """Правила, которые срабатывают без новой записи пациента, — от времени («нет записей N дней»)."""
    return [r for r in kb.rules.values() if any(name in TIME_ANCHORS for name, _ in referenced_names(r.when))]


def check_all_patients(db: Session, kb: KnowledgeBase) -> list[uuid.UUID]:
    """Правила от времени по всем пациентам с лечащим врачом. Остальные правила по расписанию не проверяются:
    у молчащего пациента нет отметок приёма, и «низкая приверженность» обгоняла бы порог «нет записей».
    Отпечаток данных не даёт повторить уже известный алерт. Возвращает, что отправить врачам."""
    rules = timed_rules(kb)
    push: list[uuid.UUID] = []
    for patient_id in db.scalars(
        select(DoctorPatientLink.patient_id).where(DoctorPatientLink.active.is_(True)).distinct()
    ).all():
        push += apply_rules(db, kb, patient_id, trigger="schedule", rules=rules).push_ids
    db.commit()
    return push


async def rules_schedule(kb: KnowledgeBase, minutes: int) -> None:
    """Проверка правил по расписанию: сразу при старте, затем раз в `minutes` минут (RULES_CHECK_MINUTES)."""
    def check() -> list[uuid.UUID]:
        with SessionLocal() as db:
            return check_all_patients(db, kb)

    while True:
        try:
            ids = await asyncio.to_thread(check)
            log.info("rules schedule: %d alerts to push", len(ids))
            await hub.push(ids)
        except Exception:
            log.exception("rules schedule failed")
        await asyncio.sleep(minutes * 60)


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
        "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
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
                    created = alert.created_at.replace(tzinfo=alert.created_at.tzinfo or timezone.utc)  # SQLite: без пояса
                    log.info("alert %s delivered in %s", alert.id, alert.delivered_at - created)
            db.commit()


hub = AlertHub()
