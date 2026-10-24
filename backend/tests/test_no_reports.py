"""C9: нет записей пациента 3 дня — напоминание в приложении, 5 дней — алерт врачу. Молчание не порождает
записей, поэтому правила проверяются ещё и по расписанию (services/alerts.check_all_patients)."""

import uuid
from datetime import timedelta

import pytest

from app.db import SessionLocal
from app.kb import Rule, get_kb
from app.models import DiaryEntry, Prescription, User, utcnow
from app.services.alerts import check_all_patients
from tests.conftest import auth

DIARY = {"anxiety": 5, "mood": 5, "sleep_quality": 5}


def patient_id(client, doctor_token) -> uuid.UUID:
    return uuid.UUID(client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"])


def silent_for(pid: uuid.UUID, days: int) -> None:
    """Пациент последний раз заполнил дневник `days` дней назад."""
    at = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        db.get(User, pid).created_at = at - timedelta(days=1)
        db.add(DiaryEntry(patient_id=pid, day=at.date(), anxiety=5, mood=5, sleep_quality=5, created_at=at))
        db.commit()


def scheduled_check() -> int:
    """Число алертов, которые проверка по расписанию отправила бы врачу."""
    with SessionLocal() as db:
        return len(check_all_patients(db, get_kb()))


def reminders(client, token) -> list[str]:
    return [r["rule_id"] for r in client.get("/api/patient/reminders", headers=auth(token)).json()]


def open_alerts(client, doctor_token) -> list[dict]:
    return client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()


def test_new_patient_gets_nothing(client, doctor_token, patient_token):
    assert reminders(client, patient_token) == []
    assert scheduled_check() == 0


def test_three_days_remind_patient_only(client, doctor_token, patient_token):
    silent_for(patient_id(client, doctor_token), 3)
    assert reminders(client, patient_token) == ["no_reports_3d"]
    assert scheduled_check() == 0 and open_alerts(client, doctor_token) == [], "врачу на 3-й день ничего не приходит"

    client.post("/api/patient/diary", json=DIARY, headers=auth(patient_token))
    assert reminders(client, patient_token) == [], "новая запись снимает напоминание"


def test_five_days_alert_doctor_once_per_silence(client, doctor_token, patient_token, monkeypatch):
    silent_for(patient_id(client, doctor_token), 5)
    assert reminders(client, patient_token) == ["no_reports_3d"]
    assert scheduled_check() == 1
    [alert] = open_alerts(client, doctor_token)
    assert alert["rule_id"] == "no_reports_5d" and alert["trigger"] == "schedule"
    assert list(alert["evidence"]) == ["last_report"], "в отпечатке — дата последней записи, а не число дней"
    assert scheduled_check() == 0, "тот же перерыв: повторно не отправляем"

    client.post(f"/api/doctor/alerts/{alert['id']}/ack", headers=auth(doctor_token))
    tomorrow = utcnow() + timedelta(days=1)
    monkeypatch.setattr("app.services.context.utcnow", lambda: tomorrow)
    assert scheduled_check() == 0, "шестой день того же перерыва — не новый алерт"

    client.post("/api/patient/diary", json=DIARY, headers=auth(patient_token))
    assert open_alerts(client, doctor_token) == [] and reminders(client, patient_token) == []


def test_schedule_checks_only_time_rules(client, doctor_token, patient_token):
    """У молчащего пациента нет отметок приёма; «низкая приверженность» по расписанию не должна обгонять C9."""
    pid = patient_id(client, doctor_token)
    doctor_id = uuid.UUID(client.get("/api/auth/me", headers=auth(doctor_token)).json()["id"])
    with SessionLocal() as db:
        db.add(Prescription(patient_id=pid, doctor_id=doctor_id, drug_name="Тестовый препарат",
                            start_date=utcnow().date() - timedelta(days=14)))
        db.commit()
    silent_for(pid, 5)
    assert scheduled_check() == 1
    assert [a["rule_id"] for a in open_alerts(client, doctor_token)] == ["no_reports_5d"]


def test_chat_message_counts_as_report(client, doctor_token, patient_token):
    silent_for(patient_id(client, doctor_token), 5)
    client.post("/api/patient/messages", json={"body": "Добрый день, всё в порядке"}, headers=auth(patient_token))
    assert reminders(client, patient_token) == [] and scheduled_check() == 0


def test_reminder_rule_needs_text():
    with pytest.raises(ValueError, match="remind_ru"):
        Rule(id="x", title_ru="X", level="medium", status="draft", when="days_since_report >= 3",
             actions=["remind_patient"])
