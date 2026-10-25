#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docker"
docker compose pull || true
docker compose build agent
docker compose up -d waf crowdsec agent
docker compose ps
sleep 3
curl -fsS http://127.0.0.1/healthz || curl -fsS http://127.0.0.1/ | head -c 300 || true
echo
echo DEPLOY_OK
