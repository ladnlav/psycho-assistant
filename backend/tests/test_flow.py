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
