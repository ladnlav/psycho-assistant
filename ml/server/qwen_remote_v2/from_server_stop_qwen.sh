#!/usr/bin/env bash
set -euo pipefail

OLLAMA="$HOME/apps/ollama/bin/ollama"
PROXY="$HOME/ollama_proxy.py"

echo "Step 1: Stopping Python proxy"

# Останавливаем только процесс нашего прокси
pkill -TERM -u "$USER" -f \
    "^python3 -u $PROXY$" 2>/dev/null || true

echo "Step 2: Stopping Ollama"

# Останавливаем только Ollama, запущенную с serve
pkill -TERM -u "$USER" -f \
    "^$OLLAMA serve$" 2>/dev/null || true

echo "Step 3: Waiting for shutdown"

for i in {1..20}; do
    if ! ss -ltn | grep -qE ':(11434|11435)[[:space:]]'; then
        break
    fi
    sleep 1
done

echo "Step 4: Checking ports"

if ss -ltn | grep -qE ':11434[[:space:]]'; then
    echo "WARNING: Port 11434 is still occupied"
else
    echo "Ollama stopped"
fi

if ss -ltn | grep -qE ':11435[[:space:]]'; then
    echo "WARNING: Port 11435 is still occupied"
else
    echo "Python proxy stopped"
fi

echo
echo "Stop procedure completed"
