import warnings

import pytest

from app.config import get_settings
from app.kb import Scale, load_kb


def test_kb_loads_and_references_resolve():
    kb = load_kb(get_settings().kb_dir)
    assert {"gad7", "phq9"} <= kb.scales.keys()
    assert "aviandr" in kb.drugs
    assert kb.rules


def test_kb_reports_unvalidated_content():
    """Не падает, но напоминает, что до демо всё должно быть validated и переведено."""
    kb = load_kb(get_settings().kb_dir)
    todo = [f"{k}:{e.id}" for k, d in (("scale", kb.scales), ("rule", kb.rules), ("drug", kb.drugs))
            for e in d.values() if e.status != "validated"]
    no_ru = [s.id for s in kb.scales.values() if any(i.text_ru is None for i in s.items)]
    if todo or no_ru:
        warnings.warn(f"draft: {todo}; нет русского текста: {no_ru}", stacklevel=1)


def _scale(**over):
    base = {
        "id": "x", "name": "X", "title_ru": "X", "rater": "patient", "status": "draft",
        "instruction_en": "i", "options": [{"value": 0, "label_en": "a"}, {"value": 1, "label_en": "b"}],
        "items": [{"id": "item1", "text_en": "q"}, {"id": "item2", "text_en": "q"}],
        "severity": [{"min": 0, "max": 1, "level": "low", "label_ru": "н"},
                     {"min": 2, "max": 2, "level": "high", "label_ru": "в"}],
        "license": {"type": "free"}, "validation_ru": {"status": "todo"},
    }
    return {**base, **over}


def test_licensed_scale_without_permission_rejected():
    with pytest.raises(ValueError, match="лицензируемая"):
        Scale.model_validate(_scale(license={"type": "licensed", "holder": "GL Assessment"}))


def test_severity_bands_must_cover_range():
    with pytest.raises(ValueError, match="без разрывов"):
        Scale.model_validate(_scale(severity=[{"min": 0, "max": 0, "level": "a", "label_ru": "a"},
                                              {"min": 2, "max": 2, "level": "b", "label_ru": "b"}]))
