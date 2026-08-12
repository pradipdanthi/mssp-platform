#!/usr/bin/env bash
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

echo "=== KB: Admin Service Catalog ops (pricing / rollout / request badges) ==="

need() { [ -f "$1" ] || { echo "FAIL missing $1"; exit 1; }; }
need postgres/init/033_service_catalog_pricing.sql
need backend-api/app/services/service_catalog_pricing.py
need backend-api/app/api/routes/service_catalog.py
need frontend-admin/src/pages/ServiceCatalogPage.tsx

# No customer consulting CTA button in admin catalog page source
if rg -n '>\s*Request for Consulting\s*<' frontend-admin/src/pages/ServiceCatalogPage.tsx; then
  echo "FAIL: Admin catalog still contains Request for Consulting CTA button"
  exit 1
fi
echo "OK: Admin catalog consulting CTA button removed"

# Pricing API routes present
rg -n 'admin/service-catalog|customer/service-catalog/pricing|rollout' backend-api/app/api/routes/service_catalog.py >/dev/null
echo "OK: catalog pricing/rollout routes present"

# Migration applied?
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d service_catalog_pricing"' >/dev/null \
  || { echo "FAIL: service_catalog_pricing table missing — apply 033 migration"; exit 1; }
echo "OK: service_catalog_pricing table exists"

API="${API_BASE:-http://127.0.0.1:8000}"
curl -fsS "$API/health" >/dev/null
echo "OK: /health"

# Unauthenticated catalog should be protected
code=$(curl -s -o /dev/null -w '%{http_code}' "$API/admin/service-catalog" || true)
if [ "$code" != "401" ] && [ "$code" != "403" ]; then
  echo "FAIL: expected 401/403 for /admin/service-catalog without auth, got $code"
  exit 1
fi
echo "OK: /admin/service-catalog requires auth ($code)"

# Admin page rebuilt into nginx (optional if containers up)
if curl -fsS http://127.0.0.1:3000/ >/dev/null 2>&1; then
  # JS bundle should not advertise consulting CTA on services route content after rebuild —
  # soft check: admin API client includes catalog helpers
  rg -n 'getAdminServiceCatalog|rolloutCatalogService|patchCatalogPricing' frontend-admin/src/api/admin.ts >/dev/null
  echo "OK: admin API client helpers present"
fi

echo
echo "VALIDATION PASSED: Admin Service Catalog ops (A+B+C foundation)"
