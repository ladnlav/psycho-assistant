"""Загрузка и проверка базы знаний (kb/*.yaml)."""

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings

Status = Literal["draft", "validated"]


class Source(BaseModel):
    id: str
    type: Literal["paper", "guideline", "instruction", "license", "other"]
    title: str
    url: str | None = None
    verified: bool = False
    note: str | None = None


class ScaleOption(BaseModel):
    value: int
    label_en: str
    label_ru: str | None = None


class ScaleItem(BaseModel):
    id: str
    text_en: str
    text_ru: str | None = None


class SeverityBand(BaseModel):
    min: int
    max: int
    level: str
    label_ru: str


class License(BaseModel):
    type: Literal["free", "public_domain", "licensed"]
    holder: str | None = None
    source: str | None = None
    permission_obtained: bool = False


class ValidationRu(BaseModel):
    status: Literal["todo", "confirmed"]
    source: str | None = None


class Scale(BaseModel):
    id: str
    name: str
    title_ru: str
    rater: Literal["patient", "clinician"]
    status: Status
    schedule_days: int | None = None
    instruction_en: str
    instruction_ru: str | None = None
    options: list[ScaleOption]
    items: list[ScaleItem]
    severity: list[SeverityBand]
    mcid: float | None = None
    license: License
    validation_ru: ValidationRu
    sources: list[str] = []

    @property
    def max_total(self) -> int:
        return len(self.items) * max(o.value for o in self.options)

    @model_validator(mode="after")
    def _check(self) -> "Scale":
        if self.license.type == "licensed" and not self.license.permission_obtained:
            raise ValueError(f"{self.id}: лицензируемая шкала без разрешения правообладателя")
        bands = sorted(self.severity, key=lambda b: b.min)
        expected = min(o.value for o in self.options) * len(self.items)
        for band in bands:
            if band.min != expected:
                raise ValueError(f"{self.id}: пороги тяжести должны идти без разрывов (ожидался min={expected})")
            expected = band.max + 1
        if expected - 1 != self.max_total:
            raise ValueError(f"{self.id}: пороги тяжести не покрывают максимум {self.max_total}")
        return self


class Proposal(BaseModel):
    kind: Literal["referral"]
    to: str
    level: Literal["mandatory", "desirable"]
    reason_ru: str


class Rule(BaseModel):
    id: str
    title_ru: str
    level: Literal["critical", "high", "medium"]
    status: Status
    when: str
    actions: list[Literal["notify_doctor", "patient_safety_screen", "remind_patient"]]
    propose: list[Proposal] = []
    sources: list[str] = []

    @model_validator(mode="after")
    def _check_expr(self) -> "Rule":
        try:
            ast.parse(self.when, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"{self.id}: синтаксическая ошибка в when: {e}") from e
        return self


# Имена, доступные в `when` пунктов инструкции (kb/README.md → «Препараты»).
DRUG_CHECK_NAMES = {"age", "sex", "dx", "taking"}


class DrugCheck(BaseModel):
    """Пункт инструкции из ГРЛС: противопоказание, «с осторожностью» или взаимодействие.
    Без `when` пункт не проверяется автоматически — врач подтверждает его сам."""
    id: str
    text_ru: str
    when: str | None = None
    severity: Literal["contraindicated", "caution"] | None = None  # только для взаимодействий

    @model_validator(mode="after")
    def _check_expr(self) -> "DrugCheck":
        if self.when is None:
            return self
        try:
            tree = ast.parse(self.when, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"{self.id}: синтаксическая ошибка в when: {e}") from e
        unknown = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - DRUG_CHECK_NAMES
        if unknown:
            raise ValueError(f"{self.id}: в when неизвестные имена {sorted(unknown)}, доступны {sorted(DRUG_CHECK_NAMES)}")
        return self


class Drug(BaseModel):
    id: str
    trade_name: str
    inn: str
    registered_rf: bool
    status: Status
    atc: str | None = None
    dosage_forms: list[str] = []
    indications: list[dict[str, Any]] = []
    contraindications: list[DrugCheck] = []
    caution: list[DrugCheck] = []
    dosing: dict[str, Any] = {}
    interactions: list[DrugCheck] = []
    adverse_events: list[dict[str, Any]] = []
    sources: list[str] = []

    @property
    def has_checks(self) -> bool:
        return bool(self.contraindications or self.caution or self.interactions)

    @model_validator(mode="after")
    def _check_items(self) -> "Drug":
        ids = [c.id for c in (*self.contraindications, *self.caution, *self.interactions)]
        if dup := {i for i in ids if ids.count(i) > 1}:
            raise ValueError(f"{self.id}: повторяются id пунктов инструкции {sorted(dup)}")
        if missing := [c.id for c in self.interactions if c.severity is None]:
            raise ValueError(f"{self.id}: у взаимодействий {missing} не указан severity (contraindicated | caution)")
        return self


class SafetyContact(BaseModel):
    title_ru: str
    phone: str


class Safety(BaseModel):
    message_ru: str
    contacts: list[SafetyContact]


class KnowledgeBase(BaseModel):
    scales: dict[str, Scale] = Field(default_factory=dict)
    rules: dict[str, Rule] = Field(default_factory=dict)
    drugs: dict[str, Drug] = Field(default_factory=dict)
    sources: dict[str, Source] = Field(default_factory=dict)
    safety: Safety

    @model_validator(mode="after")
    def _check_refs(self) -> "KnowledgeBase":
        for kind, entries in (("scale", self.scales), ("rule", self.rules), ("drug", self.drugs)):
            for entry in entries.values():
                missing = [s for s in entry.sources if s not in self.sources]
                if missing:
                    raise ValueError(f"{kind} {entry.id}: неизвестные источники {missing}")
        for scale in self.scales.values():
            for ref in (scale.license.source, scale.validation_ru.source):
                if ref and ref not in self.sources:
                    raise ValueError(f"scale {scale.id}: неизвестный источник {ref}")
        return self


def _read_dir(path: Path, model: type[BaseModel]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for file in sorted(path.glob("*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        obj = model.model_validate(data)
        if obj.id != file.stem:
            raise ValueError(f"{file.name}: id «{obj.id}» должен совпадать с именем файла")
        out[obj.id] = obj
    return out


def load_kb(kb_dir: Path) -> KnowledgeBase:
    raw_sources = yaml.safe_load((kb_dir / "sources.yaml").read_text(encoding="utf-8")) or {}
    sources = {sid: Source.model_validate({"id": sid, **body}) for sid, body in raw_sources.items()}
    safety = Safety.model_validate(yaml.safe_load((kb_dir / "safety.yaml").read_text(encoding="utf-8")))
    return KnowledgeBase(
        scales=_read_dir(kb_dir / "scales", Scale),
        rules=_read_dir(kb_dir / "rules", Rule),
        drugs=_read_dir(kb_dir / "drugs", Drug),
        sources=sources,
        safety=safety,
    )


@lru_cache
def get_kb() -> KnowledgeBase:
    return load_kb(get_settings().kb_dir)
