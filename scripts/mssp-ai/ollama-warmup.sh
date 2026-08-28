#!/usr/bin/env bash
# Preload qwen2.5:7b into RAM after ollama.service start (avoids cold-load CPU spike on first triage).
set -euo pipefail
MODEL="${OLLAMA_WARMUP_MODEL:-qwen2.5:7b}"
URL="${OLLAMA_WARMUP_URL:-http://127.0.0.1:11434}"
THREADS="${OLLAMA_NUM_THREADS:-2}"
CTX="${OLLAMA_WARMUP_NUM_CTX:-2048}"
PREDICT="${OLLAMA_WARMUP_NUM_PREDICT:-8}"

for _ in $(seq 1 60); do
  curl -fsS --max-time 2 "${URL}/api/version" >/dev/null 2>&1 && break
  sleep 1
done

curl -fsS --max-time 120 "${URL}/api/chat" \
  -H 'Content-Type: application/json' \
  -d "$(python3 - <<PY
import json
print(json.dumps({
  "model": "${MODEL}",
  "stream": False,
  "keep_alive": -1,
  "messages": [{"role": "user", "content": "warmup"}],
  "options": {
    "num_thread": int("${THREADS}"),
    "num_ctx": int("${CTX}"),
    "num_predict": int("${PREDICT}"),
    "temperature": 0.1,
  },
}))
PY
)" >/dev/null
echo "ollama-warmup OK model=${MODEL}"
