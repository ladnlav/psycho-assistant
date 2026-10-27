"""Апробация 27.10: к психиатру направление предлагают несколько правил, и открытые предложения копились.

Теперь к каждому специалисту не больше одного открытого предложения, а после направления остальные закрыты.
"""

import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Alert, AuditLog, Recommendation
from app.services.referrals import ALREADY_REFERRED, REPLACED_BY_MANDATORY
from tests.conftest import auth
from tests.test_flow import PHQ9_ITEM9, ack_all, proposed

PHQ9_SEVERE = {f"item{i}": 3 for i in range(1, 10)}  # 27 баллов и п. 9: phq9_severe и phq9_suicidal_ideation
GAD7_SEVERE = {f"item{i}": 3 for i in range(1, 8)}  # 21 балл: gad7_severe, «желательно» к психиатру
RISKY = "Доктор, иногда хочу умереть"


def card(client, doctor_token) -> dict:
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    return client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()


def statuses(client, doctor_token) -> list[tuple[str, str, str]]:
    return sorted((r["rule_id"], r["payload"]["level"], r["status"])
                  for r in card(client, doctor_token)["recommendations"])


def superseded_audit() -> list[AuditLog]:
    with SessionLocal() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == "recommendation.superseded")))


def no_proposal(rule_id: str) -> list[dict]:
    with SessionLocal() as db:
        alert = db.scalars(select(Alert).where(Alert.rule_id == rule_id)
                           .order_by(Alert.created_at.desc())).first()
        return alert.details.get("no_proposal", [])


def test_two_rules_to_psychiatrist_give_one_proposal(client, doctor_token, patient_token):
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_SEVERE}, headers=auth(patient_token))
    client.post("/api/patient/messages", json={"body": RISKY}, headers=auth(patient_token))

    alerts = {a["rule_id"] for a in client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()}
    assert alerts == {"phq9_severe", "phq9_suicidal_ideation", "free_text_risk"}, "алерты — как обычно"
    [rec] = proposed(client, doctor_token)
    assert (rec["payload"]["to"], rec["payload"]["level"]) == ("psychiatrist", "mandatory")
    assert no_proposal("free_text_risk") == [{"to": "psychiatrist", "reason": "proposed"}]


def test_mandatory_replaces_open_desirable(client, doctor_token, patient_token):
    client.post("/api/patient/scales/gad7", json={"answers": GAD7_SEVERE}, headers=auth(patient_token))
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))

    assert statuses(client, doctor_token) == [("gad7_severe", "desirable", "superseded"),
                                              ("phq9_suicidal_ideation", "mandatory", "proposed")]
    desirable = next(r for r in card(client, doctor_token)["recommendations"] if r["status"] == "superseded")
    assert desirable["decision_note"] == REPLACED_BY_MANDATORY
    [row] = superseded_audit()
    assert row.entity_id == desirable["id"] and row.actor_id is None, "закрыла система, а не врач"

    ack_all(client, doctor_token)  # новая тревога: алерт есть, «желательно» при «обязательно» — нет
    client.post("/api/patient/scales/gad7", json={"answers": GAD7_SEVERE}, headers=auth(patient_token))
    assert [a["rule_id"] for a in client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()] == [
        "gad7_severe"]
    assert [r["rule_id"] for r in proposed(client, doctor_token)] == ["phq9_suicidal_ideation"]


def test_accepting_closes_other_proposals(client, doctor_token, patient_token):
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    pid = card(client, doctor_token)["id"]
    with SessionLocal() as db:  # дубль из данных до исправления
        old = Recommendation(patient_id=uuid.UUID(pid), kind="referral", title="Направить к психиатру",
                             payload={"to": "psychiatrist", "level": "desirable", "reason_ru": "…"},
                             rule_id="gad7_severe")
        db.add(old)
        db.commit()
    [rec] = [r for r in proposed(client, doctor_token) if r["rule_id"] == "phq9_suicidal_ideation"]

    r = client.post(f"/api/doctor/recommendations/{rec['id']}/decision", json={"decision": "accepted"},
                    headers=auth(doctor_token))
    assert r.json()["status"] == "accepted"
    assert statuses(client, doctor_token) == [("gad7_severe", "desirable", "superseded"),
                                              ("phq9_suicidal_ideation", "mandatory", "accepted")]
    doctor_id = client.get("/api/auth/me", headers=auth(doctor_token)).json()["id"]
    [row] = superseded_audit()
    assert row.entity_id == str(old.id) and str(row.actor_id) == doctor_id
    assert row.data == {"to": "psychiatrist", "reason": ALREADY_REFERRED}
    closed = client.post(f"/api/doctor/recommendations/{old.id}/decision", json={"decision": "accepted"},
                         headers=auth(doctor_token))
    assert closed.status_code == 409, "закрытое предложение уже не принять"
    assert len(card(client, doctor_token)["referrals"]) == 1


def test_manual_referral_closes_proposals_to_same_specialist(client, doctor_token, patient_token):
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    pid = card(client, doctor_token)["id"]
    url = f"/api/doctor/patients/{pid}/referrals"
    client.post(url, json={"to_specialty": "psychotherapist", "level": "desirable", "reason": "КПТ"},
                headers=auth(doctor_token))
    assert len(proposed(client, doctor_token)) == 1, "к психотерапевту — не к психиатру"

    client.post(url, json={"to_specialty": "psychiatrist", "level": "mandatory", "reason": "Риск"},
                headers=auth(doctor_token))
    [rec] = card(client, doctor_token)["recommendations"]
    assert rec["status"] == "superseded" and rec["decision_note"] == ALREADY_REFERRED
    [row] = superseded_audit()
    assert row.entity_id == rec["id"] and row.actor_id is not None


def test_after_referral_rule_alerts_without_proposal(client, doctor_token, patient_token):
    client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    [rec] = proposed(client, doctor_token)
    client.post(f"/api/doctor/recommendations/{rec['id']}/decision", json={"decision": "accepted"},
                headers=auth(doctor_token))
    ack_all(client, doctor_token)

    r = client.post("/api/patient/scales/phq9", json={"answers": PHQ9_ITEM9}, headers=auth(patient_token))
    assert r.json()["safety"] is not None
    alerts = client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()
    assert [a["rule_id"] for a in alerts] == ["phq9_suicidal_ideation"], "алерт есть"
    assert proposed(client, doctor_token) == [], "а предложения нет: пациент уже направлен"
    assert no_proposal("phq9_suicidal_ideation") == [{"to": "psychiatrist", "reason": "referred"}]
