#!/usr/bin/env bash
# Install Ollama on the Kevantic appliance (systemd + localhost-only bind + CPU pinning).
# Safe to re-run. Does NOT pull models (see pull_local_ai_model.sh).
#
# Profile defaults (override via env before running):
#   KEVANTIC_APPLIANCE_PROFILE=lab|prod
#   OLLAMA_CPU_THREADS, OLLAMA_CORE_PINNING, OLLAMA_KEEP_ALIVE
#
# Usage (on appliance as root/sudo):
#   ./install_appliance_ollama.sh
set -euo pipefail

log() { printf '[install-appliance-ollama] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "run as root (or sudo)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="${OLLAMA_UNIT_SRC:-$SCRIPT_DIR/../configs/systemd/ollama.service}"
DROPIN_SRC="${OLLAMA_DROPIN_SRC:-$SCRIPT_DIR/../configs/systemd/ollama.service.d/override.conf}"
WRAPPER_SRC="${OLLAMA_WRAPPER_SRC:-$SCRIPT_DIR/../configs/systemd/ollama-serve-pinned.sh}"
ENV_EXAMPLE="${OLLAMA_ENV_EXAMPLE:-$SCRIPT_DIR/../configs/kevantic/ollama.env.example}"

PROFILE="${KEVANTIC_APPLIANCE_PROFILE:-${KEVANTIC_DEPLOY_PROFILE:-lab}}"
PROFILE="$(echo "$PROFILE" | tr '[:upper:]' '[:lower:]')"

if [[ "$PROFILE" == "prod" || "$PROFILE" == "production" ]]; then
  DEFAULT_CPU_THREADS=6
  DEFAULT_CORE_PINNING="0-5"
else
  DEFAULT_CPU_THREADS=4
  DEFAULT_CORE_PINNING="0-5"
fi

OLLAMA_CPU_THREADS="${OLLAMA_CPU_THREADS:-$DEFAULT_CPU_THREADS}"
OLLAMA_CORE_PINNING="${OLLAMA_CORE_PINNING:-$DEFAULT_CORE_PINNING}"
OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"

if ! command -v ollama >/dev/null 2>&1; then
  log "Installing Ollama via official install script"
  export OLLAMA_INSTALL_DIR="${OLLAMA_INSTALL_DIR:-/usr/local}"
  curl -fsSL https://ollama.com/install.sh | sh
else
  log "Ollama already present: $(command -v ollama) ($(ollama --version 2>/dev/null || true))"
fi

command -v ollama >/dev/null 2>&1 || die "ollama binary missing after install"
command -v taskset >/dev/null 2>&1 || log "WARN: taskset missing — wrapper will run unpinned ollama serve"

# Pinned serve wrapper (taskset + core mask from ollama.env).
if [[ -f "$WRAPPER_SRC" ]]; then
  install -m 0755 "$WRAPPER_SRC" /usr/local/sbin/ollama-serve-pinned.sh
else
  cat >/usr/local/sbin/ollama-serve-pinned.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
PIN="${OLLAMA_CORE_PINNING:-0-5}"
OLLAMA_BIN="${OLLAMA_BIN:-/usr/local/bin/ollama}"
if command -v taskset >/dev/null 2>&1; then
  exec taskset -c "$PIN" "$OLLAMA_BIN" serve
fi
exec "$OLLAMA_BIN" serve
EOF
  chmod 0755 /usr/local/sbin/ollama-serve-pinned.sh
fi

# Environment file — lab vs prod thread defaults; operators may edit in place.
install -d -m 0755 /etc/kevantic /etc/niktiar
for ENVF in /etc/kevantic/ollama.env /etc/niktiar/ollama.env; do
  if [[ ! -f "$ENVF" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
      install -m 0644 "$ENV_EXAMPLE" "$ENVF"
    else
      cat >"$ENVF" <<EOF
KEVANTIC_APPLIANCE_PROFILE=${PROFILE}
OLLAMA_CPU_THREADS=${OLLAMA_CPU_THREADS}
OLLAMA_CORE_PINNING=${OLLAMA_CORE_PINNING}
OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE}
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_ORIGINS=http://127.0.0.1,http://localhost
LOCAL_AI_NUM_THREAD=${OLLAMA_CPU_THREADS}
LOCAL_AI_CACHE_ENABLED=true
LOCAL_AI_CACHE_TTL_SECONDS=86400
EOF
    fi
  fi
  # Idempotent refresh of core tuning keys (preserve unrelated custom keys).
  for kv in \
    "KEVANTIC_APPLIANCE_PROFILE=${PROFILE}" \
    "OLLAMA_CPU_THREADS=${OLLAMA_CPU_THREADS}" \
    "OLLAMA_CORE_PINNING=${OLLAMA_CORE_PINNING}" \
    "OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE}" \
    "OLLAMA_NUM_PARALLEL=1" \
    "OLLAMA_MAX_LOADED_MODELS=1" \
    "OLLAMA_HOST=127.0.0.1:11434" \
    "LOCAL_AI_NUM_THREAD=${OLLAMA_CPU_THREADS}"; do
    key="${kv%%=*}"
    if grep -q "^${key}=" "$ENVF" 2>/dev/null; then
      sed -i "s|^${key}=.*|${kv}|" "$ENVF"
    else
      echo "$kv" >>"$ENVF"
    fi
  done
done

# Prefer our hardened unit / drop-in (localhost bind) over installer defaults.
if [[ -f "$UNIT_SRC" ]]; then
  install -d -m 0755 /etc/systemd/system
  if [[ "$(readlink -f "$UNIT_SRC")" != "$(readlink -f /etc/systemd/system/ollama.service)" ]]; then
    install -m 0644 "$UNIT_SRC" /etc/systemd/system/ollama.service
  fi
fi
install -d -m 0755 /etc/systemd/system/ollama.service.d
if [[ -f "$DROPIN_SRC" ]]; then
  DEST=/etc/systemd/system/ollama.service.d/override.conf
  if [[ "$(readlink -f "$DROPIN_SRC")" != "$(readlink -f "$DEST")" ]]; then
    install -m 0644 "$DROPIN_SRC" "$DEST"
  fi
else
  cat >/etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
EnvironmentFile=-/etc/kevantic/ollama.env
EnvironmentFile=-/etc/niktiar/ollama.env
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=-1"
ExecStart=
ExecStart=/usr/local/sbin/ollama-serve-pinned.sh
EOF
fi

if ! id ollama >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /usr/share/ollama --shell /usr/sbin/nologin ollama
fi
install -d -m 0755 -o ollama -g ollama /usr/share/ollama

systemctl daemon-reload
systemctl enable ollama.service
systemctl restart ollama.service

ready=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" -eq 1 ]] || die "Ollama did not become ready on 127.0.0.1:11434"

if ss -ltn 2>/dev/null | grep -E '0\.0\.0\.0:11434|:::11434|\*:11434' >/dev/null; then
  die "Ollama is listening on non-loopback — refuse (must be 127.0.0.1 only)"
fi

log "OK — Ollama active profile=${PROFILE} threads=${OLLAMA_CPU_THREADS} pin=${OLLAMA_CORE_PINNING} keep_alive=${OLLAMA_KEEP_ALIVE}"
echo APPLIANCE_OLLAMA_INSTALL_OK
