from pathlib import Path

from app.schemas import ExtractionResult
from app.triage import triage_keywords
from eval.metrics import compare

GOLD = ExtractionResult.model_validate_json(
    (Path(__file__).parents[1] / "eval" / "gold" / "example_001.json").read_text(encoding="utf-8"))


def test_perfect_prediction_scores_one():
    scores = compare(GOLD, GOLD)
    assert all(s.f1 == 1.0 for s in scores.values())


def test_missing_and_extra_facts_are_counted():
    pred = GOLD.model_copy(update={"medications": [], "risk_flags": ["suicidal_ideation"]})
    scores = compare(GOLD, pred)
    assert scores["medications"].recall == 0.0
    assert scores["risk_flags"].precision == 0.0


def test_medication_name_normalized():
    pred = GOLD.model_copy(update={"medications": [GOLD.medications[0].model_copy(update={"name": "Лозартан 50мг"})]})
    assert compare(GOLD, pred)["medications"].f1 == 1.0


def test_triage_detects_suicidal_message():
    r = triage_keywords("Доктор, мне очень плохо, иногда думаю, что не хочу жить")
    assert r.level == "critical" and "suicidal_ideation" in r.categories


def test_triage_side_effect_is_attention():
    r = triage_keywords("После таблетки небольшая тошнота")
    assert r.level == "attention"


def test_triage_neutral_message():
    assert triage_keywords("Всё хорошо, спасибо").level == "none"
