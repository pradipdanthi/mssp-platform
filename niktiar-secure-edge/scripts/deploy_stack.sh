#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docker"
mkdir -p ../runtime/caddy ../runtime/dns-filter ../runtime/dns-feeds ../runtime/coraza-rules.d
[[ -f ../runtime/sites.caddy ]] || echo '# bootstrap' > ../runtime/sites.caddy
if [[ ! -f ../runtime/dns-filter/config.yml ]]; then
  cp -a ../runtime/dns-filter/config.yml.bak 2>/dev/null || true
  cat > ../runtime/dns-filter/config.yml <<'YAML'
ports:
  dns: 0.0.0.0:53
  http: 0.0.0.0:4000
upstreams:
  groups:
    default:
      - 1.1.1.1
      - 8.8.8.8
blocking:
  blackLists: {}
  clientGroupsBlock:
    default: []
  blockType: zeroIP
caching:
  minTime: 5m
  maxTime: 30m
  prefetching: true
log:
  level: info
YAML
fi
docker compose pull || true
docker compose build agent dashboard dns-feed-sync
docker compose up -d
docker compose ps
sleep 8
curl -fsS http://127.0.0.1/healthz || curl -fsS http://127.0.0.1/edge-info || curl -fsS http://127.0.0.1/ | head -c 300 || true
echo
# DNS filter feed sync may take a minute on first pull
docker logs niktiar-se-dns-sync --tail 20 2>/dev/null || true
echo DEPLOY_OK
