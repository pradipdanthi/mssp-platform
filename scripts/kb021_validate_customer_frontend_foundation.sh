#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3001"
BODY_FILE="/tmp/kb021-body.txt"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-021: Validate Customer Frontend Foundation"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  docker compose logs --tail=60 frontend-customer 2>/dev/null || true
  rm -f "$BODY_FILE"
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

cleanup() {
  rm -f "$BODY_FILE"
}
trap cleanup EXIT

section "1. Required frontend-customer files exist"

REQUIRED=(
  "frontend-customer/package.json"
  "frontend-customer/package-lock.json"
  "frontend-customer/Dockerfile"
  "frontend-customer/vite.config.ts"
  "frontend-customer/index.html"
  "frontend-customer/public/app-config.json"
  "frontend-customer/public/brand/kestrel-mark.svg"
  "frontend-customer/public/brand/kestrel-logo.svg"
  "frontend-customer/src/main.tsx"
  "frontend-customer/src/App.tsx"
  "frontend-customer/src/api/client.ts"
  "frontend-customer/src/api/auth.ts"
  "frontend-customer/src/api/customer.ts"
  "frontend-customer/src/auth/AuthContext.tsx"
  "frontend-customer/src/pages/LoginPage.tsx"
  "frontend-customer/src/pages/DashboardPage.tsx"
  "frontend-customer/src/pages/AlertsPage.tsx"
  "frontend-customer/src/pages/IncidentsPage.tsx"
  "frontend-customer/src/pages/AssetsPage.tsx"
  "frontend-customer/src/pages/ReportsPage.tsx"
  "frontend-customer/src/pages/AccountPage.tsx"
  "scripts/kb021_validate_customer_frontend_foundation.sh"
  "docs/KB021_CUSTOMER_FRONTEND_FOUNDATION.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. docker-compose.yml includes frontend-customer on 3001:5173"

grep -q "^  frontend-customer:" docker-compose.yml || fail "docker-compose.yml missing frontend-customer service"
grep -q "container_name: mssp-frontend-customer" docker-compose.yml || fail "missing container_name mssp-frontend-customer"
grep -q '"3001:5173"' docker-compose.yml || fail "missing port mapping 3001:5173"
docker compose config >/dev/null || fail "docker compose config is invalid"
echo "OK: frontend-customer service and compose config are valid."

section "3. Protected paths were not modified"

for p in frontend-admin/ postgres/init/; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-021 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-021 must not modify it"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "4. Customer routes and no admin API usage"

for r in /login /dashboard /alerts /incidents /assets /reports /account; do
  grep -q "path=\"$r\"" frontend-customer/src/App.tsx || fail "App.tsx missing route $r"
  echo "found route: $r"
done

if grep -REn '/admin|/api/admin' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not call /admin APIs"
fi
echo "OK: no /admin API usage in customer frontend source."

grep -q '/customer/dashboard' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/dashboard"
grep -q '/customer/incidents' frontend-customer/src/api/customer.ts \
  || fail "customer.ts missing /customer/incidents"
echo "OK: customer API helpers use /customer/dashboard and /customer/incidents."

section "5. Forbidden admin/credential UI strings"

if grep -RInE 'activation token|api_key|credential rotation|tenant management|user management|Rotate credential' \
  frontend-customer/src 2>/dev/null; then
  fail "customer frontend source contains forbidden admin/credential UI strings"
fi
echo "OK: no activation-token / api_key / rotation / admin management UI strings."

section "6. sessionStorage only (not localStorage for JWT)"

grep -q 'sessionStorage' frontend-customer/src/auth/AuthContext.tsx \
  || fail "AuthContext must use sessionStorage"
if grep -REn 'localStorage\.(setItem|getItem)' frontend-customer/src 2>/dev/null; then
  fail "frontend-customer/src must not use localStorage"
fi
echo "OK: JWT storage uses sessionStorage; no localStorage usage."

section "7. /auth/me tenant_short_code and tenant_name gap-fill"

grep -q "tenant_short_code" backend-api/app/schemas/auth.py \
  || fail "UserPublic schema missing tenant_short_code"
grep -q "tenant_name" backend-api/app/schemas/auth.py \
  || fail "UserPublic schema missing tenant_name"
grep -q "tenant_short_code" backend-api/app/services/auth_service.py \
  || fail "auth_service missing tenant_short_code join/field"
grep -q "tenant_name" backend-api/app/services/auth_service.py \
  || fail "auth_service missing tenant_name join/field"
echo "OK: /auth/me public user model includes tenant_short_code and tenant_name."

section "8. Branding config"

grep -q "Kestrel Cyber Control Plane - Customer" frontend-customer/public/app-config.json \
  || fail "app-config.json documentTitle should be customer-branded"
echo "OK: customer branding config present."

section "9. OpenAPI customer paths"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json" || fail "Could not fetch OpenAPI — is backend-api running?")"
echo "$OPENAPI" | jq -e '.paths | has("/customer/dashboard/{short_code}")' >/dev/null \
  || fail "OpenAPI missing /customer/dashboard/{short_code}"
echo "$OPENAPI" | jq -e '.paths | has("/customer/incidents/{short_code}")' >/dev/null \
  || fail "OpenAPI missing /customer/incidents/{short_code}"
echo "OK: customer endpoints registered in OpenAPI."

section "10. Build and start frontend-customer"

echo "Running: docker compose build frontend-customer"
docker compose build frontend-customer || fail "docker compose build frontend-customer failed"

echo "Running: docker compose up -d frontend-customer"
docker compose up -d frontend-customer || fail "docker compose up -d frontend-customer failed"

echo "Waiting for customer frontend..."
UP=0
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "$FRONTEND_BASE/" 2>/dev/null; then
    UP=1
    break
  fi
  sleep 1
done
[ "$UP" = "1" ] || fail "frontend-customer did not respond on $FRONTEND_BASE within 30s"

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo missing)"
frontend_state="$(docker inspect -f '{{.State.Status}}' mssp-frontend-customer 2>/dev/null || echo missing)"
[ "$backend_state" = "running" ] || fail "backend-api is not running"
[ "$frontend_state" = "running" ] || fail "frontend-customer is not running"
echo "OK: containers running."

section "11. Customer app-config and Vite proxy health"

curl -fsS "$FRONTEND_BASE/app-config.json" -o "$BODY_FILE" || fail "GET app-config.json failed"
jq -e '
  .documentTitle == "Kestrel Cyber Control Plane - Customer"
  and .productName == "Kestrel Cyber"
  and .companyName == "Keroxsys"
' "$BODY_FILE" >/dev/null || fail "app-config.json branding fields incorrect"
echo "OK: customer branding JSON served."

curl -fsS "$FRONTEND_BASE/api/health" -o "$BODY_FILE" || fail "GET /api/health via customer proxy failed"
jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
  || fail "proxied /api/health unhealthy"
echo "OK: Vite proxy reaches backend-api."

section "12. TypeScript/Vite build inside container"

if docker compose exec -T frontend-customer npm run build; then
  echo "OK: npm run build succeeded inside frontend-customer."
else
  fail "npm run build failed inside frontend-customer"
fi

section "13. Secret leak sanity (source)"

if grep -REn 'console\.(log|debug|info|warn|error)\([^)]*\b(token|password|api_?key|secret|jwt)\b' \
  frontend-customer/src 2>/dev/null; then
  fail "Found console.* referring to secrets in frontend-customer/src"
fi
echo "OK: no console secret logging patterns found."

section "14. Honesty note"

echo "curl verifies HTML/config/proxy/build and static source rules. It cannot"
echo "execute the React SPA. Manually open $FRONTEND_BASE, sign in as a customer"
echo "demo user (e.g. customer.viewer@demo.local), and confirm dashboard/"
echo "incidents/assets/reports/account pages render with tenant-scoped data."

section "15. Final verdict"

echo "======================================================================"
echo "KB-021 CUSTOMER FRONTEND FOUNDATION VALIDATION PASSED"
echo "======================================================================"
