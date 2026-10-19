"""Движок правил: безопасное вычисление выражений `when` из kb/rules над контекстом пациента."""

import logging
from collections.abc import Iterable
from typing import Any

from simpleeval import SimpleEval

from app.kb import Rule

log = logging.getLogger(__name__)


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
