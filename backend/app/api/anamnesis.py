"""Анамнез, источники диагнозов и лабораторные исследования.

Врач видит и меняет раздел только у своих пациентов, пациент читает «Мою историю» только о себе. Каждое изменение
пишется в журнал аудита: кто, что и на что поменял.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.kb import KnowledgeBase, get_kb
from app.models import Anamnesis, Diagnosis, LabResult, User, utcnow
from app.schemas import (AnamnesisIn, AnamnesisOut, DiagnosisIn, DiagnosisOut, DiagnosisSourceIn, LabResultIn,
                         LabResultOut, PatientHistory)
from app.security import ensure_own_patient, require_doctor, require_patient
from app.services.anamnesis import anamnesis_out, diagnosis_out, patient_history
from app.services.audit import audit

doctor_router = APIRouter(prefix="/api/doctor", tags=["doctor"])
patient_router = APIRouter(prefix="/api/patient", tags=["patient"])

ANAMNESIS_FIELDS = ("complaints", "history", "notes")


@doctor_router.get("/patients/{patient_id}/history", response_model=PatientHistory)
def history(patient_id: uuid.UUID, doctor: User = Depends(require_doctor), db: Session = Depends(get_db),
            kb: KnowledgeBase = Depends(get_kb)):
    ensure_own_patient(db, doctor, patient_id)
    return patient_history(db, kb, patient_id)


@doctor_router.put("/patients/{patient_id}/anamnesis", response_model=AnamnesisOut)
def update_anamnesis(patient_id: uuid.UUID, body: AnamnesisIn, doctor: User = Depends(require_doctor),
                     db: Session = Depends(get_db)):
    """Жалобы, история заболевания и примечания целиком. В журнал — поля, которые поменялись, с новым текстом."""
    ensure_own_patient(db, doctor, patient_id)
    a = db.get(Anamnesis, patient_id)
    new = {f: getattr(body, f) or None for f in ANAMNESIS_FIELDS}
    changed = {f: v for f, v in new.items() if v != (getattr(a, f) if a else None)}
    if changed:
        if a is None:
            a = Anamnesis(patient_id=patient_id)
            db.add(a)
        for f, v in changed.items():
            setattr(a, f, v)
        a.updated_by, a.updated_at = doctor.id, utcnow()
        audit(db, doctor.id, "anamnesis.updated", "patient", patient_id, changed)
        db.commit()
    return anamnesis_out(db, a)


@doctor_router.post("/patients/{patient_id}/diagnoses", response_model=DiagnosisOut)
def add_diagnosis(patient_id: uuid.UUID, body: DiagnosisIn, doctor: User = Depends(require_doctor),
                  db: Session = Depends(get_db)):
    """Диагноз от врача сразу подтверждён им; откуда он — обязательно. Его видит проверка назначения (dx())."""
    ensure_own_patient(db, doctor, patient_id)
    d = Diagnosis(patient_id=patient_id, icd10=body.icd10, title=body.title, confirmed_by=doctor.id,
                  source=body.source, source_note=body.source_note or None, diagnosed_on=body.diagnosed_on)
    db.add(d)
    db.flush()
    audit(db, doctor.id, "diagnosis.created", "diagnosis", d.id, body.model_dump(mode="json"))
    db.commit()
    return diagnosis_out(d)


@doctor_router.patch("/diagnoses/{diagnosis_id}", response_model=DiagnosisOut)
def update_diagnosis_source(diagnosis_id: uuid.UUID, body: DiagnosisSourceIn, doctor: User = Depends(require_doctor),
                            db: Session = Depends(get_db)):
    """Откуда диагноз и когда поставлен. Код и название не меняются: другой код — другой диагноз."""
    d = db.get(Diagnosis, diagnosis_id)
    if d is None:
        raise HTTPException(404, "Диагноз не найден")
    ensure_own_patient(db, doctor, d.patient_id)
    before = {"source": d.source, "source_note": d.source_note,
              "diagnosed_on": d.diagnosed_on.isoformat() if d.diagnosed_on else None}
    d.source, d.source_note, d.diagnosed_on = body.source, body.source_note or None, body.diagnosed_on
    audit(db, doctor.id, "diagnosis.source_updated", "diagnosis", d.id,
          {"before": before, "after": body.model_dump(mode="json")})
    db.commit()
    return diagnosis_out(d)


@doctor_router.post("/patients/{patient_id}/labs", response_model=LabResultOut)
def add_lab_result(patient_id: uuid.UUID, body: LabResultIn, doctor: User = Depends(require_doctor),
                   db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    """Результат анализа в единице из kb/labs.yaml: с ней сравнивают условия инструкции (lab('egfr') < 60).
    Исправить результат — внести новый с той же датой сдачи."""
    ensure_own_patient(db, doctor, patient_id)
    test = kb.labs.get(body.analyte)
    if test is None:
        raise HTTPException(422, f"Анализа «{body.analyte}» нет в базе знаний (kb/labs.yaml)")
    r = LabResult(patient_id=patient_id, analyte=test.id, value=body.value, unit=test.unit, taken_on=body.taken_on,
                  source=body.source, source_note=body.source_note or None, entered_by=doctor.id)
    db.add(r)
    db.flush()
    audit(db, doctor.id, "lab_result.created", "lab_result", r.id, body.model_dump(mode="json") | {"unit": test.unit})
    db.commit()
    return r


@patient_router.get("/history", response_model=PatientHistory)
def my_history(user: User = Depends(require_patient), db: Session = Depends(get_db),
               kb: KnowledgeBase = Depends(get_kb)):
    """«Моя история»: жалобы и анамнез, которые записал врач, диагнозы с источниками и анализы. Только чтение."""
    return patient_history(db, kb, user.id)
