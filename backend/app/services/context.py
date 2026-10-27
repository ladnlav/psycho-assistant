"""Контекст пациента, над которым вычисляются правила из kb/rules (см. kb/README.md)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kb import KnowledgeBase, Scale
from app.models import (AdverseEvent, DiaryEntry, MedicationIntake, Message, Prescription, ScaleResponse, User,
                        utcnow)
from app.services.rules import LAST_REPORT, RECORD


def _scale_context(db: Session, patient_id: uuid.UUID, scale: Scale) -> dict | None:
    rows = db.scalars(
        select(ScaleResponse)
        .where(ScaleResponse.patient_id == patient_id, ScaleResponse.scale_id == scale.id)
        .order_by(ScaleResponse.created_at)
    ).all()
    if not rows:
        return None
    latest, first = rows[-1], rows[0]
    prev = rows[-2] if len(rows) > 1 else None
    return {
        **latest.answers,
        **{sub.id: sum(latest.answers[i] for i in sub.items) for sub in scale.subscales},
        "total": latest.total,
        "severity": latest.severity,
        "n": len(rows),
        "mcid": scale.mcid,
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


def _help_context(db: Session, patient_id: uuid.UUID, since: datetime) -> dict:
    """Просьбы о срочной помощи с причиной за сутки (кнопка «Нужна срочная помощь»).
    _record — последняя просьба: новая просьба — новые данные для алерта, повтор старой — нет."""
    ids = db.scalars(select(Message.id).where(
        Message.patient_id == patient_id, Message.sender_id == patient_id, Message.kind == "help",
        Message.created_at >= since).order_by(Message.created_at)).all()
    return {"requests_24h": len(ids), RECORD: str(ids[-1]) if ids else None}


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


def last_report(db: Session, patient_id: uuid.UUID) -> date | None:
    """День последней записи пациента: дневник, шкала, отметка приёма, нежелательное явление или сообщение врачу.
    Записей ещё нет — день регистрации: «не начал пользоваться» — тоже повод напомнить."""
    times = [
        db.scalar(select(func.max(DiaryEntry.created_at)).where(DiaryEntry.patient_id == patient_id)),
        db.scalar(select(func.max(ScaleResponse.created_at)).where(
            ScaleResponse.patient_id == patient_id, ScaleResponse.submitted_by == patient_id)),
        db.scalar(select(func.max(MedicationIntake.created_at)).where(MedicationIntake.patient_id == patient_id)),
        db.scalar(select(func.max(AdverseEvent.created_at)).where(
            AdverseEvent.patient_id == patient_id, AdverseEvent.reported_by == patient_id)),
        db.scalar(select(func.max(Message.created_at)).where(
            Message.patient_id == patient_id, Message.sender_id == patient_id)),
    ]
    last = max((t for t in times if t is not None), default=None)
    if last is None:
        last = db.scalar(select(User.created_at).where(User.id == patient_id))
    return last.date() if last else None


def build_context(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID,
                  now: datetime | None = None) -> dict[str, Any]:
    """`now` — на какой момент считать контекст; по умолчанию сейчас (другой — для демо-сценариев)."""
    now = now or utcnow()
    week_ago = now - timedelta(days=7)
    ctx: dict[str, Any] = {
        sid: _scale_context(db, patient_id, scale) for sid, scale in kb.scales.items()
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
    ctx["help"] = _help_context(db, patient_id, now - timedelta(days=1))
    ctx["pdc_7d"] = pdc_7d(db, patient_id, now.date())
    last = last_report(db, patient_id)
    ctx["days_since_report"] = (now.date() - last).days if last else None
    ctx[LAST_REPORT] = last.isoformat() if last else None
    return ctx
