# Модель на V100 через JupyterHub

Скрипты запускают с ноутбука GPU-сессию JupyterHub, а в ней — Ollama с OpenAI-совместимым прокси на порту 11435. SSH не нужен. Настройка `.env` и проверка описаны в корневом README, раздел «Модель на V100 через JupyterHub».

Скрипты `from_server_...` - копия скриптов, находящихся на сервере. 

## Установка

```bash
py -3.12 -m venv .venv                            # Ubuntu: python3 -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Ubuntu: .venv/bin/pip install -r requirements.txt
```

## Запуск и остановка

```bash
./start_llm.sh 
./stop_llm.sh
./stop_llm.sh --session   # заодно остановить GPU-сессию JupyterHub
```

Адрес и токен скрипт берёт из корневого `.env` репозитория:

- `LLM_BASE_URL` — `https://<адрес-JupyterHub>/user/<логин>/proxy/11435/v1`, из него же берётся логин;
- `LLM_API_KEY` — токен JupyterHub. Он должен оставаться действительным после остановки GPU-сессии и давать право запускать сессии с профилем `gpu`.

На GPU-сервере нужны `~/start_qwen.sh`, `~/stop_qwen.sh`, `~/ollama_proxy.py` и Ollama с моделью `qwen2.5:14b`. Эти скрипты находятся в этой директории с префиксом `from_server_`.
