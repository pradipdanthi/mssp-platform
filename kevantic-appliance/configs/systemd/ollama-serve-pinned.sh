#!/usr/bin/env bash
# CPU-pinned Ollama serve wrapper for appliance systemd.
# Reads OLLAMA_CORE_PINNING from environment (set via /etc/kevantic/ollama.env).
set -euo pipefail

PIN="${OLLAMA_CORE_PINNING:-0-5}"
OLLAMA_BIN="${OLLAMA_BIN:-/usr/local/bin/ollama}"

if ! command -v taskset >/dev/null 2>&1; then
  exec "$OLLAMA_BIN" serve
fi

exec taskset -c "$PIN" "$OLLAMA_BIN" serve
