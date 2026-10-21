"""Движок правил: безопасное вычисление выражений `when` из kb/rules над контекстом пациента."""

import ast
import logging
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from simpleeval import SimpleEval

from app.kb import Rule

log = logging.getLogger(__name__)

# Служебный ключ в пространстве имён шкалы: id последнего результата. Из `when` он недоступен
# (simpleeval не пускает к именам с «_»), зато по нему отпечаток отличает новый результат от старого.
RECORD = "_record"


def evaluate(rules: Iterable[Rule], context: dict[str, Any]) -> list[Rule]:
    """Возвращает сработавшие правила. Если данных для правила нет — оно не срабатывает."""
    evaluator = SimpleEval(names=context)
    fired = []
    for rule in rules:
        try:
            if evaluator.eval(rule.when) is True:
                fired.append(rule)
        except Exception as e:  # нет данных (None), отсутствующее поле и т. п.
            log.debug("rule %s skipped: %s", rule.id, e)
    return fired


@lru_cache
def referenced_names(expr: str) -> tuple[tuple[str, str | None], ...]:
    """Имена из выражения `when`: ("phq9", "item9") для phq9.item9 и ("pdc_7d", None) для pdc_7d."""
    tree = ast.parse(expr, mode="eval")
    bases, refs = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            bases.add(node.value)
            refs.add((node.value.id, node.attr))
    refs |= {(n.id, None) for n in ast.walk(tree) if isinstance(n, ast.Name) and n not in bases}
    return tuple(sorted(refs, key=lambda r: (r[0], r[1] or "")))


def _plain(value: Any) -> Any:
    return round(value, 4) if isinstance(value, float) else value


def evidence(rule: Rule, context: dict[str, Any]) -> dict[str, Any]:
    """Отпечаток данных, на которых сработало правило: значения имён из `when` и id последнего результата шкалы.

    Правило смотрит на состояние пациента, поэтому срабатывает при каждой его записи. Отпечаток отличает новое
    событие (другой результат шкалы, ещё одно НЯ) от того же состояния, о котором врач уже знает.
    """
    ev: dict[str, Any] = {}
    for root, attr in referenced_names(rule.when):
        ns = context.get(root)
        if attr is None:
            ev[root] = _plain(ns)
        elif isinstance(ns, dict):
            ev[f"{root}.{attr}"] = _plain(ns.get(attr))
            if RECORD in ns:
                ev[f"{root}.{RECORD}"] = ns[RECORD]
    return ev
