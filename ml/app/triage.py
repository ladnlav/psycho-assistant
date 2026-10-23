"""Триаж сообщений пациента.

Базовый уровень — словарь шаблонов: работает без LLM и при её недоступности (безопасность важнее точности,
поэтому baseline настроен на полноту и даёт ложные срабатывания на отрицаниях).
TODO(Матвей): LLM-классификатор поверх baseline + оценка на размеченном наборе сообщений.
"""

import re

from app.schemas import TriageResponse

PATTERNS: dict[str, tuple[str, list[str]]] = {
    "suicidal_ideation": ("critical", [
        r"не\s+хочу\s+жить", r"покончить\s+с\s+собой", r"суицид", r"убить\s+себя", r"свести\s+сч[её]ты",
        r"наложить\s+на\s+себя\s+руки", r"лучше\s+бы\s+меня\s+не\s+было", r"жить\s+незачем",
        # 23.10, после прогона Сани («Смерть умираю»). «умираю» ловит и панику — для безопасности это допустимо.
        r"хочу\s+умереть", r"умереть\s+бы", r"\bумираю\b(?!\s+(от|со)\s+(скуки|смеха))",
        r"не\s+хочу\s+просыпаться", r"лучше\s+бы\s+не\s+просыпаться", r"нет\s+смысла\s+жить",
        r"покончу\s+с\s+собой",
    ]),
    "self_harm": ("critical", [r"самоповрежд", r"порезать\s+себя", r"режу\s+себя", r"причинить\s+себе\s+вред",
                               r"себе\s+порез", r"порезы\s+на\s+(руке|руках|предплечье)"]),
    "adverse_effect": ("attention", [
        r"побочк", r"побочн", r"сыпь", r"тошн", r"головокруж", r"сонлив", r"после\s+таблет",
    ]),
    "worsening": ("attention", [r"стало\s+хуже", r"ухудш", r"паник", r"не\s+сплю"]),
}
_RANK = {"critical": 2, "attention": 1, "none": 0}


def triage_keywords(text: str) -> TriageResponse:
    lowered = text.lower()
    level, categories, matches = "none", [], []
    for category, (cat_level, patterns) in PATTERNS.items():
        for p in patterns:
            m = re.search(p, lowered)
            if m:
                categories.append(category)
                matches.append(m.group(0))
                if _RANK[cat_level] > _RANK[level]:
                    level = cat_level
                break
    return TriageResponse(level=level, categories=categories, matches=matches, method="keywords")
