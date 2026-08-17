#!/usr/bin/env bash
# Run Playwright E2E via official image (host may not have Node).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.51.0-jammy}"
ARGS=("${@:-}")

cd "$ROOT"

# Ensure validation.env is readable inside the container (mounted).
if [[ ! -f "$ROOT/.secrets/validation.env" ]]; then
  echo "Missing $ROOT/.secrets/validation.env — required for portal login tests."
  exit 1
fi

docker run --rm --network host \
  -u "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e npm_config_cache=/tmp/npm-cache \
  -v "$ROOT/e2e:/work" \
  -v "$ROOT/.secrets/validation.env:/secrets/validation.env:ro" \
  -e MSSP_VALIDATION_ENV=/secrets/validation.env \
  -e E2E_ADMIN_URL="${E2E_ADMIN_URL:-http://127.0.0.1:3000}" \
  -e E2E_CUSTOMER_URL="${E2E_CUSTOMER_URL:-http://127.0.0.1:3001}" \
  -w /work \
  "$IMAGE" \
  bash -lc 'npm install --silent && npx playwright test '"${ARGS[*]}"
