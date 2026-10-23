#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$SCRIPT_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$SCRIPT_DIR/.venv/Scripts/python"   # Windows: venv кладёт python в Scripts
exec "$PY" "$SCRIPT_DIR/remote_llm.py" stop "$@"
