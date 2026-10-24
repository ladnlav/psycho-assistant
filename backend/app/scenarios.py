"""Демо-сценарии: scenarios/*.yaml → пациенты демо-врача с историей по неделям.

    python -m app.scenarios                 # загрузить все сценарии (уже загруженные пропускаются)
    python -m app.scenarios s1 --reset      # перезагрузить сценарий: данные пациента создаются заново

Нужен демо-врач из app.seed; пароль пациентов сценариев — SEED_PASSWORD. Даты считаются от сегодняшнего дня:
последняя неделя сценария заканчивается вчера, а сегодняшний день пустой — его показывают на демо.
С last_report_days_ago > 1 история кончается раньше: пациент перестал вести записи (правила C9).
Формат файла — scenarios/README.md.
"""

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.kb import KnowledgeBase, Scale, get_kb
from app.models import (AdverseEvent, Alert, Consent, Diagnosis, DiaryEntry, DoctorPatientLink, MedicationIntake,
                        Message, PatientProfile, Prescription, Recommendation, Referral, ScaleResponse, User, utcnow)
from app.security import hash_password
from app.services.alerts import apply_rules, timed_rules
from app.services.audit import audit
from app.services.scoring import score

DOCTOR_EMAIL = "doctor@example.com"


class ScenarioPatient(BaseModel):
    full_name: str
    email: str
    sex: Literal["male", "female"]
    age: int = Field(ge=0, le=120)


class ScenarioDiagnosis(BaseModel):
    icd10: str
    title: str


class ScenarioAdverseEvent(BaseModel):
    description: str
    severity: Literal["mild", "moderate", "severe"]
    serious: bool = False


class Week(BaseModel):
    """Строка листа «Сценарий N»: неделя 0 — визит и назначение."""
    week: int = Field(ge=0)
    anxiety: int | None = Field(None, ge=0, le=10)
    mood: int | None = Field(None, ge=0, le=10)
    sleep: int | None = Field(None, ge=0, le=10)
    gad7: int | None = Field(None, ge=0, le=21)
    phq9: int | None = Field(None, ge=0, le=27)
    phq9_item9: int | None = Field(None, ge=0, le=3)
    intake_days: int | None = Field(None, ge=0, le=7)
    adverse_events: list[ScenarioAdverseEvent] = []
    messages: list[str] = []
    expected_ru: str | None = None  # что должна сделать система — для проверки демо, в базу не пишется

    @model_validator(mode="after")
    def _check(self) -> "Week":
        if self.phq9_item9 is not None and (self.phq9 is None or self.phq9_item9 > self.phq9):
            raise ValueError(f"неделя {self.week}: пункт 9 PHQ-9 задаётся вместе с суммой PHQ-9 и не больше неё")
        if (self.anxiety is None) != (self.mood is None):
            raise ValueError(f"неделя {self.week}: самочувствие задаётся тревогой и настроением вместе")
        return self


class Scenario(BaseModel):
    id: str
    title_ru: str
    status: Literal["draft", "validated"]
    author_ru: str
    show_ru: str | None = None
    complaints_ru: str | None = None  # для описания сценария; в базу не пишется
    patient: ScenarioPatient
    diagnoses: list[ScenarioDiagnosis] = []
    past_medications: list[str] = []
    prescribe_aviandr: bool = False
    aviandr_dose_mg: float | None = None
    last_report_days_ago: int = Field(1, ge=1)  # 1 — последняя запись вчера; больше — пациент перестал писать (C9)
    weeks: list[Week] = []
    expected: dict[str, str] = {}

    @model_validator(mode="after")
    def _check(self) -> "Scenario":
        numbers = [w.week for w in self.weeks]
        if numbers != sorted(set(numbers)):
            raise ValueError(f"{self.id}: недели должны идти по возрастанию без повторов")
        if any(w.intake_days is not None for w in self.weeks) and not self.prescribe_aviandr:
            raise ValueError(f"{self.id}: отметки приёма есть, а Авиандр не назначен (prescribe_aviandr)")
        return self


def read_scenarios(path: Path) -> dict[str, Scenario]:
    out = {}
    for file in sorted(path.glob("*.yaml")):
        sc = Scenario.model_validate(yaml.safe_load(file.read_text(encoding="utf-8")))
        if sc.id != file.stem:
            raise ValueError(f"{file.name}: id «{sc.id}» должен совпадать с именем файла")
        out[sc.id] = sc
    return out


def answers_for(scale: Scale, total: int, fixed: dict[str, int] | None = None) -> dict[str, int]:
    """Ответы шкалы с заданной суммой: закреплённые пункты как есть, остальное поровну по прочим пунктам."""
    fixed = fixed or {}
    top = max(o.value for o in scale.options)
    free = [i.id for i in scale.items if i.id not in fixed]
    rest = total - sum(fixed.values())
    if not 0 <= rest <= top * len(free):
        raise ValueError(f"{scale.id}: сумму {total} нельзя набрать при пунктах {fixed}")
    answers = dict(fixed)
    for n, item_id in enumerate(free):
        answers[item_id] = rest // len(free) + (1 if n < rest % len(free) else 0)
    return answers


def _at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=timezone.utc)


def _purge(db: Session, patient_id) -> None:
    """Стирает данные пациента сценария; учётная запись, профиль и привязка к врачу остаются."""
    for model in (Referral, Recommendation, Alert, Message, AdverseEvent, MedicationIntake, Prescription,
                  DiaryEntry, ScaleResponse, Diagnosis):
        db.execute(delete(model).where(model.patient_id == patient_id))


def load_scenario(db: Session, kb: KnowledgeBase, sc: Scenario, doctor: User, password: str, today: date,
                  reset: bool = False) -> User | None:
    """Создаёт пациента сценария. Уже загруженный сценарий пропускается (None), если не reset."""
    user = db.scalar(select(User).where(User.email == sc.patient.email))
    if user is not None and not reset:
        return None
    birth = date(today.year - sc.patient.age, 1, 1)  # ровно age полных лет в любой день года
    if user is None:
        user = User(email=sc.patient.email, password_hash=hash_password(password), role="patient",
                    full_name=sc.patient.full_name)
        db.add(user)
        db.flush()
        db.add(PatientProfile(user_id=user.id, birth_date=birth, sex=sc.patient.sex))
        db.flush()  # согласие и привязка ссылаются на профиль
        db.add_all([Consent(patient_id=user.id, kind="pd_processing", version="demo"),
                    DoctorPatientLink(doctor_id=doctor.id, patient_id=user.id)])
    else:
        _purge(db, user.id)
        user.full_name = sc.patient.full_name
        profile = db.get(PatientProfile, user.id)
        profile.birth_date, profile.sex = birth, sc.patient.sex
    db.flush()

    weeks = (sc.weeks[-1].week + 1) if sc.weeks else 0
    end = today - timedelta(days=sc.last_report_days_ago - 1)  # первый день без записей
    start = end - timedelta(days=7 * weeks)
    for d in sc.diagnoses:
        db.add(Diagnosis(patient_id=user.id, icd10=d.icd10, title=d.title, confirmed_by=doctor.id))
    for name in sc.past_medications:  # до назначения Авиандра, уже отменены
        db.add(Prescription(patient_id=user.id, doctor_id=doctor.id, drug_name=name, active=False,
                            start_date=start - timedelta(days=90), end_date=start - timedelta(days=1)))
    rx = None
    if sc.prescribe_aviandr:
        drug = kb.drugs["aviandr"]
        rx = Prescription(patient_id=user.id, doctor_id=doctor.id, drug_id=drug.id, drug_name=drug.trade_name,
                          dose_mg=sc.aviandr_dose_mg, start_date=start)
        db.add(rx)
        db.flush()

    for w in sc.weeks:
        first = start + timedelta(days=7 * w.week)
        for d in range(7):
            day = first + timedelta(days=d)
            if w.anxiety is not None:
                db.add(DiaryEntry(patient_id=user.id, day=day, anxiety=w.anxiety, mood=w.mood,
                                  sleep_quality=w.sleep, created_at=_at(day, 20)))
            if w.intake_days is not None:
                db.add(MedicationIntake(patient_id=user.id, prescription_id=rx.id, day=day,
                                        status="taken" if d < w.intake_days else "missed", created_at=_at(day, 9)))
        for scale_id, total, fixed in (("gad7", w.gad7, None),
                                       ("phq9", w.phq9, None if w.phq9_item9 is None else {"item9": w.phq9_item9})):
            if total is None:
                continue
            scale = kb.scales[scale_id]
            answers = answers_for(scale, total, fixed)
            result = score(scale, answers)
            db.add(ScaleResponse(patient_id=user.id, scale_id=scale_id, answers=answers, total=result.total,
                                 severity=result.severity, submitted_by=user.id, created_at=_at(first, 10)))
        for ae in w.adverse_events:
            db.add(AdverseEvent(patient_id=user.id, description=ae.description, severity=ae.severity,
                                serious=ae.serious, reported_by=user.id, created_at=_at(first + timedelta(days=3), 12)))
        for text in w.messages:
            db.add(Message(patient_id=user.id, sender_id=user.id, body=text, created_at=_at(first + timedelta(days=2), 18)))
    db.flush()
    # Алерты по итоговому состоянию — как если бы пациент только что прислал последние данные. Если с тех пор
    # пациент молчит, правила отработали в день последней записи, а дальше — только проверка по расписанию:
    # иначе у молчащего пациента без отметок приёма сработала бы ещё и «низкая приверженность».
    silent_since = _at(end - timedelta(days=1), 21) if sc.last_report_days_ago > 1 else None
    apply_rules(db, kb, user.id, trigger=f"scenario:{sc.id}", now=silent_since)
    if silent_since:
        apply_rules(db, kb, user.id, trigger="schedule", rules=timed_rules(kb))
    audit(db, doctor.id, "scenario.loaded", "patient", user.id, {"scenario": sc.id, "reset": reset})
    return user


def main() -> None:
    ap = argparse.ArgumentParser(description="Загрузка демо-сценариев из scenarios/*.yaml")
    ap.add_argument("ids", nargs="*", help="id сценариев (по умолчанию все)")
    ap.add_argument("--reset", action="store_true", help="перезагрузить уже загруженные")
    args = ap.parse_args()
    password = os.environ.get("SEED_PASSWORD")
    if not password:
        raise SystemExit("Задайте SEED_PASSWORD (см. .env.example)")
    kb, scenarios = get_kb(), read_scenarios(get_settings().scenarios_dir)
    unknown = set(args.ids) - set(scenarios)
    if unknown:
        raise SystemExit(f"Нет сценариев {sorted(unknown)}; есть {sorted(scenarios)}")
    with SessionLocal() as db:
        doctor = db.scalar(select(User).where(User.email == DOCTOR_EMAIL))
        if doctor is None:
            raise SystemExit("Нет демо-врача: сначала python -m app.seed")
        for sid in args.ids or scenarios:
            user = load_scenario(db, kb, scenarios[sid], doctor, password, utcnow().date(), reset=args.reset)
            db.commit()
            print(f"{sid}: " + (f"загружен — {scenarios[sid].patient.email}" if user else "уже загружен (--reset)"))


if __name__ == "__main__":
    main()
