"""PHQ-4 — шкала, добавленная одним файлом kb/scales/phq4.yaml: раз в неделю, подшкалы тревоги и депрессии."""

from datetime import timedelta

import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.kb import get_kb, load_kb
from app.models import utcnow
from app.services.context import build_context
from app.services.scoring import score
from tests.conftest import auth
from tests.test_no_reports import patient_id

KB = load_kb(get_settings().kb_dir)


def test_phq4_weekly_with_two_subscales():
    s = KB.scales["phq4"]
    assert s.rater == "patient" and s.schedule_days == 7
    assert [i.id for i in s.items] == ["item1", "item2", "item3", "item4"]
    assert all(i.text_ru for i in s.items) and s.instruction_ru
    assert {sub.id: (sub.items, sub.positive_min) for sub in s.subscales} == {
        "anxiety": (["item1", "item2"], 3), "depression": (["item3", "item4"], 3)}
    assert s.license.type == "free" and s.validation_ru.source == "zolotareva2024_phq4_ru"


@pytest.mark.parametrize("total,level", [(0, "normal"), (2, "normal"), (3, "mild"), (5, "mild"), (6, "moderate"),
                                         (8, "moderate"), (9, "severe"), (12, "severe")])
def test_phq4_total_bands(total, level):
    a = {f"item{i}": 0 for i in range(1, 5)}
    for i in range(total):
        a[f"item{i % 4 + 1}"] += 1
    assert score(KB.scales["phq4"], a).severity == level


def test_patient_gets_phq4_weekly_and_rules_see_subscales(client, doctor_token, patient_token):
    h = auth(patient_token)
    assert "phq4" in [s["id"] for s in client.get("/api/patient/scales", headers=h).json()]
    due = {s["scale_id"]: s for s in client.get("/api/patient/scales/schedule", headers=h).json()}
    assert due["phq4"]["due"], "первый раз — сразу"

    r = client.post("/api/patient/scales/phq4", json={"answers": {"item1": 2, "item2": 1, "item3": 1, "item4": 0}},
                    headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["total"] == 4 and r.json()["severity_label_ru"] == "лёгкий дистресс"
    due = {s["scale_id"]: s for s in client.get("/api/patient/scales/schedule", headers=h).json()}
    assert not due["phq4"]["due"] and due["phq4"]["next_due"] == str(utcnow().date() + timedelta(days=7))

    with SessionLocal() as db:
        ctx = build_context(db, get_kb(), patient_id(client, doctor_token))
    assert (ctx["phq4"]["anxiety"], ctx["phq4"]["depression"]) == (3, 1)
