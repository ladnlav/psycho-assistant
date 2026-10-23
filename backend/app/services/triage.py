"""Триаж свободного текста пациента: сообщения врачу и описания нежелательных явлений.

ml-сервис (/triage) только размечает текст уровнем риска, а что с этим делать, решают правила kb/rules
по имени text.critical (ядро на правилах, ML на периферии). Если ml-сервис не ответил, текст сохраняется
без разметки и правила по нему не срабатывают — это пишется в лог.
"""

import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
TIMEOUT_S = 5


def classify(text: str) -> dict[str, Any] | None:
    """{"level": "critical" | "attention" | "none", "categories": [...], "matches": [...], "method": ...} или None."""
    try:
        r = httpx.post(f"{get_settings().ml_url}/triage", json={"text": text}, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("триаж недоступен, текст сохранён без разметки: %s", e)
        return None
