"""Предложения направить к специалисту: у пациента не больше одного открытого предложения к каждому.

К психиатру направление предлагают несколько правил (gad7_severe — «желательно», phq9_severe,
phq9_suicidal_ideation, free_text_risk — «обязательно»). Новое предложение к специалисту не создаётся, если
пациент к нему уже направлен или предложение к нему уже ждёт решения врача. Исключение: открыто только
«желательно», а правило предлагает «обязательно», — тогда «желательно» закрывается. Когда врач направляет
пациента, открытые предложения к тому же специалисту закрываются со статусом superseded.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kb import Proposal, Rule
from app.models import Recommendation, Referral, utcnow
from app.services.audit import audit

# «Направить к …» — дательный падеж специальности из kb/rules (propose.to)
REFERRAL_TO_RU = {"psychiatrist": "психиатру", "psychotherapist": "психотерапевту", "neurologist": "неврологу"}

# Почему предложение закрыто без решения врача (Recommendation.decision_note при status="superseded")
ALREADY_REFERRED = "уже направлен"
REPLACED_BY_MANDATORY = "предложено «обязательно»"


def open_proposals(db: Session, patient_id: uuid.UUID, to: str) -> list[Recommendation]:
    pending = db.scalars(
        select(Recommendation).where(
            Recommendation.patient_id == patient_id, Recommendation.kind == "referral",
            Recommendation.status == "proposed",
        )
    )
    return [r for r in pending if r.payload.get("to") == to]


def is_referred(db: Session, patient_id: uuid.UUID, to: str) -> bool:
    """Направление не отменяется, поэтому любое направление к специалисту действует."""
    return db.scalar(
        select(Referral.id).where(Referral.patient_id == patient_id, Referral.to_specialty == to).limit(1)
    ) is not None


def supersede(db: Session, actor_id: uuid.UUID | None, recs: list[Recommendation], reason: str) -> None:
    """Закрывает открытые предложения без клинического действия; actor_id None — закрыла система."""
    for rec in recs:
        rec.status, rec.decided_by, rec.decided_at = "superseded", actor_id, utcnow()
        rec.decision_note = reason
        audit(db, actor_id, "recommendation.superseded", "recommendation", rec.id,
              {"to": rec.payload.get("to"), "reason": reason})


def close_after_referral(db: Session, doctor_id: uuid.UUID, patient_id: uuid.UUID, to: str) -> None:
    """Врач направил пациента к `to`: остальные предложения к нему больше не ждут решения."""
    supersede(db, doctor_id, open_proposals(db, patient_id, to), ALREADY_REFERRED)


def propose_referral(db: Session, patient_id: uuid.UUID, rule: Rule, p: Proposal) -> str | None:
    """Создаёт предложение правила, если оно нужно. Иначе возвращает, почему его нет: referred | proposed."""
    if is_referred(db, patient_id, p.to):
        return "referred"
    pending = open_proposals(db, patient_id, p.to)
    if pending and (p.level != "mandatory" or any(r.payload.get("level") == "mandatory" for r in pending)):
        return "proposed"  # прежнее предложение ещё ждёт решения врача
    supersede(db, None, pending, REPLACED_BY_MANDATORY)  # открыты только «желательно»
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
    db.flush()  # autoflush выключен, а следующее правило в этом же вызове должно увидеть предложение
    return None
