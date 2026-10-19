from dataclasses import dataclass

from app.kb import Scale


class ScoringError(ValueError):
    pass


@dataclass
class ScoreResult:
    total: int
    severity: str
    severity_label_ru: str


def score(scale: Scale, answers: dict[str, int]) -> ScoreResult:
    item_ids = {item.id for item in scale.items}
    allowed = {o.value for o in scale.options}
    missing = item_ids - answers.keys()
    extra = answers.keys() - item_ids
    if missing or extra:
        raise ScoringError(f"Ответы не совпадают с пунктами шкалы: нет {sorted(missing)}, лишние {sorted(extra)}")
    bad = {k: v for k, v in answers.items() if v not in allowed}
    if bad:
        raise ScoringError(f"Недопустимые значения: {bad}")

    total = sum(answers.values())
    band = next(b for b in scale.severity if b.min <= total <= b.max)
    return ScoreResult(total=total, severity=band.level, severity_label_ru=band.label_ru)
