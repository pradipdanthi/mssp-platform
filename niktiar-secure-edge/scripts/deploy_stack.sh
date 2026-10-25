#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docker"
mkdir -p ../runtime/caddy
[[ -f ../runtime/sites.caddy ]] || echo '# bootstrap' > ../runtime/sites.caddy
docker compose pull || true
docker compose build agent
docker compose up -d
docker compose ps
sleep 5
curl -fsS http://127.0.0.1/healthz || curl -fsS http://127.0.0.1/edge-info || curl -fsS http://127.0.0.1/ | head -c 300 || true
echo
echo DEPLOY_OK
