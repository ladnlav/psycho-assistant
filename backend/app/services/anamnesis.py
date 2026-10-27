"""Анамнез, диагнозы с источниками и анализы в одном ответе: раздел «Анамнез» у врача и «Моя история» у пациента."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kb import KnowledgeBase
from app.models import Anamnesis, Diagnosis, LabResult, User
from app.schemas import AnamnesisOut, DiagnosisOut, LabResultOut, LabTestOut, PatientHistory


def diagnosis_out(d: Diagnosis) -> DiagnosisOut:
    return DiagnosisOut(id=d.id, icd10=d.icd10, title=d.title, confirmed=d.confirmed_by is not None,
                        source=d.source, source_note=d.source_note, diagnosed_on=d.diagnosed_on)


def diagnoses(db: Session, patient_id: uuid.UUID) -> list[DiagnosisOut]:
    return [diagnosis_out(d) for d in db.scalars(select(Diagnosis).where(Diagnosis.patient_id == patient_id)
                                                 .order_by(Diagnosis.created_at, Diagnosis.icd10))]


def anamnesis_out(db: Session, a: Anamnesis | None) -> AnamnesisOut:
    if a is None:
        return AnamnesisOut()
    author = db.get(User, a.updated_by) if a.updated_by else None
    return AnamnesisOut(complaints=a.complaints, history=a.history, notes=a.notes, updated_at=a.updated_at,
                        updated_by_name=author.full_name if author else None)


def patient_history(db: Session, kb: KnowledgeBase, patient_id: uuid.UUID) -> PatientHistory:
    labs = db.scalars(select(LabResult).where(LabResult.patient_id == patient_id)
                      .order_by(LabResult.taken_on.desc(), LabResult.created_at.desc()))
    return PatientHistory(
        anamnesis=anamnesis_out(db, db.get(Anamnesis, patient_id)),
        diagnoses=diagnoses(db, patient_id),
        labs=[LabResultOut.model_validate(r) for r in labs],
        lab_tests=[LabTestOut.model_validate(t.model_dump()) for t in kb.labs.values()],
    )
