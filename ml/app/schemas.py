"""Схема извлечения из истории болезни. Это контракт с бэкендом (ExtractedFact) и с разметкой eval/gold.
Поле evidence — дословная цитата из исходного текста, чтобы врач видел, откуда взят факт."""

from typing import Literal

from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    icd10: str | None = Field(None, description="Код МКБ-10, если указан или однозначно следует из текста")
    text: str
    evidence: str | None = None


class Medication(BaseModel):
    name: str = Field(description="МНН или торговое название, как в тексте")
    dose: str | None = None
    frequency: str | None = None
    status: Literal["current", "past", "unknown"] = "unknown"
    evidence: str | None = None


class Allergy(BaseModel):
    substance: str
    reaction: str | None = None
    evidence: str | None = None


class Condition(BaseModel):
    text: str
    icd10: str | None = None
    evidence: str | None = None


class ScaleScore(BaseModel):
    scale: str = Field(description="Название шкалы: GAD-7, PHQ-9, HAM-A, …")
    score: float
    evidence: str | None = None


class ExtractionResult(BaseModel):
    age: int | None = None
    sex: Literal["male", "female"] | None = None
    complaints: list[str] = []
    diagnoses: list[Diagnosis] = []
    comorbidities: list[Condition] = []
    medications: list[Medication] = []
    allergies: list[Allergy] = []
    scale_scores: list[ScaleScore] = []
    risk_flags: list[Literal["suicidal_ideation", "self_harm", "psychotic_symptoms", "substance_use",
                             "pregnancy"]] = Field(default=[], description="Только если явно упомянуто как наличие")


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
