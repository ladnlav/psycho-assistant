# Демо-сценарии

Каждый файл `*.yaml` — один вымышленный пациент демо-врача с историей по неделям. Сценарии пишет Савва (таблица «Сценарий N»), в YAML их переносим мы.

```bash
docker compose exec backend python -m app.seed          # сначала демо-врач
docker compose exec backend python -m app.scenarios     # все сценарии; уже загруженные пропускаются
docker compose exec backend python -m app.scenarios s1 --reset   # перезагрузить один сценарий
```

Пароль пациентов сценариев — `SEED_PASSWORD` из `.env`. Даты считаются от сегодняшнего дня: последняя неделя заканчивается вчера, сегодняшний день пустой — его показывают на демо. После загрузки система проверяет правила по итоговому состоянию, и врач сразу видит алерты.

## Формат

```yaml
id: s1                          # совпадает с именем файла
title_ru: "…"
status: draft                   # draft → validated после проверки Саввой
author_ru: "Савва, таблица 21.10"
patient: { full_name: "Сценарий 1: …", email: scenario1@example.com, sex: male, age: 63 }
diagnoses:
  - { icd10: "F41.1", title: "Генерализованное тревожное расстройство" }
past_medications: ["Пароксетин"]      # до Авиандра, уже отменены
prescribe_aviandr: true               # false — врач назначает на демо
aviandr_dose_mg: null                 # только по инструкции ГРЛС
weeks:                                # неделя 0 — визит и назначение
  - week: 0
    anxiety: 7                        # самочувствие 0–10, одно значение на всю неделю
    mood: 3
    sleep: 4
    gad7: 14                          # сумма; ответы по пунктам раскладываются поровну
    phq9: 9
    phq9_item9: 0                     # пункт 9 отдельно (0–3)
    intake_days: 6                    # дней с приёмом из 7
    adverse_events: [{ description: "…", severity: mild, serious: false }]
    messages: ["…"]                   # сообщения пациента в чат
    expected_ru: "что должна показать система"   # для проверки демо, в базу не пишется
expected:
  referral_ru: "…"
```
