"""Проверка назначения по инструкции из kb/drugs: противопоказания, «с осторожностью», взаимодействия.

Система ничего не запрещает: она показывает врачу пункты инструкции, а решение и обоснование остаются за ним.
Пункт без `when` врач проверяет сам; пункт, для которого в карточке нет данных, тоже уходит врачу.
"""

import ast
import uuid
from dataclasses import dataclass, field
from datetime import date

from simpleeval import SimpleEval
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kb import Drug, DrugCheck, KnowledgeBase
from app.models import Diagnosis, PatientProfile, Prescription, utcnow
from app.schemas import DrugWarning, PrescriptionCheck, PrescriptionIn

SECTION_RU = {
    "contraindication": "Противопоказания",
    "caution": "С осторожностью",
    "interaction": "Взаимодействие с другими лекарственными средствами",
}
MISSING_RU = {"age": "нет даты рождения", "sex": "не указан пол"}


@dataclass
class PatientFacts:
    age: int | None = None
    sex: str | None = None
    diagnoses: list[str] = field(default_factory=list)   # коды МКБ-10
    medications: list[str] = field(default_factory=list)  # id, МНН и названия активных назначений, в нижнем регистре


def _age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def patient_facts(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID) -> PatientFacts:
    profile = db.get(PatientProfile, patient_id)
    meds = []
    for rx in db.scalars(select(Prescription).where(Prescription.patient_id == patient_id, Prescription.active.is_(True))):
        meds += [rx.drug_name.lower()]
        if rx.drug_id:
            meds += [rx.drug_id.lower()] + ([kb.drugs[rx.drug_id].inn.lower()] if rx.drug_id in kb.drugs else [])
    return PatientFacts(
        age=_age(profile.birth_date if profile else None, utcnow().date()),
        sex=profile.sex if profile else None,
        diagnoses=[d.icd10 for d in db.scalars(select(Diagnosis).where(Diagnosis.patient_id == patient_id))],
        medications=meds,
    )


def _norm_code(code: str) -> str:
    return code.upper().replace(" ", "")


def _evaluator(facts: PatientFacts) -> SimpleEval:
    codes = [_norm_code(c) for c in facts.diagnoses]
    return SimpleEval(
        names={"age": facts.age, "sex": facts.sex},
        functions={
            "dx": lambda *prefixes: any(c.startswith(_norm_code(p)) for c in codes for p in prefixes),
            "taking": lambda *names: any(n.lower() in m for m in facts.medications for n in names),
        },
    )


def _missing(expr: str, facts: PatientFacts) -> list[str]:
    used = {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)}
    return [MISSING_RU[n] for n in ("age", "sex") if n in used and getattr(facts, n) is None]


def _should_ask(item: DrugCheck, facts: PatientFacts) -> bool:
    if isinstance(item.ask, bool):
        return item.ask
    if _missing(item.ask, facts):
        return True  # не знаем, относится ли пункт к пациенту, — лучше спросить
    try:
        return _evaluator(facts).eval(item.ask) is True
    except Exception:
        return True


def _evaluate(item: DrugCheck, facts: PatientFacts) -> tuple[str, str | None] | None:
    """(status, detail) для пункта, который надо показать врачу; None — пункт к пациенту не относится."""
    if item.when is None:
        return "manual", None
    if missing := _missing(item.when, facts):
        return "unchecked", ", ".join(missing)
    try:
        fired = _evaluator(facts).eval(item.when) is True
    except Exception:  # выражение не вычислилось — пусть врач проверит сам
        return "unchecked", "условие не удалось проверить"
    if fired:
        return "fired", None
    return ("manual", None) if _should_ask(item, facts) else None


def check(drug: Drug, facts: PatientFacts, sources: list[str] | None = None) -> list[DrugWarning]:
    """`sources` — на что ссылается каждый пункт; по умолчанию все источники препарата."""
    sources = drug.sources if sources is None else sources
    out = []
    groups = (("contraindication", drug.contraindications), ("caution", drug.caution),
              ("interaction", drug.interactions))
    for kind, items in groups:
        for item in items:
            result = _evaluate(item, facts)
            if result is None:
                continue
            status, detail = result
            hard = kind == "contraindication" or item.severity == "contraindicated"
            out.append(DrugWarning(
                id=item.id, kind=kind, status=status, text_ru=item.text_ru, section_ru=SECTION_RU[kind],
                detail_ru=detail, requires_reason=hard and status == "fired", sources=sources,
            ))
    order = {"fired": 0, "unchecked": 1, "manual": 2}
    return sorted(out, key=lambda w: order[w.status])  # sorted() устойчива: внутри статуса порядок инструкции


def check_prescription(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID, body: PrescriptionIn) -> PrescriptionCheck:
    if body.drug_id is None:
        return PrescriptionCheck(checked=False, notice_ru="Препарата нет в базе знаний — инструкция не проверялась")
    drug = kb.drugs[body.drug_id]
    if not drug.has_checks:
        return PrescriptionCheck(
            checked=False, notice_ru="Данные инструкции из ГРЛС ещё не внесены — противопоказания не проверены")
    # Пункт цитирует инструкцию, а не, например, презентацию производителя.
    instruction = [s for s in drug.sources if s in kb.sources and kb.sources[s].type == "instruction"]
    return PrescriptionCheck(checked=True, warnings=check(drug, patient_facts(db, kb, patient_id), instruction))
