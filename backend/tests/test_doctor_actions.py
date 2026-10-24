"""Действия врача в карточке: отмена назначения и направление без предложения правила."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog
from tests.conftest import auth

AVIANDR = {"drug_id": "aviandr", "drug_name": "Авиандр"}
REFERRAL = {"to_specialty": "psychotherapist", "level": "desirable", "reason": "Нужна когнитивно-поведенческая терапия"}
PHQ9_ITEM9 = {f"item{i}": 0 for i in range(1, 10)} | {"item9": 1}


def other_doctor(client) -> str:
    return client.post("/api/auth/register/doctor", json={
        "email": "other@example.com", "password": "test-password", "full_name": "Другой врач"}).json()["access_token"]


def patient_id(client, doctor_token) -> str:
    return client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]


def audit_rows(action: str) -> list[AuditLog]:
    with SessionLocal() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


def prescribe(client, doctor_token, pid) -> dict:
    check = client.post(f"/api/doctor/patients/{pid}/prescriptions/check", json=AVIANDR, headers=auth(doctor_token))
    acked = AVIANDR | {"acknowledged_warnings": [w["id"] for w in check.json()["warnings"]]}
    r = client.post(f"/api/doctor/patients/{pid}/prescriptions", json=acked, headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    return r.json()


def test_doctor_stops_prescription_with_reason(client, doctor_token, patient_token):
    pid = patient_id(client, doctor_token)
    rx = prescribe(client, doctor_token, pid)

    assert client.post(f"/api/doctor/prescriptions/{rx['id']}/stop", json={"reason": "Тошнота"},
                       headers=auth(other_doctor(client))).status_code == 404, "чужой врач не отменит назначение"

    r = client.post(f"/api/doctor/prescriptions/{rx['id']}/stop", json={"reason": "  Тошнота  "},
                    headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False and r.json()["end_date"]
    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert [p["active"] for p in card["prescriptions"]] == [False]
    assert client.get("/api/patient/prescriptions", headers=auth(patient_token)).json() == []

    [row] = audit_rows("prescription.stopped")
    assert row.entity_id == rx["id"] and row.data == {"reason": "Тошнота"}
    assert client.post(f"/api/doctor/prescriptions/{rx['id']}/stop",
                       headers=auth(doctor_token)).status_code == 409, "повторная отмена не меняет дату"


def test_stop_without_reason(client, doctor_token, patient_token):
    rx = prescribe(client, doctor_token, patient_id(client, doctor_token))
    assert client.post(f"/api/doctor/prescriptions/{rx['id']}/stop", headers=auth(doctor_token)).status_code == 200
    [row] = audit_rows("prescription.stopped")
    assert row.data == {"reason": None}


def test_doctor_refers_patient_without_rule(client, doctor_token, patient_token):
    pid = patient_id(client, doctor_token)
    r = client.post(f"/api/doctor/patients/{pid}/referrals", json=REFERRAL, headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    ref = r.json()
    assert ref["recommendation_id"] is None, "направление по решению врача, а не по правилу"

    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert [(x["id"], x["to_specialty"], x["level"], x["reason"]) for x in card["referrals"]] == [
        (ref["id"], "psychotherapist", "desirable", REFERRAL["reason"])]
    assert card["recommendations"] == []

    doctor_id = client.get("/api/auth/me", headers=auth(doctor_token)).json()["id"]
    [row] = audit_rows("referral.created")
    assert row.entity_id == ref["id"] and str(row.actor_id) == doctor_id and row.data == REFERRAL


def test_card_lists_referrals_from_rules_and_doctor(client, doctor_token, patient_token):
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    pid = patient_id(client, doctor_token)
    rec = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()["recommendations"][0]
    client.post(f"/api/doctor/recommendations/{rec['id']}/decision", json={"decision": "accepted"},
                headers=auth(doctor_token))
    client.post(f"/api/doctor/patients/{pid}/referrals", json=REFERRAL, headers=auth(doctor_token))

    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert {(x["to_specialty"], x["level"], x["recommendation_id"]) for x in card["referrals"]} == {
        ("psychiatrist", "mandatory", rec["id"]), ("psychotherapist", "desirable", None)}


def test_referral_checks(client, doctor_token, patient_token):
    pid = patient_id(client, doctor_token)
    url = f"/api/doctor/patients/{pid}/referrals"
    assert client.post(url, json=REFERRAL, headers=auth(other_doctor(client))).status_code == 404
    no_reason = {k: v for k, v in REFERRAL.items() if k != "reason"}
    assert client.post(url, json=no_reason, headers=auth(doctor_token)).status_code == 422
    assert client.post(url, json=REFERRAL | {"reason": "   "}, headers=auth(doctor_token)).status_code == 422
    assert client.post(url, json=REFERRAL | {"to_specialty": "surgeon"}, headers=auth(doctor_token)).status_code == 422
    assert client.post(url, json=REFERRAL | {"level": "urgent"}, headers=auth(doctor_token)).status_code == 422
    assert client.post(url, json=REFERRAL, headers=auth(patient_token)).status_code == 403
    assert client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()["referrals"] == []
    assert audit_rows("referral.created") == []
