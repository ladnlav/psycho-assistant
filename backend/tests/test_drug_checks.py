"""Проверка назначения по инструкции. Препарат — вымышленный: данные Авиандра берутся только из ГРЛС."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.db import SessionLocal
from app.kb import OFF_LABEL_ID, Drug, DrugCheck, Indication, get_kb
from app.main import app
from app.models import AuditLog, Diagnosis, Prescription
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
# Показания вымышленные: одно из одного кода, другое — из двух кодов, которые должны быть в карточке вместе.
INDICATED_DRUG = TEST_DRUG.model_copy(update={"indications": [
    Indication(icd10="F41.1", text="Тревожное расстройство"),
    Indication(icd10=["F43.2", "U09.9"], text="Расстройство адаптации после перенесённой инфекции"),
]})


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


def test_dx_matches_code_prefixes():
    """Префиксы МКБ-10, как в пунктах об органических заболеваниях мозга: 'I6' — I60–I69, 'F0' — вместе с F07.2."""
    drug = Drug(id="prefixdrug", trade_name="Префиксин", inn="префиксин", registered_rf=True, status="draft",
                contraindications=[DrugCheck(id="brain", text_ru="Органическое заболевание",
                                             when="dx('I6', 'F0', 'G0', 'G10', 'G93.1', 'Q04')")])

    def fired(code: str) -> bool:
        return [w.status for w in check(drug, PatientFacts(diagnoses=[code]))] == ["fired"]

    assert all(fired(c) for c in ["I63.5", "F07.2", "g06", "G10", "G93.1", "Q04.3"])
    assert not any(fired(c) for c in ["I70", "G11.1", "G93.2", "Q05", "F10.2"])


def test_kb_rejects_bad_checks():
    with pytest.raises(ValidationError, match="неизвестные имена"):
        DrugCheck(id="weight", text_ru="Масса тела", when="weight > 100")
    with pytest.raises(ValidationError, match="severity"):
        Drug(id="x", trade_name="X", inn="x", registered_rf=True, status="draft",
             interactions=[DrugCheck(id="i", text_ru="…", when="taking('y')")])
    with pytest.raises(ValidationError, match="at least 1"):
        Indication(icd10=[], text="Показание без кодов подтверждалось бы всегда")
    with pytest.raises(ValidationError, match="вне показаний"):
        Drug(id="x", trade_name="X", inn="x", registered_rf=True, status="draft",
             caution=[DrugCheck(id=OFF_LABEL_ID, text_ru="…")])


# --- показания ----------------------------------------------------------------------------------

def off_label(diagnoses: list[str], drug: Drug = INDICATED_DRUG):
    return next((w for w in check(drug, PatientFacts(age=30, diagnoses=diagnoses)) if w.id == OFF_LABEL_ID), None)


def test_off_label_when_no_indication_in_card():
    w = off_label(["F32.1", "I10"])
    assert (w.kind, w.status, w.requires_reason) == ("off_label", "fired", False), "уровень «с осторожностью»"
    assert w.text_ru == "Назначение вне зарегистрированных показаний"
    assert w.detail_ru == "в карточке F32.1, I10"
    assert [(i.text_ru, i.icd10) for i in w.indications] == [
        ("Тревожное расстройство", ["F41.1"]),
        ("Расстройство адаптации после перенесённой инфекции", ["F43.2", "U09.9"])], "показания — из kb, как есть"
    assert w.sources == INDICATED_DRUG.sources

    empty = off_label([])
    assert (empty.status, empty.detail_ru) == ("unchecked", "диагнозы не внесены")


def test_indication_in_card_means_no_off_label():
    assert off_label(["f41.1"]) is None, "сравнение по префиксу и без учёта регистра, как dx()"
    assert off_label(["I10", "F41.1"]) is None
    assert off_label(["F32.1"], drug=TEST_DRUG) is None, "показаний в kb нет — проверки нет"


def test_two_code_indication_needs_both_codes():
    assert off_label(["F43.2"]) is not None
    assert off_label(["U09.9"]) is not None
    assert off_label(["U09.9", "F43.22"]) is None


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


def test_off_label_is_acknowledged_without_reason(client, doctor_token, patient_token, kb_with_testdrug):
    kb_with_testdrug.drugs["testdrug"] = INDICATED_DRUG
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    with SessionLocal() as db:
        db.add(Diagnosis(patient_id=uuid.UUID(pid), icd10="F32.1", title="Депрессивный эпизод средней степени"))
        db.commit()
    url = f"/api/doctor/patients/{pid}/prescriptions"

    warnings = client.post(url + "/check", json=RX, headers=auth(doctor_token)).json()["warnings"]
    w = warnings[0]
    assert (w["id"], w["kind"], w["status"]) == (OFF_LABEL_ID, "off_label", "fired")
    assert w["sources"] == ["grls_aviandr"] and w["indications"][1]["icd10"] == ["F43.2", "U09.9"]

    others = [x["id"] for x in warnings if x["id"] != OFF_LABEL_ID]
    assert client.post(url, json=RX | {"acknowledged_warnings": others},
                       headers=auth(doctor_token)).status_code == 409, "пункт «вне показаний» врач отмечает"
    r = client.post(url, json=RX | {"acknowledged_warnings": [x["id"] for x in warnings]}, headers=auth(doctor_token))
    assert r.status_code == 200, "обоснование не нужно: " + r.text
    with SessionLocal() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "prescription.created"))
    assert {"id": OFF_LABEL_ID, "kind": "off_label", "status": "fired"} in entry.data["warnings"]


def test_second_active_prescription_is_rejected(client, doctor_token, patient_token, kb_with_testdrug):
    pid = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]
    url = f"/api/doctor/patients/{pid}/prescriptions"

    def prescribe():
        result = client.post(url + "/check", json=RX, headers=auth(doctor_token)).json()
        acked = RX | {"acknowledged_warnings": [w["id"] for w in result["warnings"]]}
        return result, client.post(url, json=acked, headers=auth(doctor_token))

    result, first = prescribe()
    assert result["already_prescribed"] is None and first.status_code == 200, first.text

    result, again = prescribe()
    assert result["already_prescribed"]["id"] == first.json()["id"], "проверка сразу говорит, что препарат назначен"
    assert result["warnings"] == [] and "уже назначен с" in result["notice_ru"]
    assert again.status_code == 409 and "уже назначен" in again.json()["detail"]
    with SessionLocal() as db:
        assert len(db.scalars(select(Prescription).where(Prescription.drug_id == "testdrug")).all()) == 1

    kb_with_testdrug.drugs["otherdrug"] = TEST_DRUG.model_copy(update={"id": "otherdrug", "trade_name": "Другоцин"})
    other = client.post(url + "/check", json={"drug_id": "otherdrug", "drug_name": "Другоцин"},
                        headers=auth(doctor_token))
    assert other.json()["already_prescribed"] is None, "другой препарат назначению не мешает"

    assert client.post(f"/api/doctor/prescriptions/{first.json()['id']}/stop",
                       headers=auth(doctor_token)).status_code == 200
    result, renewed = prescribe()
    assert result["already_prescribed"] is None and result["warnings"], "после отмены — снова обычная проверка"
    assert renewed.status_code == 200, renewed.text


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
    """Значения — из инструкции ГРЛС (их сверяет врач команды), здесь проверяем только, что форма их получит."""
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
