import pytest

from app.config import get_settings
from app.kb import load_kb
from app.services.rules import evaluate
from app.services.scoring import ScoringError, score

KB = load_kb(get_settings().kb_dir)


def answers(n: int, value: int = 0, **override) -> dict[str, int]:
    return {f"item{i}": override.get(f"item{i}", value) for i in range(1, n + 1)}


@pytest.mark.parametrize("total,level", [(0, "minimal"), (4, "minimal"), (5, "mild"), (10, "moderate"),
                                         (15, "severe"), (21, "severe")])
def test_gad7_severity_bands(total, level):
    a = answers(7)
    for i in range(total):
        a[f"item{i % 7 + 1}"] += 1
    assert score(KB.scales["gad7"], a).severity == level


def test_scoring_rejects_incomplete_answers():
    with pytest.raises(ScoringError):
        score(KB.scales["phq9"], answers(8))


def fired(ctx: dict) -> set[str]:
    base = {sid: None for sid in KB.scales} | {"ae": {"serious_7d": 0, "any_7d": 0}, "pdc_7d": None,
                                              "days_since_report": None}
    return {r.id for r in evaluate(KB.rules.values(), base | ctx)}


def test_phq9_item9_fires_critical_rule():
    ctx = {"phq9": {**answers(9, item9=1), "total": 1, "n": 1, "delta_prev": 0, "mcid": 5}}
    assert "phq9_suicidal_ideation" in fired(ctx)


def test_no_data_fires_nothing():
    assert fired({}) == set()


def test_gad7_worsening_uses_mcid():
    gad = {"total": 12, "n": 2, "mcid": 4}
    assert "gad7_worsening" in fired({"gad7": {**gad, "delta_prev": 4}})
    assert "gad7_worsening" not in fired({"gad7": {**gad, "delta_prev": 3}})


def test_low_adherence():
    assert "low_adherence" in fired({"pdc_7d": 0.5})
    assert "low_adherence" not in fired({"pdc_7d": 1.0})
