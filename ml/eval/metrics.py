"""Метрики извлечения (техметрика №2 кейса): precision / recall / F1 по каждому полю.

Списочные поля сравниваются как множества нормализованных ключей, скалярные — на точное совпадение.
Диагнозы с кодом МКБ сравниваются по коду. Диагнозы без кода — по тексту, и текст засчитывается, если слова одной
формулировки входят в другую: «ГБ 2 ст» и «ГБ 2 ст, контролируемая, риск ССО 4» — один диагноз. Так эталон не
приходится подгонять под длину цитаты, которую выбрала модель.
TODO(Матвей): нечёткое сопоставление названий препаратов (МНН ↔ торговое название, опечатки).
"""

import re
from collections import defaultdict
from dataclasses import dataclass

from app.schemas import ExtractionResult


def _norm(s: str | None) -> str:
    return re.sub(r"[^\w\s.-]", "", (s or "").lower()).strip()


def _code(icd10: str | None, text: str) -> str:
    return _norm(icd10).upper() if icd10 else _norm(text)


def _same_text(a: str, b: str) -> bool:
    """Тексты диагнозов без кода: слова короткой формулировки входят в длинную."""
    wa, wb = set(a.split()), set(b.split())
    return bool(wa) and bool(wb) and (wa <= wb or wb <= wa)


def _matches(gold: set[str], pred: set[str], loose: bool) -> int:
    """Число совпавших ключей. loose — текстовые ключи (без кода, в нижнем регистре) сравниваются по словам."""
    tp = len(gold & pred)
    if not loose:
        return tp
    left = sorted(p for p in pred - gold if p != p.upper())
    for g in sorted(k for k in gold - pred if k != k.upper()):
        hit = next((p for p in left if _same_text(g, p)), None)
        if hit is not None:
            tp += 1
            left.remove(hit)
    return tp


KEYS = {
    "diagnoses": lambda r: {_code(d.icd10, d.text) for d in r.diagnoses},
    "comorbidities": lambda r: {_code(c.icd10, c.text) for c in r.comorbidities},
    "medications": lambda r: {_norm(m.name).split()[0] for m in r.medications if _norm(m.name)},
    "allergies": lambda r: {_norm(a.substance) for a in r.allergies},
    "scale_scores": lambda r: {(_norm(s.scale).replace(" ", ""), float(s.score)) for s in r.scale_scores},
    "risk_flags": lambda r: set(r.risk_flags),
}
LOOSE = ("diagnoses", "comorbidities")   # текст без кода — по словам, см. _same_text
SCALARS = ("age", "sex")


@dataclass
class FieldScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def compare(gold: ExtractionResult, pred: ExtractionResult) -> dict[str, FieldScore]:
    scores: dict[str, FieldScore] = {}
    for field, key in KEYS.items():
        g, p = key(gold), key(pred)
        tp = _matches(g, p, loose=field in LOOSE)
        scores[field] = FieldScore(tp=tp, fp=len(p) - tp, fn=len(g) - tp)
    for field in SCALARS:
        g, p = getattr(gold, field), getattr(pred, field)
        fs = FieldScore()
        if g is not None or p is not None:
            if g == p:
                fs.tp = 1
            else:
                fs.fp, fs.fn = int(p is not None), int(g is not None)
        scores[field] = fs
    return scores


def aggregate(per_doc: list[dict[str, FieldScore]]) -> dict[str, FieldScore]:
    total: dict[str, FieldScore] = defaultdict(FieldScore)
    for doc in per_doc:
        for field, fs in doc.items():
            t = total[field]
            t.tp, t.fp, t.fn = t.tp + fs.tp, t.fp + fs.fp, t.fn + fs.fn
    return dict(total)
