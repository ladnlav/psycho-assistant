from app.schemas import Condition, Diagnosis, ExtractionResult
from eval.metrics import compare


def _dx(*items: tuple[str | None, str]) -> ExtractionResult:
    return ExtractionResult(diagnoses=[Diagnosis(icd10=code, text=text) for code, text in items])


def test_text_without_code_matches_longer_quote():
    gold = ExtractionResult(comorbidities=[Condition(text="ГБ 2 ст")])
    pred = ExtractionResult(comorbidities=[Condition(text="ГБ 2 ст, контролируемая, риск ссо4")])
    s = compare(gold, pred)["comorbidities"]
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_codes_compare_exactly():
    s = compare(_dx(("F41.1", "ГТР")), _dx(("F41", "ГТР")))["diagnoses"]
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_different_texts_do_not_match():
    s = compare(_dx((None, "астено-невротический синдром")), _dx((None, "невротический синдром тревоги")))["diagnoses"]
    assert s.tp == 0


def test_one_prediction_matches_one_gold_item():
    gold = _dx((None, "мигрень"), (None, "мигрень с аурой"))
    s = compare(gold, _dx((None, "мигрень")))["diagnoses"]
    assert (s.tp, s.fp, s.fn) == (1, 0, 1)
