#!/usr/bin/env bash
set -euo pipefail

OLLAMA="$HOME/apps/ollama/bin/ollama"
MODEL="qwen2.5:14b"
PROXY="$HOME/ollama_proxy.py"
LOG_DIR="$HOME/qwen_logs"

mkdir -p "$LOG_DIR"

export PATH="$HOME/apps/ollama/bin:$PATH"
export OLLAMA_HOST="127.0.0.1:11434"
export OLLAMA_MODELS="$HOME/ollama_models"
export OLLAMA_CONTEXT_LENGTH=4096

# Use NVIDIA CUDA 12 instead of Vulkan
export OLLAMA_VULKAN=0
export GGML_VK_VISIBLE_DEVICES=-1
export OLLAMA_LLM_LIBRARY=cuda_v12

# Library paths
export LD_LIBRARY_PATH="$HOME/apps/ollama/lib/ollama/cuda_v12:$HOME/apps/ollama/lib/ollama:$HOME/apps/ollama/lib:${LD_LIBRARY_PATH:-}"

echo "Step 1: Checking GPU"

if [[ -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
    echo "ERROR: No allocated GPU found in CUDA_VISIBLE_DEVICES"
    exit 1
fi

nvidia-smi -L

test -x "$OLLAMA" || {
    echo "ERROR: Ollama not found"
    exit 1
}

test -f "$PROXY" || {
    echo "ERROR: Proxy script not found"
    exit 1
}

echo "Step 2: Restarting Ollama"

# Stop previous Ollama server owned by this user
pkill -u "$USER" -x ollama 2>/dev/null || true

for i in {1..20}; do
    if ! ss -ltn | grep -qE ':11434[[:space:]]'; then
        break
    fi
    sleep 1
done

if ss -ltn | grep -qE ':11434[[:space:]]'; then
    echo "ERROR: Port 11434 is still occupied"
    exit 1
fi

nohup "$OLLAMA" serve \
    > "$LOG_DIR/ollama.log" 2>&1 \
    < /dev/null &

echo "Ollama PID: $!"

echo "Step 3: Waiting for Ollama"

READY=0
for i in {1..40}; do
    if curl -fsS --max-time 2 \
        http://127.0.0.1:11434/api/tags \
        >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [[ "$READY" -ne 1 ]]; then
    echo "ERROR: Ollama did not start"
    tail -n 30 "$LOG_DIR/ollama.log"
    exit 1
fi

echo "Step 4: Checking model"

if ! "$OLLAMA" list |
    awk 'NR > 1 {print $1}' |
    grep -Fxq "$MODEL"; then
    echo "ERROR: Model not found: $MODEL"
    exit 1
fi

echo "Step 5: Starting Python proxy"

if ! curl -fsS --max-time 3 \
    http://127.0.0.1:11435/api/tags \
    >/dev/null 2>&1; then

    if ss -ltn | grep -qE ':11435[[:space:]]'; then
        echo "ERROR: Port 11435 is occupied"
        exit 1
    fi

    nohup python3 -u "$PROXY" \
        > "$LOG_DIR/proxy.log" 2>&1 \
        < /dev/null &

    READY=0
    for i in {1..20}; do
        if curl -fsS --max-time 2 \
            http://127.0.0.1:11435/api/tags \
            >/dev/null 2>&1; then
            READY=1
            break
        fi
        sleep 1
    done

    if [[ "$READY" -ne 1 ]]; then
        echo "ERROR: Proxy did not start"
        tail -n 20 "$LOG_DIR/proxy.log"
        exit 1
    fi
fi

echo "Step 6: Testing model on GPU"

curl -fsS --max-time 180 \
    http://127.0.0.1:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen2.5:14b",
        "prompt": "Привет",
        "stream": false,
        "keep_alive": "30m",
        "options": {
            "num_gpu": 99,
            "num_predict": 8
        }
    }' > "$LOG_DIR/test.json" || {
        echo "ERROR: Model failed to respond"
        tail -n 30 "$LOG_DIR/ollama.log"
        exit 1
    }

python3 - "$LOG_DIR/test.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    result = json.load(f)

if result.get("error") or "response" not in result:
    raise SystemExit(f"Model error: {result}")

print("Model response:", result["response"])
PY

echo "Step 7: Checking GPU inference"

"$OLLAMA" ps

if ! "$OLLAMA" ps | grep -F "$MODEL" |
    grep -Fq "100% GPU"; then

    echo "ERROR: Model is not fully loaded on GPU"
    echo "Check CUDA initialization:"
    grep -iE 'cuda|vulkan|error|library|offload' \
        "$LOG_DIR/ollama.log" | tail -n 35 || true
    exit 1
fi

echo "Step 8: Checking native and OpenAI-compatible APIs"

curl -fsS --max-time 10 \
    http://127.0.0.1:11435/api/tags \
    | python3 -m json.tool >/dev/null || {
        echo "ERROR: Native Ollama API is unavailable"
        exit 1
    }

echo "Native Ollama API: OK"

curl -fsS --max-time 10 \
    http://127.0.0.1:11435/v1/models \
    | python3 -m json.tool >/dev/null || {
        echo "ERROR: OpenAI-compatible API is unavailable"
        exit 1
    }

echo "OpenAI-compatible API: OK"

echo
echo "SUCCESS: Qwen 2.5 14B is ready"
echo "GPU inference: 100%"
echo "Remote proxy port: 11435"
echo "Model: $MODEL"
echo "Log: $LOG_DIR/ollama.log"
