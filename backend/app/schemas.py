import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---

class DoctorRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    specialty: str = "therapist"


class PatientRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    invite_code: str
    consent_pd: bool = Field(description="Согласие на обработку персональных данных (152-ФЗ)")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Me(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["doctor", "patient"]
    specialty: str | None = None
    doctor_name: str | None = None


# --- clinical ---

class InviteCreate(BaseModel):
    patient_label: str | None = None


class InviteOut(ORM):
    code: str
    patient_label: str | None
    created_at: datetime
    used_at: datetime | None


class ScaleSubmit(BaseModel):
    answers: dict[str, int]


class SafetyScreen(BaseModel):
    message_ru: str
    contacts: list[dict[str, str]]


class ScaleResult(ORM):
    id: uuid.UUID
    scale_id: str
    total: int
    severity: str
    created_at: datetime


class ScaleSubmitResult(BaseModel):
    result: ScaleResult
    severity_label_ru: str
    safety: SafetyScreen | None = None


class DiaryIn(BaseModel):
    anxiety: int = Field(ge=0, le=10)
    mood: int = Field(ge=0, le=10)
    sleep_quality: int | None = Field(default=None, ge=0, le=10)
    note: str | None = None
    day: date | None = None


class DiaryOut(ORM):
    id: uuid.UUID
    day: date
    anxiety: int
    mood: int
    sleep_quality: int | None
    note: str | None


class ScaleSchedule(BaseModel):
    scale_id: str
    last_taken_at: datetime | None
    next_due: date | None
    due: bool


class AdverseEventIn(BaseModel):
    description: str
    severity: Literal["mild", "moderate", "severe"]
    serious: bool = False


class AdverseEventOut(ORM):
    id: uuid.UUID
    description: str
    severity: str
    serious: bool
    created_at: datetime


class AdverseEventSent(AdverseEventOut):
    safety: SafetyScreen | None = None  # экран помощи, если в описании есть признаки риска (kb/rules)


class PrescriptionIn(BaseModel):
    drug_id: str | None = Field(None, description="id из kb/drugs, если препарат там есть")
    drug_name: str
    dose_mg: float | None = None
    frequency: str | None = None
    start_date: date | None = None
    acknowledged_warnings: list[str] = Field([], description="id пунктов инструкции, которые врач учёл")
    override_note: str | None = Field(None, description="обоснование врача, если у пациента есть противопоказание")


class DrugWarning(BaseModel):
    id: str
    kind: Literal["contraindication", "caution", "interaction"]
    status: Literal["fired", "manual", "unchecked"]  # найдено в карточке | проверить вручную | нет данных
    text_ru: str
    section_ru: str
    detail_ru: str | None = None
    check_ru: str | None = None  # чем подтвердить или исключить пункт: анализы, осмотр (kb/drugs)
    requires_reason: bool = False
    sources: list[str] = []


class PrescriptionCheck(BaseModel):
    checked: bool
    notice_ru: str | None = None
    warnings: list[DrugWarning] = []


class PrescriptionOut(ORM):
    id: uuid.UUID
    drug_id: str | None
    drug_name: str
    dose_mg: float | None
    frequency: str | None
    start_date: date
    active: bool


class IntakeIn(BaseModel):
    prescription_id: uuid.UUID
    status: Literal["taken", "missed"]
    day: date | None = None


class IntakeOut(ORM):
    id: uuid.UUID
    prescription_id: uuid.UUID
    day: date
    status: str


class AlertOut(ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    rule_id: str
    level: str
    title: str
    sources: list[str]
    created_at: datetime
    delivered_at: datetime | None
    acknowledged_at: datetime | None
    updated_at: datetime | None = None  # новые данные в открытом алерте


class RecommendationOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    payload: dict[str, Any]
    sources: list[str]
    rule_id: str | None
    status: str
    created_at: datetime
    decided_at: datetime | None
    decision_note: str | None


class Decision(BaseModel):
    decision: Literal["accepted", "rejected"]
    note: str | None = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageOut(ORM):
    id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    created_at: datetime


class MessageSent(MessageOut):
    safety: SafetyScreen | None = None  # экран помощи, если в сообщении есть признаки риска (kb/rules)


class PatientSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    open_alerts: int
    top_alert_level: str | None
    last_scores: dict[str, ScaleResult]


class DiagnosisOut(BaseModel):
    id: uuid.UUID
    icd10: str
    title: str
    confirmed: bool = Field(description="подтверждён врачом")


class PatientCard(BaseModel):
    id: uuid.UUID
    full_name: str
    birth_date: date | None
    diagnoses: list[DiagnosisOut]
    scales: dict[str, list[ScaleResult]]
    diary: list[DiaryOut]
    prescriptions: list[PrescriptionOut]
    intakes: list[IntakeOut]
    pdc_7d: float | None
    adverse_events: list[AdverseEventOut]
    alerts: list[AlertOut]
    recommendations: list[RecommendationOut]
