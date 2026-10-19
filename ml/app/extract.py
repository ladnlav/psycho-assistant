import json

from app.llm import chat_json
from app.schemas import ExtractionResult

SYSTEM_PROMPT = """Ты — ассистент для структурирования медицинских документов на русском языке.
Извлеки из текста истории болезни факты строго по JSON-схеме ниже.

Правила:
- Извлекай только то, что явно написано в тексте. Ничего не додумывай и не ставь диагнозов сам.
- Для каждого факта в поле evidence приводи дословную короткую цитату из текста.
- Отрицания не являются фактами: «суицидальные мысли отрицает» → не добавлять suicidal_ideation.
- Код МКБ-10 указывай, только если он есть в тексте или однозначно соответствует названию диагноза.
- Основной диагноз (психиатрический/неврологический повод обращения) — в diagnoses, остальные — в comorbidities.
- Если данных нет — пустой список или null.
- Ответ — только JSON, без пояснений.

JSON-схема:
{schema}
"""


def extract(text: str) -> ExtractionResult:
    schema = json.dumps(ExtractionResult.model_json_schema(), ensure_ascii=False)
    return chat_json(SYSTEM_PROMPT.format(schema=schema), text, ExtractionResult)
