# Модель на V100 через JupyterHub

Скрипты запускают с ноутбука GPU-сессию JupyterHub, а в ней — Ollama с `qwen2.5:14b` и OpenAI-совместимым прокси на порту 11435. JupyterHub отдаёт этот порт по https и пускает только с токеном; для приложения это обычный OpenAI-совместимый сервер, SSH не нужен.

Скрипты `from_server_...` — копия скриптов, находящихся на сервере.

## Настройка `.env`

Строки в корневом `.env` репозитория. Токен храним только там: не коммитим и не пересылаем в общие чаты.

```ini
LLM_BASE_URL=https://<адрес-JupyterHub>/user/<логин>/proxy/11435/v1
LLM_BASE_URL_DOCKER=https://<адрес-JupyterHub>/user/<логин>/proxy/11435/v1   # тот же адрес — для контейнера ml
LLM_API_KEY=<токен JupyterHub>
LLM_MODEL=qwen2.5:14b
```

Логин скрипт берёт из `LLM_BASE_URL`. Токен должен оставаться действительным после остановки GPU-сессии и давать право запускать сессии с профилем `gpu`.

## Установка

```bash
py -3.12 -m venv .venv                            # Ubuntu: python3 -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Ubuntu: .venv/bin/pip install -r requirements.txt
```

## Запуск и остановка

```bash
./start_llm.sh                # поднимает GPU-сессию, если её нет, и запускает Ollama с прокси
./stop_llm.sh                 # останавливает Ollama; GPU-сессия остаётся
./stop_llm.sh --session       # заодно освобождает GPU-сессию
```

Запуск с нуля занимает около 2 минут. Повторный `./start_llm.sh` ничего не ломает: если модель уже отвечает, он сообщит `Ollama and OpenAI-compatible proxy already available`.

Проверка — ответ JSON со списком моделей:

```bash
curl -H "Authorization: Bearer <токен>" https://<адрес-JupyterHub>/user/<логин>/proxy/11435/v1/models
```

Затем `docker compose up -d ml` из корня репозитория пересоздаст контейнер с новыми переменными, и `POST /extract` пойдёт в модель на V100: короткая история болезни — около 10–20 секунд. `python -m eval.run_eval` в `ml/` берёт адрес из того же `.env`.

## Что важно знать

- GPU-сессия живёт до 4 часов, потом JupyterHub её останавливает, и `/extract` отвечает «503: LLM недоступна». Тогда снова `./start_llm.sh`.
- `ERROR: LLM_BASE_URL в .env должен быть адресом прокси JupyterHub` — в `.env` остался адрес локальной Ollama.
- Ответ 302 с переходом на `/hub/login` или 403 — токен не передан, отозван или у него нет прав на GPU-сессии.
- На GPU-сервере нужны `~/start_qwen.sh`, `~/stop_qwen.sh`, `~/ollama_proxy.py` и Ollama с моделью `qwen2.5:14b`; их копии — файлы `from_server_*` в этой папке.
- Без JupyterHub модель можно запустить на любом сервере с GPU (`ollama serve`) и пробросить до ноутбука SSH-туннелем: `ssh -N -L 11434:localhost:11434 <логин>@<сервер>`. Тогда в `.env` — адрес локальной Ollama по умолчанию.
