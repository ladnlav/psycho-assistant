import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@event.listens_for(engine, "connect")
def _foreign_keys(dbapi_connection, _record):
    """SQLite по умолчанию не проверяет внешние ключи, а Postgres проверяет."""
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def doctor_token(client) -> str:
    r = client.post("/api/auth/register/doctor", json={
        "email": "doc@example.com", "password": "test-password", "full_name": "Врач Тестовый"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def patient_token(client, doctor_token) -> str:
    code = client.post("/api/doctor/invites", json={}, headers=auth(doctor_token)).json()["code"]
    r = client.post("/api/auth/register/patient", json={
        "email": "pat@example.com", "password": "test-password", "full_name": "Пациент Тестовый",
        "invite_code": code, "consent_pd": True})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
