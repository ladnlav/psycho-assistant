"""Загрузчик демо-сценариев: scenarios/*.yaml → пациент с историей по неделям."""

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.kb import get_kb
from app.models import Alert, DiaryEntry, Prescription, ScaleResponse, User, utcnow
from app.scenarios import Scenario, answers_for, load_scenario, read_scenarios
from app.services.alerts import check_all_patients, patient_reminders
from tests.conftest import auth

KB = get_kb()
SCENARIO = Scenario.model_validate({
    "id": "t1", "title_ru": "Тест", "status": "draft", "author_ru": "тест",
    "patient": {"full_name": "Тест: женщина, 34 года", "email": "t1@example.com", "sex": "female", "age": 34},
    "diagnoses": [{"icd10": "F41.1", "title": "ГТР"}],
    "past_medications": ["Сертралин"],
    "prescribe_aviandr": True,
    "weeks": [
        {"week": 0, "anxiety": 8, "mood": 3, "sleep": 4, "gad7": 15, "phq9": 9, "intake_days": 7},
        {"week": 1, "anxiety": 7, "mood": 4, "sleep": 5, "intake_days": 7},
        {"week": 2, "anxiety": 7, "mood": 4, "sleep": 5, "gad7": 12, "phq9": 10, "phq9_item9": 1, "intake_days": 3,
         "messages": ["Плохо сплю"]},
    ],
})


def test_repo_scenarios_are_valid():
    assert "s1" in read_scenarios(get_settings().scenarios_dir)


def test_answers_for_keeps_sum_and_fixed_items():
    answers = answers_for(KB.scales["phq9"], 10, {"item9": 1})
    assert sum(answers.values()) == 10 and answers["item9"] == 1
    with pytest.raises(ValueError):
        answers_for(KB.scales["gad7"], 22)


def test_intakes_need_aviandr():
    with pytest.raises(ValidationError, match="prescribe_aviandr"):
        Scenario.model_validate(SCENARIO.model_dump() | {"prescribe_aviandr": False})


def test_load_scenario(client, doctor_token):
    today = utcnow().date()
    with SessionLocal() as db:
        doctor = db.scalar(select(User).where(User.email == "doc@example.com"))
        patient = load_scenario(db, KB, SCENARIO, doctor, "test-password", today)
        db.commit()
        pid = patient.id

        days = db.scalars(select(DiaryEntry.day).where(DiaryEntry.patient_id == pid)).all()
        assert len(days) == 21 and max(days) == today - timedelta(days=1), "последняя неделя заканчивается вчера"
        totals = db.scalars(select(ScaleResponse.total).where(ScaleResponse.patient_id == pid,
                                                              ScaleResponse.scale_id == "gad7")).all()
        assert sorted(totals) == [12, 15]
        rx = db.scalars(select(Prescription).where(Prescription.patient_id == pid)).all()
        assert {(p.drug_name, p.active) for p in rx} == {("Авиандр", True), ("Сертралин", False)}
        rules = set(db.scalars(select(Alert.rule_id).where(Alert.patient_id == pid)))
        assert {"phq9_suicidal_ideation", "low_adherence"} <= rules, "алерты по итоговому состоянию"

        assert load_scenario(db, KB, SCENARIO, doctor, "test-password", today) is None, "повторно — пропуск"
        load_scenario(db, KB, SCENARIO, doctor, "test-password", today, reset=True)
        db.commit()
        assert db.scalar(select(func.count()).select_from(DiaryEntry).where(DiaryEntry.patient_id == pid)) == 21

    names = [p["full_name"] for p in client.get("/api/doctor/patients", headers=auth(doctor_token)).json()]
    assert "Тест: женщина, 34 года" in names


def test_silent_patient_scenario_shows_c9(client, doctor_token):
    """Сценарий 5: записи кончились 6 дней назад — напоминание пациентке и алерт врачу, без «низкой приверженности»."""
    sc = read_scenarios(get_settings().scenarios_dir)["s5"]
    today = utcnow().date()
    with SessionLocal() as db:
        doctor = db.scalar(select(User).where(User.email == "doc@example.com"))
        pid = load_scenario(db, KB, sc, doctor, "test-password", today).id
        db.commit()
        last = db.scalar(select(func.max(DiaryEntry.day)).where(DiaryEntry.patient_id == pid))
        assert last == today - timedelta(days=6)
        alerts = db.scalars(select(Alert).where(Alert.patient_id == pid)).all()
        assert [(a.rule_id, a.trigger) for a in alerts] == [("no_reports_5d", "schedule")]
        assert "no_reports_3d" in [rid for rid, _ in patient_reminders(db, KB, pid)]
        with SessionLocal() as other:
            assert check_all_patients(other, KB) == [], "проверка по расписанию не повторяет алерт"
