# Замеры: доставка алертов и нагрузка

Два скрипта для техметрик кейса: за сколько алерт доходит до врача и как API держит нагрузку. Оба работают только с локальным стендом: они создают учётные записи через обычный API, у каждого прогона свой врач (`latency-…@example.com`, `load-…@example.com`). Демо-врач этих пациентов не видит.

## Подготовка

Стенд поднят (`docker compose up -d --build`). Отдельное окружение для замеров:

```bash
py -3.12 -m venv loadtest/.venv                  # Ubuntu: python3 -m venv loadtest/.venv
source loadtest/.venv/Scripts/activate           # Ubuntu: source loadtest/.venv/bin/activate
pip install -r loadtest/requirements.txt
```

Все команды ниже — из корня репозитория в этом окружении. Если в Git Bash на Windows вместо русских букв видны «кракозябры», выполните `export PYTHONUTF8=1`.

Цифры зависят от машины: рядом с результатами запишите процессор, память и ОС. На время замера закройте тяжёлые программы. Бэкенд сразу после запуска и затем раз в час (`RULES_CHECK_MINUTES`) проверяет правила по всем пациентам, вместе с тестовыми; каждая проверка видна в `docker compose logs backend` строкой `rules schedule: …`. Если она пришлась на замер, повторите его.

## Доставка алертов

```bash
python loadtest/alert_latency.py                                     # 30 пациентов
python loadtest/alert_latency.py --patients 50 --csv loadtest/results/latency.csv
```

Скрипт подключается как врач, за каждого пациента по очереди отправляет PHQ-9 с пунктом 9 = 1 и ждёт критичный алерт. В конце — медиана, p95 и максимум трёх времён:

- **до экрана врача** — от отправки PHQ-9 до прихода алерта врачу, вместе с сетью;
- **на сервере** — от создания алерта до отправки врачу (`delivered_at − created_at` в базе);
- **ответ API** — сколько сервер обрабатывал отправку PHQ-9.

## Нагрузка

```bash
locust -f loadtest/locustfile.py --host http://localhost:8000        # веб-интерфейс: http://localhost:8089
```

Без веб-интерфейса — по одной команде на ступень, каждая 2 минуты:

```bash
locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 10 -r 2 -t 2m --csv loadtest/results/u10
locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 50 -r 5 -t 2m --csv loadtest/results/u50
locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 100 -r 10 -t 2m --csv loadtest/results/u100
```

На каждого виртуального врача приходится 10 пациентов. Пациенты открывают главную (расписание шкал, дневник, напоминания), пишут дневник, открывают и заполняют GAD-7; врач открывает список пациентов, карточки и алерты. Регистрация в статистику не попадает, поэтому в таблицу берите строку **Aggregated**: Med, 95% и # fails. Ниже locust печатает время на сервере по каждому запросу — без сети и без очереди на стороне locust.

| Пользователей | Медиана, мс | p95, мс | Ошибки, % | Запросов/с |
|---|---|---|---|---|
| 10 | | | | |
| 50 | | | | |
| 100 | | | | |

Результаты в `loadtest/results/` в git не попадают. Убрать тестовых пользователей можно только вместе со всей базой: `docker compose down -v`, затем команды из «Быстрого старта» в [README проекта](../README.md) — `docker compose up -d --build`, `docker compose exec backend python -m app.seed` и `docker compose exec backend python -m app.scenarios`.
