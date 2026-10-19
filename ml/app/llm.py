"""Тонкая обёртка над OpenAI-совместимым API: запрос → JSON → проверка pydantic-схемой → повтор при ошибке."""

import json
import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def _client() -> OpenAI:
    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=s.llm_timeout_s)


def chat_json(system: str, user: str, schema: type[T]) -> T:
    s = get_settings()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_error: Exception | None = None
    for attempt in range(s.llm_max_retries + 1):
        resp = _client().chat.completions.create(
            model=s.llm_model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        try:
            return schema.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            log.warning("LLM вернула невалидный JSON (попытка %d): %s", attempt + 1, e)
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"Ответ не соответствует схеме: {e}. Верни только исправленный JSON."},
            ]
    raise LLMError(f"Не удалось получить валидный JSON: {last_error}")
