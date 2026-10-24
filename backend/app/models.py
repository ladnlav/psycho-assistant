"""Модель данных. Перечисления хранятся строками (String), допустимые значения — в константах ниже,
чтобы расширение не требовало миграции типа ENUM."""

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")

ROLES = ("doctor", "patient")
ALERT_LEVELS = ("critical", "high", "medium")
REFERRAL_LEVELS = ("mandatory", "desirable")
DECISION_STATUSES = ("proposed", "accepted", "rejected")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, index=True)


def _patient_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("patient_profiles.user_id", ondelete="CASCADE"), index=True)


# --- Пользователи и связь врач–пациент -------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()

    doctor_profile: Mapped["DoctorProfile | None"] = relationship(back_populates="user", uselist=False)
    patient_profile: Mapped["PatientProfile | None"] = relationship(back_populates="user", uselist=False)


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    specialty: Mapped[str] = mapped_column(String(50))  # therapist | neurologist | psychiatrist | ...
    user: Mapped[User] = relationship(back_populates="doctor_profile")


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(10))
    user: Mapped[User] = relationship(back_populates="patient_profile")


class Invite(Base):
    """Код, который врач выдаёт пациенту для регистрации и привязки."""
    __tablename__ = "invites"
    id: Mapped[uuid.UUID] = _id()
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    patient_label: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created()
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class DoctorPatientLink(Base):
    """Пациент закреплён за ведущим врачом; данные пациента видит только он."""
    __tablename__ = "doctor_patient_links"
    __table_args__ = (UniqueConstraint("doctor_id", "patient_id"),)
    id: Mapped[uuid.UUID] = _id()
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    kind: Mapped[str] = mapped_column(String(50))  # pd_processing | telemedicine
    version: Mapped[str] = mapped_column(String(20))
    accepted_at: Mapped[datetime] = _created()


# --- Клинические данные ----------------------------------------------------------------------

class ClinicalDocument(Base):
    """Исходный текст истории болезни / выписки (вход для LLM-извлечения)."""
    __tablename__ = "clinical_documents"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(255))
    source_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class ExtractedFact(Base):
    """Факт, извлечённый из документа. В карточку попадает только после проверки врачом."""
    __tablename__ = "extracted_facts"
    id: Mapped[uuid.UUID] = _id()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinical_documents.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(50))  # diagnosis | medication | allergy | comorbidity | ...
    value: Mapped[dict[str, Any]] = mapped_column(JSONType)
    evidence: Mapped[str | None] = mapped_column(Text)  # цитата из исходного текста
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    icd10: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(255))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    drug_id: Mapped[str | None] = mapped_column(String(50))  # id из kb/drugs, если препарат там есть
    drug_name: Mapped[str] = mapped_column(String(255))
    dose_mg: Mapped[float | None] = mapped_column(Float)
    frequency: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class MedicationIntake(Base):
    __tablename__ = "medication_intakes"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    prescription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prescriptions.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20))  # taken | missed
    created_at: Mapped[datetime] = _created()


class ScaleResponse(Base):
    __tablename__ = "scale_responses"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    scale_id: Mapped[str] = mapped_column(String(50), index=True)  # id из kb/scales
    answers: Mapped[dict[str, int]] = mapped_column(JSONType)
    total: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(30))
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    day: Mapped[date] = mapped_column(Date, index=True)
    anxiety: Mapped[int] = mapped_column(Integer)  # 0–10
    mood: Mapped[int] = mapped_column(Integer)  # 0–10
    sleep_quality: Mapped[int | None] = mapped_column(Integer)  # 0–10
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class AdverseEvent(Base):
    __tablename__ = "adverse_events"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prescriptions.id"))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))  # mild | moderate | severe
    serious: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    triage: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # результат ml/triage по описанию
    created_at: Mapped[datetime] = _created()


# --- Решения, алерты, коммуникация, аудит ----------------------------------------------------

class Recommendation(Base):
    """Предложение системы. Действует только после решения врача (accepted)."""
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    kind: Mapped[str] = mapped_column(String(30))  # referral | therapy | assessment | safety
    title: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    sources: Mapped[list[str]] = mapped_column(JSONType, default=list)
    rule_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_at: Mapped[datetime] = _created()
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendations.id"))
    to_specialty: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(20))  # mandatory | desirable
    reason: Mapped[str] = mapped_column(Text)
    confirmed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    sources: Mapped[list[str]] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = _created()
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    @property
    def updated_at(self) -> datetime | None:
        """Когда в открытый алерт последний раз пришли новые данные (services/alerts.apply_rules)."""
        value = (self.details or {}).get("updated_at")
        return datetime.fromisoformat(value) if value else None

    @property
    def trigger(self) -> str | None:
        """Что запустило проверку: scale:gad7, diary, message, schedule…"""
        return (self.details or {}).get("trigger")

    @property
    def evidence(self) -> dict[str, Any]:
        """Данные, на которых сработало правило, без служебных id записей (rules.RECORD)."""
        return {k: v for k, v in ((self.details or {}).get("evidence") or {}).items() if not k.endswith("._record")}

    @property
    def updates(self) -> int:
        return (self.details or {}).get("updates", 0)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _id()
    patient_id: Mapped[uuid.UUID] = _patient_fk()
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="chat", server_default="chat")  # chat | help — просьба о помощи
    triage: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # результат ml/triage
    created_at: Mapped[datetime] = _created()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = _id()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = _created()
