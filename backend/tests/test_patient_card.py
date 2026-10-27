"""Карточка пациента у врача: диагнозы видны своему врачу и не видны чужому."""

import uuid

from app.db import SessionLocal
from app.models import Diagnosis
from tests.conftest import auth


def test_card_shows_diagnoses_to_own_doctor_only(client, doctor_token, patient_token):
    doctor_id = client.get("/api/auth/me", headers=auth(doctor_token)).json()["id"]
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    with SessionLocal() as db:
        db.add(Diagnosis(patient_id=uuid.UUID(pid), icd10="F41.1", title="Генерализованное тревожное расстройство",
                         confirmed_by=uuid.UUID(doctor_id)))
        db.add(Diagnosis(patient_id=uuid.UUID(pid), icd10="I10", title="Эссенциальная гипертензия"))
        db.commit()

    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert {(d["icd10"], d["title"], d["confirmed"]) for d in card["diagnoses"]} == {
        ("F41.1", "Генерализованное тревожное расстройство", True),
        ("I10", "Эссенциальная гипертензия", False),
    }

    other = client.post("/api/auth/register/doctor", json={
        "email": "other@example.com", "password": "test-password", "full_name": "Другой врач"}).json()["access_token"]
    assert client.get(f"/api/doctor/patients/{pid}", headers=auth(other)).status_code == 404


def test_patient_list_shows_diagnoses(client, doctor_token, patient_token):
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    with SessionLocal() as db:
        db.add(Diagnosis(patient_id=uuid.UUID(pid), icd10="F41.1", title="Генерализованное тревожное расстройство"))
        db.commit()
    [patient] = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()
    assert [(d["icd10"], d["title"]) for d in patient["diagnoses"]] == [
        ("F41.1", "Генерализованное тревожное расстройство")]


def test_card_without_diagnoses(client, doctor_token, patient_token):
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    assert client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()["diagnoses"] == []


def test_card_view_is_audited_once_per_window(client, doctor_token, patient_token):
    """Карточка опрашивается раз в 10 с — журнал аудита не должен расти на каждый опрос."""
    from sqlalchemy import func, select

    from app.models import AuditLog
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    for _ in range(3):
        assert client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).status_code == 200
    with SessionLocal() as db:
        views = db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "patient_card.viewed", AuditLog.entity_id == pid))
    assert views == 1
