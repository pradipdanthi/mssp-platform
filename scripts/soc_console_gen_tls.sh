#!/usr/bin/env bash
# Generate/renew lab self-signed TLS for SOC console mic (HTTPS :3443).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/frontend-soc/certs"
IP="${SOC_CONSOLE_IP:-192.168.0.201}"
mkdir -p "$DIR"
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout "$DIR/soc.key" \
  -out "$DIR/soc.crt" \
  -subj "/CN=mssp-soc-console/O=Kevantic/C=IN" \
  -addext "subjectAltName=IP:${IP},IP:127.0.0.1,DNS:localhost,DNS:soc.local"
chmod 600 "$DIR/soc.key"
chmod 644 "$DIR/soc.crt"
echo "OK: $DIR/soc.crt (use https://${IP}:3443/ for microphone)"
