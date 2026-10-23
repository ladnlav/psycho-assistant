"""Триаж свободного текста: сообщения врачу и описания НЯ → правило free_text_risk → алерт и экран помощи.

Сам триаж (словарь ml-сервиса) подменён в conftest: «умереть», «умираю» — риск, остальное — нет.
"""

from tests.conftest import auth
from tests.test_flow import DIARY, ack_all, proposed

RISKY = "Доктор, иногда хочу умереть"


def alerts(client, doctor_token):
    return [a["rule_id"] for a in client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()]


def test_risky_message_alerts_doctor_and_shows_safety(client, doctor_token, patient_token):
    r = client.post("/api/patient/messages", json={"body": RISKY}, headers=auth(patient_token))
    assert r.status_code == 200 and r.json()["body"] == RISKY
    assert r.json()["safety"] is not None, "пациенту сразу экран помощи"
    assert alerts(client, doctor_token) == ["free_text_risk"]
    [rec] = proposed(client, doctor_token)
    assert rec["payload"]["level"] == "mandatory" and rec["payload"]["to"] == "psychiatrist"


def test_risky_adverse_event_description(client, doctor_token, patient_token):
    """Прогон 23.10: «Смерть умираю» в описании побочного эффекта система не заметила."""
    r = client.post("/api/patient/adverse-events", json={"description": "Смерть умираю", "severity": "mild"},
                    headers=auth(patient_token))
    assert r.status_code == 200 and r.json()["safety"] is not None
    assert alerts(client, doctor_token) == ["free_text_risk"]


def test_neutral_text_and_doctor_messages_do_not_alert(client, doctor_token, patient_token):
    r = client.post("/api/patient/messages", json={"body": "Всё хорошо, спасибо"}, headers=auth(patient_token))
    assert r.json()["safety"] is None
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    client.post(f"/api/doctor/patients/{pid}/messages", json={"body": "Если захочется умереть — звоните 112"},
                headers=auth(doctor_token))
    assert alerts(client, doctor_token) == [], "размечаем только текст пациента"


def test_alert_repeats_only_on_new_risky_text(client, doctor_token, patient_token):
    client.post("/api/patient/messages", json={"body": RISKY}, headers=auth(patient_token))
    ack_all(client, doctor_token)

    client.post("/api/patient/diary", json=DIARY, headers=auth(patient_token))
    r = client.post("/api/patient/messages", json={"body": "Сегодня получше"}, headers=auth(patient_token))
    assert r.json()["safety"] is None and alerts(client, doctor_token) == [], "старое сообщение не повторяет алерт"

    client.post("/api/patient/messages", json={"body": "Опять думаю, что лучше умереть"}, headers=auth(patient_token))
    assert alerts(client, doctor_token) == ["free_text_risk"]


def test_message_saved_when_ml_is_down(client, doctor_token, patient_token, triage):
    triage["down"] = True
    r = client.post("/api/patient/messages", json={"body": RISKY}, headers=auth(patient_token))
    assert r.status_code == 200 and r.json()["safety"] is None
    assert alerts(client, doctor_token) == []
    assert [m["body"] for m in client.get("/api/patient/messages", headers=auth(patient_token)).json()] == [RISKY]
