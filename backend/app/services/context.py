"""Контекст пациента, над которым вычисляются правила из kb/rules (см. kb/README.md)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kb import KnowledgeBase
from app.models import (AdverseEvent, DiaryEntry, MedicationIntake, Message, Prescription, ScaleResponse,
                        utcnow)
from app.services.rules import RECORD


def _scale_context(db: Session, patient_id: uuid.UUID, scale_id: str, mcid: float | None) -> dict | None:
    rows = db.scalars(
        select(ScaleResponse)
        .where(ScaleResponse.patient_id == patient_id, ScaleResponse.scale_id == scale_id)
        .order_by(ScaleResponse.created_at)
    ).all()
    if not rows:
        return None
    latest, first = rows[-1], rows[0]
    prev = rows[-2] if len(rows) > 1 else None
    return {
        **latest.answers,
        "total": latest.total,
        "severity": latest.severity,
        "n": len(rows),
        "mcid": mcid,
        "delta_prev": latest.total - prev.total if prev else 0,
        "delta_baseline": latest.total - first.total,
        RECORD: str(latest.id),
    }


def _text_context(db: Session, patient_id: uuid.UUID, since: datetime) -> dict:
    """Свободный текст пациента за 7 дней — сообщения врачу и описания НЯ — по разметке триажа (services/triage).

    _record — последний текст с признаками риска: повтор старого не создаёт нового алерта, новый текст — создаёт.
    """
    texts = [
        *db.execute(select(Message.id, Message.triage, Message.created_at).where(
            Message.patient_id == patient_id, Message.sender_id == patient_id, Message.created_at >= since)),
        *db.execute(select(AdverseEvent.id, AdverseEvent.triage, AdverseEvent.created_at).where(
            AdverseEvent.patient_id == patient_id, AdverseEvent.created_at >= since)),
    ]
    critical = sorted((t for t in texts if (t.triage or {}).get("level") == "critical"), key=lambda t: t.created_at)
    return {"critical": bool(critical), RECORD: str(critical[-1].id) if critical else None}


MIN_PDC_DAYS = 3  # меньше трёх дней наблюдения — приверженность не оцениваем


def pdc_7d(db: Session, patient_id: uuid.UUID, today: date) -> float | None:
    """Доля дней с приёмом за последние 7 завершённых дней (сегодня не считается — день ещё идёт),
    только за дни, когда назначение уже действовало."""
    start = db.scalar(
        select(func.min(Prescription.start_date)).where(
            Prescription.patient_id == patient_id, Prescription.active.is_(True)
        )
    )
    if start is None:
        return None
    window_end = today - timedelta(days=1)
    window_start = max(start, today - timedelta(days=7))
    days = (window_end - window_start).days + 1
    if days < MIN_PDC_DAYS:
        return None
    taken = db.scalar(
        select(func.count(func.distinct(MedicationIntake.day))).where(
            MedicationIntake.patient_id == patient_id,
            MedicationIntake.status == "taken",
            MedicationIntake.day >= window_start,
            MedicationIntake.day <= window_end,
        )
    )
    return taken / days


def build_context(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID) -> dict[str, Any]:
    now = utcnow()
    week_ago = now - timedelta(days=7)
    ctx: dict[str, Any] = {
        sid: _scale_context(db, patient_id, sid, scale.mcid) for sid, scale in kb.scales.items()
    }
    ctx["ae"] = {
        "serious_7d": db.scalar(
            select(func.count()).where(
                AdverseEvent.patient_id == patient_id,
                AdverseEvent.serious.is_(True),
                AdverseEvent.created_at >= week_ago,
            )
        ),
        "any_7d": db.scalar(
            select(func.count()).where(AdverseEvent.patient_id == patient_id, AdverseEvent.created_at >= week_ago)
        ),
    }
    ctx["text"] = _text_context(db, patient_id, week_ago)
    ctx["pdc_7d"] = pdc_7d(db, patient_id, now.date())
    last_report = db.scalar(select(func.max(DiaryEntry.day)).where(DiaryEntry.patient_id == patient_id))
    ctx["days_since_report"] = (now.date() - last_report).days if last_report else None
    return ctx
