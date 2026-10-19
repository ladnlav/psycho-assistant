import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.kb import KnowledgeBase
from app.models import ScaleResponse
from app.schemas import SafetyScreen, ScaleResult, ScaleSubmitResult
from app.services.alerts import RulesOutcome, apply_rules
from app.services.audit import audit
from app.services.scoring import ScoringError, score


def safety_screen(kb: KnowledgeBase) -> SafetyScreen:
    return SafetyScreen(
        message_ru=kb.safety.message_ru,
        contacts=[c.model_dump() for c in kb.safety.contacts],
    )


def record_scale(
    db: Session, kb: KnowledgeBase, patient_id: uuid.UUID, actor_id: uuid.UUID, scale_id: str,
    answers: dict[str, int], rater: str,
) -> tuple[ScaleSubmitResult, RulesOutcome]:
    scale = kb.scales.get(scale_id)
    if scale is None:
        raise HTTPException(404, "Шкала не найдена")
    if scale.rater != rater:
        raise HTTPException(403, "Эту шкалу заполняет " + ("пациент" if scale.rater == "patient" else "врач"))
    try:
        result = score(scale, answers)
    except ScoringError as e:
        raise HTTPException(422, str(e)) from e

    row = ScaleResponse(patient_id=patient_id, scale_id=scale_id, answers=answers, total=result.total,
                        severity=result.severity, submitted_by=actor_id)
    db.add(row)
    db.flush()
    audit(db, actor_id, "scale.submitted", "scale_response", row.id, {"scale": scale_id, "total": result.total})
    outcome = apply_rules(db, kb, patient_id, trigger=f"scale:{scale_id}")
    db.commit()
    return (
        ScaleSubmitResult(
            result=ScaleResult.model_validate(row),
            severity_label_ru=result.severity_label_ru,
            safety=safety_screen(kb) if outcome.show_safety_screen else None,
        ),
        outcome,
    )
