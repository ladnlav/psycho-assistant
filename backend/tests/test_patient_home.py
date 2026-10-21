"""Главная пациента: расписание шкал, одна запись дневника в день, отправленные побочные эффекты."""

from datetime import timedelta

from app.models import utcnow
from tests.conftest import auth

GAD7 = {f"item{i}": 1 for i in range(1, 8)}


def schedule(client, token) -> dict[str, dict]:
    return {s["scale_id"]: s for s in client.get("/api/patient/scales/schedule", headers=auth(token)).json()}


def test_scale_schedule_every_14_days(client, patient_token):
    assert all(s["due"] and s["last_taken_at"] is None for s in schedule(client, patient_token).values())

    client.post("/api/patient/scales/gad7", json={"answers": GAD7}, headers=auth(patient_token))
    s = schedule(client, patient_token)
    assert s["gad7"]["due"] is False
    assert s["gad7"]["next_due"] == str(utcnow().date() + timedelta(days=14))
    assert s["phq9"]["due"] is True

    # «Стало хуже — пройти сейчас»: раньше срока заполнить можно.
    r = client.post("/api/patient/scales/gad7", json={"answers": GAD7}, headers=auth(patient_token))
    assert r.status_code == 200


def test_diary_one_entry_per_day(client, patient_token):
    client.post("/api/patient/diary", json={"anxiety": 7, "mood": 3}, headers=auth(patient_token))
    client.post("/api/patient/diary", json={"anxiety": 4, "mood": 6, "note": "исправил"}, headers=auth(patient_token))
    diary = client.get("/api/patient/diary", headers=auth(patient_token)).json()
    assert [(d["anxiety"], d["mood"], d["note"]) for d in diary] == [(4, 6, "исправил")]


def test_patient_sees_sent_adverse_events(client, patient_token):
    body = {"description": "Тошнота по утрам", "severity": "mild"}
    sent = client.post("/api/patient/adverse-events", json=body, headers=auth(patient_token)).json()
    mine = client.get("/api/patient/adverse-events", headers=auth(patient_token)).json()
    assert [a["id"] for a in mine] == [sent["id"]]
