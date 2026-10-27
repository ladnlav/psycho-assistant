"""Анамнез, источники диагнозов и анализы: доступ, аудит, анализы в проверке назначения.
Препараты — вымышленные: данные Авиандра берутся только из ГРЛС."""

import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.kb import Drug, DrugCheck, KnowledgeBase, get_kb
from app.main import app
from app.models import AuditLog, User, utcnow
from app.scenarios import load_scenario, read_scenarios
from app.schemas import LabValue
from app.services.drug_checks import PatientFacts, check, patient_facts
from tests.conftest import auth

RENAL_DRUG = Drug(
    id="renaldrug", trade_name="Нефроцин", inn="нефроцин", registered_rf=True, status="draft",
    contraindications=[
        DrugCheck(id="renal", text_ru="Почечная недостаточность (СКФ < 60)",
                  when="dx('N18.3', 'N18.4') or lab('egfr') < 60", ask=True, labs=["creatinine"]),
        DrugCheck(id="hepatic", text_ru="Печёночная недостаточность", when="dx('K72')", ask=True,
                  labs=["bilirubin", "albumin", "inr"]),
        DrugCheck(id="egfr-only", text_ru="Тяжёлая почечная недостаточность", when="lab('egfr') < 30"),
    ],
    sources=["grls_aviandr"],
)
RX = {"drug_id": "renaldrug", "drug_name": "Нефроцин"}
KB = get_kb()


def egfr(value: float, taken_on: date = date(2026, 10, 20)) -> dict[str, LabValue]:
    return {"egfr": LabValue(analyte="egfr", title_ru="СКФ", unit="мл/мин/1,73 м²", value=value, taken_on=taken_on)}


def by_id(facts: PatientFacts):
    return {w.id: w for w in check(RENAL_DRUG, facts, kb=KB)}


@pytest.fixture()
def kb_with_renal_drug():
    kb = get_kb().model_copy(deep=True)
    kb.drugs["renaldrug"] = RENAL_DRUG
    app.dependency_overrides[get_kb] = lambda: kb
    yield kb
    app.dependency_overrides.pop(get_kb, None)


@pytest.fixture()
def pid(client, doctor_token, patient_token) -> str:
    return client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]


@pytest.fixture()
def other_doctor(client) -> str:
    return client.post("/api/auth/register/doctor", json={
        "email": "other@example.com", "password": "test-password", "full_name": "Другой врач"}).json()["access_token"]


def audit_entries(action: str) -> list[AuditLog]:
    with SessionLocal() as db:
        return db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)).all()


# --- анализы в проверке назначения ------------------------------------------------------------

def test_low_egfr_is_found_in_card_and_needs_reason():
    w = by_id(PatientFacts(labs=egfr(52)))["renal"]
    assert w.status == "fired" and w.requires_reason
    assert [(x.analyte, x.value) for x in w.labs] == [("egfr", 52), ("creatinine", None)], "СКФ из when, затем labs"


def test_normal_egfr_stays_manual_and_shows_value():
    w = by_id(PatientFacts(labs=egfr(95)))["renal"]
    assert w.status == "manual" and not w.requires_reason
    assert w.labs[0].value == 95 and w.labs[0].taken_on == date(2026, 10, 20)


def test_no_lab_result_stays_check_with_patient():
    warnings = by_id(PatientFacts())
    assert warnings["renal"].status == "manual", "анализа нет — «проверьте у пациента», как без lab()"
    assert [(x.analyte, x.title_ru, x.value) for x in warnings["renal"].labs] == [
        ("egfr", "СКФ", None), ("creatinine", "Креатинин", None)]
    assert "egfr-only" not in warnings, "без ask и без анализа пункт не показывается"
    assert by_id(PatientFacts(diagnoses=["N18.4"]))["renal"].status == "fired", "диагноз срабатывает без анализа"


def test_hepatic_shows_labs_without_computing_class():
    labs = {"bilirubin": LabValue(analyte="bilirubin", title_ru="Общий билирубин", unit="мкмоль/л", value=60)}
    w = by_id(PatientFacts(labs=labs))["hepatic"]
    assert w.status == "manual", "класс по Чайлд-Пью система не вычисляет"
    assert [(x.analyte, x.value) for x in w.labs] == [("bilirubin", 60), ("albumin", None), ("inr", None)]


def test_kb_rejects_bad_lab_references():
    with pytest.raises(ValidationError, match="lab\\(\\) принимает один id"):
        DrugCheck(id="x", text_ru="…", when="lab(age) < 60")
    kb = get_kb().model_dump()
    kb["drugs"] = {"d": Drug(id="d", trade_name="Д", inn="д", registered_rf=True, status="draft", contraindications=[
        DrugCheck(id="x", text_ru="…", when="lab('potassium') > 5")]).model_dump()}
    with pytest.raises(ValidationError, match="неизвестные анализы"):
        KnowledgeBase.model_validate(kb)


def test_prescription_check_reads_latest_lab_from_card(client, doctor_token, pid, kb_with_renal_drug):
    url = f"/api/doctor/patients/{pid}"
    statuses = lambda: {w["id"]: w for w in client.post(  # noqa: E731
        f"{url}/prescriptions/check", json=RX, headers=auth(doctor_token)).json()["warnings"]}
    assert statuses()["renal"]["status"] == "manual"

    lab = {"analyte": "egfr", "value": 48, "taken_on": "2026-10-20", "source": "lab"}
    r = client.post(f"{url}/labs", json=lab, headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    assert r.json()["unit"] == "мл/мин/1,73 м²", "единица — из kb/labs.yaml"
    renal = statuses()["renal"]
    assert renal["status"] == "fired" and renal["requires_reason"]
    assert (renal["labs"][0]["analyte"], renal["labs"][0]["value"]) == ("egfr", 48)

    # Исправление — новый результат с той же датой; более старый анализ не перебивает последний.
    client.post(f"{url}/labs", json=lab | {"value": 78}, headers=auth(doctor_token))
    client.post(f"{url}/labs", json=lab | {"value": 40, "taken_on": "2026-01-10"}, headers=auth(doctor_token))
    assert statuses()["renal"]["status"] == "manual"
    assert statuses()["renal"]["labs"][0]["value"] == 78


# --- анамнез и «Моя история» ------------------------------------------------------------------

def test_doctor_edits_anamnesis_and_patient_reads_it(client, doctor_token, patient_token, pid):
    body = {"complaints": "Тревога почти каждый день", "history": "  Около полугода  ", "notes": ""}
    r = client.put(f"/api/doctor/patients/{pid}/anamnesis", json=body, headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["history"] == "Около полугода" and a["notes"] is None
    assert a["updated_by_name"] == "Врач Тестовый" and a["updated_at"]

    mine = client.get("/api/patient/history", headers=auth(patient_token)).json()
    assert mine["anamnesis"]["complaints"] == "Тревога почти каждый день"
    assert mine["anamnesis"]["updated_by_name"] == "Врач Тестовый"
    assert [t["id"] for t in mine["lab_tests"]][:2] == ["creatinine", "egfr"]

    [entry] = audit_entries("anamnesis.updated")
    assert entry.entity_id == pid and entry.data == {"complaints": "Тревога почти каждый день",
                                                     "history": "Около полугода"}
    client.put(f"/api/doctor/patients/{pid}/anamnesis", json=body, headers=auth(doctor_token))
    assert len(audit_entries("anamnesis.updated")) == 1, "без изменений — без записи в журнал"
    client.put(f"/api/doctor/patients/{pid}/anamnesis", json=body | {"notes": "Аллергии нет"},
               headers=auth(doctor_token))
    assert audit_entries("anamnesis.updated")[-1].data == {"notes": "Аллергии нет"}, "в журнал — только изменённое"


def test_diagnosis_source_and_date(client, doctor_token, patient_token, pid):
    body = {"icd10": "n18.3 ", "title": "Хроническая болезнь почек, стадия 3а", "source": "discharge",
            "source_note": "выписка нефролога", "diagnosed_on": "2024-05-14"}
    r = client.post(f"/api/doctor/patients/{pid}/diagnoses", json=body, headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["icd10"], d["confirmed"], d["source"], d["diagnosed_on"]) == ("N18.3", True, "discharge", "2024-05-14")
    card = client.get(f"/api/doctor/patients/{pid}", headers=auth(doctor_token)).json()
    assert card["diagnoses"][0]["source_note"] == "выписка нефролога", "источник виден в карточке"
    assert client.get("/api/patient/history", headers=auth(patient_token)).json()["diagnoses"][0]["source"] == "discharge"

    other = {"source": "other"}
    assert client.patch(f"/api/doctor/diagnoses/{d['id']}", json=other, headers=auth(doctor_token)).status_code == 422
    r = client.patch(f"/api/doctor/diagnoses/{d['id']}", json=other | {"source_note": "карта из частной клиники"},
                     headers=auth(doctor_token))
    assert r.json()["source"] == "other" and r.json()["diagnosed_on"] is None

    assert audit_entries("diagnosis.created")[0].data["icd10"] == "N18.3"
    [changed] = audit_entries("diagnosis.source_updated")
    assert changed.data["before"]["source"] == "discharge" and changed.data["after"]["source"] == "other"


def test_lab_results_are_audited_and_validated(client, doctor_token, pid):
    url = f"/api/doctor/patients/{pid}/labs"
    lab = {"analyte": "alt", "value": 31, "taken_on": "2026-10-20", "source": "mis", "source_note": "МИС поликлиники"}
    lab_id = client.post(url, json=lab, headers=auth(doctor_token)).json()["id"]
    [entry] = audit_entries("lab_result.created")
    assert entry.entity_id == lab_id and entry.data["value"] == 31 and entry.data["unit"] == "Ед/л"
    assert client.post(url, json=lab | {"analyte": "potassium"}, headers=auth(doctor_token)).status_code == 422
    assert client.post(url, json=lab | {"value": -1}, headers=auth(doctor_token)).status_code == 422
    history = client.get(f"/api/doctor/patients/{pid}/history", headers=auth(doctor_token)).json()
    assert [(x["analyte"], x["value"], x["source"]) for x in history["labs"]] == [("alt", 31, "mis")]


def test_access_only_own_patient(client, doctor_token, patient_token, pid, other_doctor):
    lab = {"analyte": "egfr", "value": 50, "taken_on": "2026-10-20", "source": "lab"}
    dx = {"icd10": "I10", "title": "Гипертоническая болезнь", "source": "exam"}
    d_id = client.post(f"/api/doctor/patients/{pid}/diagnoses", json=dx, headers=auth(doctor_token)).json()["id"]
    calls = [
        ("get", f"/api/doctor/patients/{pid}/history", None),
        ("put", f"/api/doctor/patients/{pid}/anamnesis", {"complaints": "чужая запись"}),
        ("post", f"/api/doctor/patients/{pid}/diagnoses", dx),
        ("patch", f"/api/doctor/diagnoses/{d_id}", {"source": "mis"}),
        ("post", f"/api/doctor/patients/{pid}/labs", lab),
    ]
    for method, url, body in calls:
        assert client.request(method, url, json=body, headers=auth(other_doctor)).status_code == 404, url
        assert client.request(method, url, json=body, headers=auth(patient_token)).status_code == 403, url
    assert client.get("/api/patient/history", headers=auth(doctor_token)).status_code == 403
    assert client.patch(f"/api/doctor/diagnoses/{uuid.uuid4()}", json={"source": "mis"},
                        headers=auth(doctor_token)).status_code == 404

    # Другой пациент того же врача не видит чужую историю: «Моя история» — всегда о себе.
    code = client.post("/api/doctor/invites", json={}, headers=auth(doctor_token)).json()["code"]
    second = client.post("/api/auth/register/patient", json={
        "email": "pat2@example.com", "password": "test-password", "full_name": "Второй пациент",
        "invite_code": code, "consent_pd": True}).json()["access_token"]
    assert client.get("/api/patient/history", headers=auth(second)).json()["diagnoses"] == []


# --- сценарии -------------------------------------------------------------------------------

def test_scenario_4_low_egfr_found_in_card(client, doctor_token):
    """Сценарий 4 (ХБП С3а): СКФ 45–59 в карточке — противопоказание по анализу находится и без кода ХБП."""
    sc = read_scenarios(get_settings().scenarios_dir)["s4"]
    today = utcnow().date()
    with SessionLocal() as db:
        doctor = db.scalar(select(User).where(User.email == "doc@example.com"))
        pid = load_scenario(db, KB, sc, doctor, "test-password", today).id
        db.commit()
        facts = patient_facts(db, KB, pid)
    assert 45 <= facts.labs["egfr"].value <= 59 and facts.labs["egfr"].taken_on == today - timedelta(days=10)
    assert "creatinine" in facts.labs
    facts.diagnoses = []  # проверяем именно анализ
    assert by_id(facts)["renal"].status == "fired"

    history = client.get(f"/api/doctor/patients/{pid}/history", headers=auth(doctor_token)).json()
    assert history["anamnesis"]["complaints"] and history["anamnesis"]["updated_by_name"]
    ckd = next(d for d in history["diagnoses"] if d["icd10"] == "N18.3")
    assert ckd["source"] == "discharge" and ckd["diagnosed_on"]


def test_repo_scenarios_use_known_labs():
    for sc in read_scenarios(get_settings().scenarios_dir).values():
        assert {lab.analyte for lab in sc.labs} <= KB.labs.keys(), sc.id
        assert sc.anamnesis and sc.anamnesis.complaints, f"{sc.id}: жалобы в анамнезе"
        assert all(d.source for d in sc.diagnoses), f"{sc.id}: у каждого диагноза указан источник"
