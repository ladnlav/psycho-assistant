# Клинический компас

Цифровой ассистент врача для ведения пациентов с тревожной и депрессивной симптоматикой. Кейс-чемпионат «Клинический компас» (Авинейро / ГК ХимРар, НМИЦ им. Сербского, Сеченовский Университет).

## Быстрый старт (всё в Docker)

Нужны [Git](https://git-scm.com/downloads) и [Docker Desktop](https://www.docker.com/products/docker-desktop/), запущенный перед командами.

```bash
git clone https://github.com/ladnlav/psycho-assistant.git
cd psycho-assistant
cp .env.example .env
docker compose up -d --build                         # первый раз — несколько минут
docker compose exec backend python -m app.seed       # демо-врач и демо-пациент с данными за 3 недели
```

- Приложение: http://localhost:8080
- API и Swagger: http://localhost:8000/docs
- ML-сервис: http://localhost:8001/docs

Демо-аккаунты: `doctor@example.com` и `patient@example.com`, пароль — `SEED_PASSWORD` из `.env`.

Остановить: `docker compose down` (данные сохранятся). `docker compose down -v` удаляет базу целиком.

## Как показать демо

Врача и пациента лучше открыть в **двух разных браузерах** (или в обычном окне и в режиме инкогнито): в одном окне браузера одновременно можно быть только одним пользователем.

1. **Врач** входит как `doctor@example.com` — видит список пациентов с последними баллами шкал. Карточку пациента не закрываем.
2. **Пациент** входит как `patient@example.com` — главная страница: самочувствие, отметка о приёме Авиандра, опросники, сообщение о побочном эффекте, чат с врачом.
3. Пациент открывает **PHQ-9** и в пункте 9 отмечает «Several days» (русские тексты шкал ещё вносятся) → сразу видит экран помощи с телефонами 112 и 103.
4. У **врача** в ту же секунду всплывает уведомление «Критично», в карточке пациента — красный алерт с временем доставки и источниками, ниже — предложение «ОБЯЗАТЕЛЬНО» направить к психиатру.
5. Врач нажимает **«Принять»** → предложение помечается «принято врачом», направление оформлено, всё записано в журнал аудита.
6. Дополнительно: дневник и графики в карточке, «Пригласить пациента» (код для регистрации нового пациента), чат.

Повторный алерт по тому же правилу не появится, пока врач не нажмёт «Принято к сведению». Чтобы начать демо с чистого листа: `docker compose down -v`, затем снова `up -d --build` и `app.seed`.

## Разработка без Docker (кроме БД)

На Windows команда `python` может называться `py`.

```bash
docker compose up -d db                                  # PostgreSQL на localhost:5433

# бэкенд — http://localhost:8000
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --reload

# фронтенд — http://localhost:5173 (проксирует /api и /ws на :8000)
cd frontend && npm install && npm run dev

# ML-сервис — http://localhost:8001
cd ml
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/uvicorn app.main:app --reload --port 8001
```

## Тесты

```bash
cd backend && .venv/Scripts/python -m pytest -q          # 20 тестов: API, правила, база знаний
cd backend && .venv/Scripts/python -m pytest tests/test_kb.py   # только проверка kb/
cd ml && .venv/Scripts/python -m pytest -q               # 6 тестов
cd ml && .venv/Scripts/python -m eval.run_eval           # метрики извлечения (нужна LLM)
cd frontend && npm run build                             # проверка типов + сборка
```

## Структура

| Папка | Что | Отвечает |
|---|---|---|
| `kb/` | База знаний: шкалы, препараты, правила алертов, источники — [kb/README.md](kb/README.md) | Владислав; клиническое содержание — Савва |
| `backend/` | FastAPI + PostgreSQL: роли, связь врач–пациент, шкалы, дневник, приём, НЯ, алерты (WebSocket), решения врача, аудит | Владислав |
| `ml/` | LLM-сервис: извлечение из историй болезни, триаж сообщений, оценка качества (`ml/eval`) | Матвей |
| `frontend/` | React PWA (Mantine): интерфейсы пациента и врача | Claude, Владислав |
| `loadtest/`, `scripts/` | Нагрузочный тест, резервные копии, замеры (появятся) | Александр |

## Изменение модели данных

```bash
cd backend
.venv/Scripts/alembic revision --autogenerate -m "что изменили"
.venv/Scripts/alembic upgrade head
```

## LLM

ml-сервис обращается к любому OpenAI-совместимому серверу (`LLM_BASE_URL`, `LLM_MODEL` в `.env`). По умолчанию это Ollama на хосте: `ollama pull qwen2.5:7b`. Для GPU с 4 ГБ подойдёт `qwen2.5:3b`, но качество будет ниже. В репозитории и в разработке — только вымышленные данные; реальные данные пациентов не должны уходить во внешние сервисы (152-ФЗ).
