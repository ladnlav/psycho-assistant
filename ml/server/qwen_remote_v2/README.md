# Qwen remote JupyterHub control

Run on your laptop, without SSH, using your existing JupyterHub token and server-side scripts.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install requests websocket-client python-dotenv
chmod +x start_llm.sh stop_llm.sh
```

## Use

```bash
./start_llm.sh
./stop_llm.sh
./stop_llm.sh --session  # also stop the JupyterHub GPU session
```

Prerequisites on GPU server: `~/start_qwen.sh`, `~/stop_qwen.sh`, `~/ollama_proxy.py`, and Ollama with the `qwen2.5:14b` model. Token file on laptop: `~/.config/qwen/token`.

Optional environment variables: `JUPYTERHUB_URL`, `JUPYTERHUB_USER`, `JUPYTERHUB_TOKEN_FILE`.

The JupyterHub token must remain valid after a GPU session stops, and you must have permissions to spawn GPU profile sessions. Per-cluster policies apply. Never commit the token to git.
