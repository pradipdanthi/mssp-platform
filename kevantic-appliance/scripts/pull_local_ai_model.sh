#!/usr/bin/env bash
# Pull the appliance-local triage model into Ollama.
# Requires ~5GB free disk. Prefer ≥16GB RAM on the host while pulling/loading.
#
# Usage:
#   ./pull_local_ai_model.sh [model]
# Default model: qwen2.5:7b
set -euo pipefail

MODEL="${1:-${LOCAL_AI_MODEL:-qwen2.5:7b}}"
log() { printf '[pull-local-ai-model] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

command -v ollama >/dev/null 2>&1 || die "ollama not installed — run install_appliance_ollama.sh first"
systemctl is-active --quiet ollama.service || systemctl start ollama.service

avail_kb="$(df -Pk /usr/share/ollama 2>/dev/null | awk 'NR==2{print $4}')"
if [[ -n "${avail_kb:-}" && "$avail_kb" -lt 6000000 ]]; then
  die "need ~6GB free under /usr/share/ollama (have ${avail_kb}KB)"
fi

log "Pulling model ${MODEL} (this can take several minutes)"
ollama pull "$MODEL"
ollama list | grep -F "$MODEL" || die "model ${MODEL} not listed after pull"

log "OK — model ${MODEL} ready"
echo APPLIANCE_LOCAL_AI_MODEL_OK
