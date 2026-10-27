"""Проверка назначения по инструкции. Препарат — вымышленный: данные Авиандра берутся только из ГРЛС."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.db import SessionLocal
from app.kb import Drug, DrugCheck, get_kb
from app.main import app
from app.models import AuditLog, Diagnosis
from app.services.drug_checks import PatientFacts, check, dosing
from tests.conftest import auth

TEST_DRUG = Drug(
    id="testdrug", trade_name="Тестоцин", inn="тестоцин", registered_rf=True, status="draft",
    contraindications=[
        DrugCheck(id="pregnancy", text_ru="Беременность", when="dx('O', 'Z33')"),
        DrugCheck(id="children", text_ru="Возраст до 18 лет", when="age < 18"),
        DrugCheck(id="hypersensitivity", text_ru="Повышенная чувствительность к компонентам",
                  check_ru="аллергологический анамнез"),
    ],
    caution=[DrugCheck(id="elderly", text_ru="Возраст старше 65 лет", when="age >= 65")],
    interactions=[DrugCheck(id="maoi", text_ru="Ингибиторы МАО", when="taking('моклобемид')",
                            severity="contraindicated")],
    sources=["grls_aviandr", "sponsor_deck_aviandr"],
)
RX = {"drug_id": "testdrug", "drug_name": "Тестоцин"}


def statuses(facts: PatientFacts) -> dict[str, str]:
    return {w.id: w.status for w in check(TEST_DRUG, facts)}


def test_manual_items_always_shown():
    assert statuses(PatientFacts(age=30, sex="female")) == {"hypersensitivity": "manual"}


def test_what_to_check_reaches_doctor():
    [w] = check(TEST_DRUG, PatientFacts(age=30, sex="female"))
    assert w.check_ru == "аллергологический анамнез"


def test_findings_from_card_come_first_and_need_reason():
    warnings = check(TEST_DRUG, PatientFacts(age=30, diagnoses=["Z33"], medications=["моклобемид 150 мг"]))
    assert [w.id for w in warnings] == ["pregnancy", "maoi", "hypersensitivity"]
    assert [w.requires_reason for w in warnings] == [True, True, False]


def test_missing_data_goes_to_doctor():
    warnings = {w.id: w for w in check(TEST_DRUG, PatientFacts(age=None))}
    assert warnings["children"].status == warnings["elderly"].status == "unchecked"
    assert warnings["children"].detail_ru == "нет даты рождения"


def test_kb_rejects_bad_checks():
    with pytest.raises(ValidationError, match="неизвестные имена"):
        DrugCheck(id="weight", text_ru="Масса тела", when="weight > 100")
    with pytest.raises(ValidationError, match="severity"):
        Drug(id="x", trade_name="X", inn="x", registered_rf=True, status="draft",
             interactions=[DrugCheck(id="i", text_ru="…", when="taking('y')")])


@pytest.fixture()
def kb_with_testdrug():
    kb = get_kb().model_copy(deep=True)
    kb.drugs["testdrug"] = TEST_DRUG
    app.dependency_overrides[get_kb] = lambda: kb
    yield kb
    app.dependency_overrides.pop(get_kb, None)


def test_prescription_needs_acknowledgement_and_reason(client, doctor_token, patient_token, kb_with_testdrug):
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    with SessionLocal() as db:
        db.add(Diagnosis(patient_id=uuid.UUID(pid), icd10="Z33", title="Беременное состояние"))
        db.commit()
    url = f"/api/doctor/patients/{pid}/prescriptions"

    result = client.post(url + "/check", json=RX, headers=auth(doctor_token)).json()
    assert result["checked"] is True
    ids = [w["id"] for w in result["warnings"]]
    assert ids[0] == "pregnancy" and "hypersensitivity" in ids
    assert result["warnings"][0]["sources"] == ["grls_aviandr"], "пункт цитирует только инструкцию"

    assert client.post(url, json=RX, headers=auth(doctor_token)).status_code == 409, "сначала врач учитывает пункты"
    acked = RX | {"acknowledged_warnings": ids}
    assert client.post(url, json=acked, headers=auth(doctor_token)).status_code == 422, "противопоказание — с обоснованием"
    r = client.post(url, json=acked | {"override_note": "Беременность исключена, Z33 внесён ошибочно"},
                    headers=auth(doctor_token))
    assert r.status_code == 200, r.text

    with SessionLocal() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "prescription.created"))
    assert entry.data["override_note"].startswith("Беременность исключена")
    assert {"id": "pregnancy", "kind": "contraindication", "status": "fired"} in entry.data["warnings"]


def test_drug_without_instruction_data_says_so(client, doctor_token, patient_token, kb_with_testdrug):
    kb_with_testdrug.drugs["emptydrug"] = Drug(id="emptydrug", trade_name="Пустоцин", inn="пустоцин",
                                               registered_rf=True, status="draft")
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    result = client.post(f"/api/doctor/patients/{pid}/prescriptions/check",
                         json={"drug_id": "emptydrug", "drug_name": "Пустоцин"}, headers=auth(doctor_token)).json()
    assert result["checked"] is False and "ГРЛС" in result["notice_ru"]
    assert result["dosing"] is None, "без раздела dosing форма назначения остаётся пустой"


def test_check_returns_dosing_for_form(client, doctor_token, patient_token, kb_with_testdrug):
    """Доза и кратность по умолчанию приходят из kb/drugs (dosing), а не зашиты во фронтенде."""
    kb_with_testdrug.drugs["testdrug"] = TEST_DRUG.model_copy(update={"dosing": {
        "single_mg": 20, "times_per_day": 2, "schedule_ru": "по 1 таблетке 2 раза в сутки"}})
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    result = client.post(f"/api/doctor/patients/{pid}/prescriptions/check", json=RX,
                         headers=auth(doctor_token)).json()
    assert result["dosing"] == {"single_mg": 20, "times_per_day": 2, "frequency_ru": "2 раза в сутки",
                                "schedule_ru": "по 1 таблетке 2 раза в сутки"}


def test_dosing_frequency_wording():
    def freq(n: int) -> str:
        return dosing(Drug(id="d", trade_name="Д", inn="д", registered_rf=True, status="draft",
                           dosing={"single_mg": 10, "times_per_day": n})).frequency_ru
    assert [freq(n) for n in (1, 2, 3, 5, 12, 22)] == [
        "1 раз в сутки", "2 раза в сутки", "3 раза в сутки", "5 раз в сутки", "12 раз в сутки", "22 раза в сутки"]


def test_aviandr_dosing_reaches_form():
    """Значения — из инструкции ГРЛС (их сверяет Савва), здесь проверяем только, что форма их получит."""
    assert dosing(get_kb().drugs["aviandr"]) is not None


def test_ask_shows_item_when_card_has_nothing():
    drug = Drug(id="d", trade_name="Д", inn="д", registered_rf=True, status="draft", contraindications=[
        DrugCheck(id="renal", text_ru="Почечная недостаточность", when="dx('N18.4')", ask=True),
        DrugCheck(id="pregnancy", text_ru="Беременность", when="dx('Z33')", ask="sex == 'female'"),
    ])
    shown = lambda facts: {w.id: w.status for w in check(drug, facts)}
    assert shown(PatientFacts(sex="male")) == {"renal": "manual"}, "мужчину о беременности не спрашиваем"
    assert shown(PatientFacts(sex="female")) == {"renal": "manual", "pregnancy": "manual"}
    assert shown(PatientFacts(sex=None))["pregnancy"] == "manual", "пол неизвестен — лучше спросить"
    assert shown(PatientFacts(sex="female", diagnoses=["Z33"]))["pregnancy"] == "fired"
