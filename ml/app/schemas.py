"""Схема извлечения из истории болезни. Это контракт с бэкендом (ExtractedFact) и с разметкой eval/gold.
Поле evidence — дословная цитата из исходного текста, чтобы врач видел, откуда взят факт."""

from typing import Literal

from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    icd10: str | None = Field(None, description="Код МКБ-10, явно указанный рядом с диагнозом. Обязательно скопируй, если он есть; иначе null.")
    text: str
    status: Literal["confirmed", "suspected"] = Field("confirmed", description="если после диагноза есть '?' - suspected")
    evidence: str | None = None


class Medication(BaseModel):
    name: str = Field(description="МНН или торговое название, как в тексте")
    dose: str | None = Field(None, description="например, масса или количество таблеток, как в тексте")
    frequency: str | None = Field(None, description="Раз в какое время, как в тексте")
    status: Literal["current", "past", "unknown"] = Field("unknown", description="Для назначенных и которые уже пациент принимает - current, которые закончил принимать - past")
    evidence: str | None = Field(None, description="Кратко с главной сутью и дословно")


class Allergy(BaseModel):
    substance: str
    reaction: str | None = None
    evidence: str | None = None


class Condition(BaseModel):
    icd10: str | None = Field(None, description="Код МКБ-10, явно указанный рядом с диагнозом. Обязательно скопируй, если он есть; иначе null.")
    text: str
    status: Literal["confirmed", "suspected"] = Field("confirmed", description="если после диагноза есть '?' - suspected")
    evidence: str | None = None


class ScaleScore(BaseModel):
    scale: str = Field(description="Название шкалы: GAD-7, PHQ-9, HAM-A, AUDIT и другие")
    score: float
    evidence: str | None = None


class ExtractionResult(BaseModel):
    age: int | None = Field(None, description="Определяется исключительно по прямому упоминанию возраста тексте (дата рождения не учитывается)")
    sex: Literal["male", "female"] | None = None
    complaints: list[str] = []
    diagnoses: list[Diagnosis] = Field(
        default_factory=list,
        description="Все психиатрические и неврологические диагнозы, включая заболевания центральной, периферической и вегетативной нервной системы."
    )
    comorbidities: list[Condition] = Field(
        default_factory=list,
        description="Остальные заболевания, не относящиеся к психиатрическим или неврологическим."
    )
    medications: list[Medication] = []
    allergies: list[Allergy] = []
    scale_scores: list[ScaleScore] = []
    risk_flags: list[Literal["suicidal_ideation", "self_harm", "psychotic_symptoms", "substance_use",
                             "pregnancy"]] = Field(default=[], description="Только если явно упомянуто как наличие pregnancy - беременности, substance_use - алкоголизма/наркомании, self_harm - действий направленных на самоповреждение, например, намеренные порезы, suicidal_ideation - в анамнезе если человек сам говорит о том что хочет умереть, psychotic_symptoms - если пациент бредит/галлюцинирует/теряет контакт с реальностью в контексте психотических симптомов, всё перечисленное только при прямом упоминании в тексте")


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1)


class ExtractResponse(BaseModel):
    result: ExtractionResult
    model: str
    elapsed_ms: float


class TriageRequest(BaseModel):
    text: str = Field(min_length=1)


class TriageResponse(BaseModel):
    level: Literal["critical", "attention", "none"]
    categories: list[str]
    matches: list[str]
    method: str
