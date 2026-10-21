"""Сквозной сценарий: врач → приглашение → пациент → PHQ-9 с п. 9 → алерт → решение врача."""

from tests.conftest import auth

PHQ9_ITEM9 = {f"item{i}": 0 for i in range(1, 10)} | {"item9": 1}


def test_critical_alert_and_doctor_decision(client, doctor_token, patient_token):
    r = client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    assert r.status_code == 200, r.text
    assert r.json()["safety"] is not None, "пациенту показан экран безопасности"

    patients = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()
    assert patients[0]["top_alert_level"] == "critical"
    pid = patients[0]["id"]

    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert [a["rule_id"] for a in card["alerts"]] == ["phq9_suicidal_ideation"]
    rec = card["recommendations"][0]
    assert rec["status"] == "proposed" and rec["payload"]["level"] == "mandatory"

    # Повторная отправка не плодит дубликаты, пока алерт не подтверждён.
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    assert len(client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()) == 1

    r = client.post(f"/api/doctor/recommendations/{rec['id']}/decision", json={"decision": "accepted"},
                    headers=auth(doctor_token))
    assert r.json()["status"] == "accepted"
    alert_id = card["alerts"][0]["id"]
    assert client.post(f"/api/doctor/alerts/{alert_id}/ack", headers=auth(doctor_token)).json()["acknowledged_at"]


GAD7_MILD = {f"item{i}": 1 for i in range(1, 8)}
DIARY = {"anxiety": 5, "mood": 5}


def ack_all(client, doctor_token):
    for a in client.get("/api/doctor/alerts", headers=auth(doctor_token)).json():
        client.post(f"/api/doctor/alerts/{a['id']}/ack", headers=auth(doctor_token))


def proposed(client, doctor_token):
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    return [r for r in card["recommendations"] if r["status"] == "proposed"]


def test_alert_not_repeated_without_new_data(client, doctor_token, patient_token):
    """Баг 21.10: после «Принято к сведению» любое действие пациента снова создавало алерт и направление."""
    for _ in range(2):  # второй ответ приходит, пока алерт открыт, — он дописывается в этот алерт
        client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    ack_all(client, doctor_token)

    client.post("/api/patient/diary", json=DIARY, headers=auth(patient_token))
    r = client.post("/api/patient/scales/gad7", json={"answers": GAD7_MILD}, headers=auth(patient_token))
    assert r.json()["safety"] is None, "экран безопасности — только на новый положительный ответ"
    assert client.get("/api/doctor/alerts", headers=auth(doctor_token)).json() == []
    assert len(proposed(client, doctor_token)) == 1


def test_new_positive_answer_after_ack_alerts_again(client, doctor_token, patient_token):
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    ack_all(client, doctor_token)

    r = client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    assert r.json()["safety"] is not None
    alerts = client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()
    assert [a["rule_id"] for a in alerts] == ["phq9_suicidal_ideation"]
    assert len(proposed(client, doctor_token)) == 1, "прежнее направление ждёт решения — второе не предлагаем"


def test_serious_adverse_event_alerts_once_per_event(client, doctor_token, patient_token):
    ae = {"description": "Обморок", "severity": "severe", "serious": True}
    client.post("/api/patient/adverse-events", json=ae, headers=auth(patient_token))
    ack_all(client, doctor_token)

    client.post("/api/patient/diary", json=DIARY, headers=auth(patient_token))
    assert client.get("/api/doctor/alerts", headers=auth(doctor_token)).json() == []

    client.post("/api/patient/adverse-events", json=ae, headers=auth(patient_token))
    alerts = client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()
    assert [a["rule_id"] for a in alerts] == ["serious_adverse_event"]


def test_prescription_and_intake(client, doctor_token, patient_token):
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    bad = client.post(f"/api/doctor/patients/{pid}/prescriptions", json={"drug_id": "unknown", "drug_name": "X"},
                      headers=auth(doctor_token))
    assert bad.status_code == 422, "только препараты из kb/drugs, зарегистрированные в РФ"

    rx = client.post(f"/api/doctor/patients/{pid}/prescriptions",
                     json={"drug_id": "aviandr", "drug_name": "Авиандр"}, headers=auth(doctor_token)).json()
    mine = client.get("/api/patient/prescriptions", headers=auth(patient_token)).json()
    assert [p["id"] for p in mine] == [rx["id"]]

    for status in ("missed", "taken"):  # повторная отметка за день — исправление, а не дубль
        r = client.post("/api/patient/intakes", json={"prescription_id": rx["id"], "status": status},
                        headers=auth(patient_token))
        assert r.status_code == 200, r.text
    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert [i["status"] for i in card["intakes"]] == ["taken"]
    assert card["pdc_7d"] is None, "в первый день приверженность не оценивается"
    assert card["alerts"] == []


def test_doctor_sees_only_own_patients(client, doctor_token, patient_token):
    other = client.post("/api/auth/register/doctor", json={
        "email": "other@example.com", "password": "test-password", "full_name": "Другой врач"}).json()["access_token"]
    assert client.get("/api/doctor/patients", headers=auth(other)).json() == []
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    assert client.get(f"/api/doctor/patients/{pid}", headers=auth(other)).status_code == 404


def test_roles_are_separated(client, doctor_token, patient_token):
    assert client.get("/api/doctor/patients", headers=auth(patient_token)).status_code == 403
    assert client.post("/api/patient/diary", json={"anxiety": 5, "mood": 5},
                       headers=auth(doctor_token)).status_code == 403


def test_registration_requires_consent_and_valid_invite(client, doctor_token):
    code = client.post("/api/doctor/invites", json={}, headers=auth(doctor_token)).json()["code"]
    body = {"email": "p2@example.com", "password": "test-password", "full_name": "П", "invite_code": code}
    assert client.post("/api/auth/register/patient", json=body | {"consent_pd": False}).status_code == 400
    assert client.post("/api/auth/register/patient", json=body | {"consent_pd": True}).status_code == 200
    reused = body | {"email": "p3@example.com", "consent_pd": True}
    assert client.post("/api/auth/register/patient", json=reused).status_code == 400
