#!/usr/bin/env bash
# Permanent lab preview via nginx container (survives reboot with --restart unless-stopped)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
NAME=niktiar-website-lab
docker rm -f "$NAME" 2>/dev/null || true
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  -p 8080:80 \
  -v "$ROOT:/usr/share/nginx/html:ro" \
  nginx:1.27-alpine
echo "Kevantic website lab: http://192.168.0.201:8080/"
docker ps --filter "name=$NAME" --format '{{.Names}} {{.Status}} {{.Ports}}'
