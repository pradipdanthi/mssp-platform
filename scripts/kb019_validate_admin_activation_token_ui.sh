#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"
BODY_FILE="/tmp/kb019-body.txt"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-019: Validate Admin Activation Token Management UI"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent frontend-admin logs:"
  docker compose logs --tail=80 frontend-admin 2>/dev/null || true
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

section "1. Expected files exist"

REQUIRED_FILES=(
  "frontend-admin/src/api/appliances.ts"
  "frontend-admin/src/pages/AppliancesPage.tsx"
  "frontend-admin/src/pages/LoginPage.tsx"
  "frontend-admin/src/components/BrandMark.tsx"
  "frontend-admin/src/styles.css"
  "frontend-admin/public/brand/kestrel-mark.svg"
  "frontend-admin/public/brand/kestrel-logo.svg"
  "frontend-admin/public/app-config.json"
  "scripts/kb019_validate_admin_activation_token_ui.sh"
)

for f in "${REQUIRED_FILES[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected paths were not modified"

PROTECTED_PATHS=(
  "backend-api/"
  "postgres/init/"
  "docker-compose.yml"
)

for p in "${PROTECTED_PATHS[@]}"; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-019 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-019 must not modify it"
  echo "OK: $p is unmodified (no working-tree or staged diff)"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows up as changed/untracked in git status - it must never be touched by this task"
fi
echo "OK: git status shows no changes to .env"

section "3. Bash syntax self-check"

bash -n "$0" && echo "OK: this validation script itself has valid bash syntax (bash -n)."

section "4. Confirm frontend and backend containers are running"

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo 'missing')"
frontend_state="$(docker inspect -f '{{.State.Status}}' mssp-frontend-admin 2>/dev/null || echo 'missing')"
postgres_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"

echo "mssp-backend-api state:    $backend_state"
echo "mssp-frontend-admin state: $frontend_state"
echo "mssp-postgres health:      $postgres_health"
echo "mssp-redis health:         $redis_health"

[ "$backend_state" = "running" ] || fail "backend-api container is not running"
[ "$frontend_state" = "running" ] || fail "frontend-admin container is not running"
[ "$postgres_health" = "healthy" ] || fail "postgres is not healthy"
[ "$redis_health" = "healthy" ] || fail "redis is not healthy"

section "5. Backend health and frontend proxy health"

curl -fsS "$API_BASE/health" -o "$BODY_FILE" || fail "GET $API_BASE/health failed"
jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
  || fail "direct /health did not report api/database/redis all as ok"

curl -fsS "$FRONTEND_BASE/api/health" -o "$BODY_FILE" || fail "GET $FRONTEND_BASE/api/health failed"
jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
  || fail "proxied /api/health did not report api/database/redis all as ok"
echo "OK: direct and proxied health checks passed."

section "6. OpenAPI lists all 3 activation-token endpoints"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json")"
for p in \
  "/admin/tenants/{tenant_id}/appliance-activation-tokens" \
  "/admin/appliance-activation-tokens/{token_id}/revoke"
do
  echo "$OPENAPI" | jq -e --arg p "$p" '.paths | has($p)' >/dev/null \
    || fail "OpenAPI schema is missing $p"
  echo "found OpenAPI path: $p"
done

# POST and GET share the same path key in OpenAPI; verify both methods exist.
echo "$OPENAPI" | jq -e '
  .paths["/admin/tenants/{tenant_id}/appliance-activation-tokens"] | has("get") and has("post")
' >/dev/null || fail "OpenAPI path for tenant activation tokens is missing get and/or post"
echo "$OPENAPI" | jq -e '
  .paths["/admin/appliance-activation-tokens/{token_id}/revoke"] | has("patch")
' >/dev/null || fail "OpenAPI path for revoke is missing patch"
echo "OK: all 3 activation-token operations are registered in OpenAPI."

section "7. Source contains activation-token API helpers and one-time warning"

grep -q "export function listActivationTokens" frontend-admin/src/api/appliances.ts \
  || fail "appliances.ts is missing listActivationTokens"
grep -q "export function createActivationToken" frontend-admin/src/api/appliances.ts \
  || fail "appliances.ts is missing createActivationToken"
grep -q "export function revokeActivationToken" frontend-admin/src/api/appliances.ts \
  || fail "appliances.ts is missing revokeActivationToken"
if grep -E '^\s*token_hash\s*:' frontend-admin/src/api/appliances.ts >/dev/null 2>&1; then
  fail "appliances.ts must not expose a token_hash field in API client types"
fi
echo "OK: activation-token API helpers are present; token_hash is not exposed as a client field."

grep -q "Copy this token now. It will not be shown again." frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "AppliancesPage.tsx is missing the one-time raw-token warning"
echo "OK: one-time raw-token warning text is present."

section "8. Role gating and raw-token safety in source"

grep -q 'user?.role === "platform_admin"' frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "AppliancesPage.tsx does not gate create/revoke on platform_admin"
grep -q "canManageTokens" frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "AppliancesPage.tsx is missing canManageTokens role gating"
echo "OK: platform_admin role gating exists for create/revoke controls."

if grep -REn 'console\.(log|debug|info|warn|error)\([^)]*\b(token|password|api_?key|secret|jwt)\b' \
  frontend-admin/src 2>/dev/null; then
  fail "Found a console.* call referencing token/password/api_key/secret/jwt in frontend-admin/src"
fi
echo "OK: no console.* calls referencing token/password/api_key/secret/jwt."

if grep -REn '(localStorage|sessionStorage)\.(setItem|getItem)\([^)]*(activation|raw.?token|token)' \
  frontend-admin/src/pages/AppliancesPage.tsx frontend-admin/src/api/appliances.ts 2>/dev/null; then
  fail "Found localStorage/sessionStorage usage for activation/raw token in activation-token UI code"
fi
# Stronger check: AppliancesPage must not write any raw activation token into storage.
if grep -En 'sessionStorage\.setItem|localStorage\.setItem' frontend-admin/src/pages/AppliancesPage.tsx 2>/dev/null; then
  fail "AppliancesPage.tsx must not call sessionStorage/localStorage setItem (raw token safety)"
fi
echo "OK: activation-token UI does not persist raw tokens in localStorage/sessionStorage."

section "9. Kestrel logo assets reachable and parseable as XML"

curl -fsS "$FRONTEND_BASE/brand/kestrel-mark.svg" -o /tmp/kb019-mark.svg \
  || fail "GET $FRONTEND_BASE/brand/kestrel-mark.svg failed"
curl -fsS "$FRONTEND_BASE/brand/kestrel-logo.svg" -o /tmp/kb019-logo.svg \
  || fail "GET $FRONTEND_BASE/brand/kestrel-logo.svg failed"

python3 - <<'PY'
import sys
import xml.etree.ElementTree as ET

for path in ("/tmp/kb019-mark.svg", "/tmp/kb019-logo.svg"):
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        print(f"INVALID SVG XML: {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    tag = root.tag.rsplit("}", 1)[-1]
    if tag.lower() != "svg":
        print(f"Root element is not svg in {path}: {root.tag}", file=sys.stderr)
        sys.exit(1)
    print(f"OK parseable SVG: {path}")
PY

rm -f /tmp/kb019-mark.svg /tmp/kb019-logo.svg
echo "OK: both brand SVG assets are reachable and parseable as XML."

section "10. Login page brand mark usage avoids broken-image rendering"

grep -q "BrandMark" frontend-admin/src/pages/LoginPage.tsx \
  || fail "LoginPage.tsx does not use BrandMark"
grep -q 'variant="mark"' frontend-admin/src/pages/LoginPage.tsx \
  || fail "LoginPage.tsx should use BrandMark variant=\"mark\" to avoid broken logo rendering"
grep -q "onError" frontend-admin/src/components/BrandMark.tsx \
  || fail "BrandMark.tsx should include an onError fallback to markSrc"
echo "OK: Login page uses BrandMark mark variant; BrandMark has onError fallback."

section "11. Frontend TypeScript/Vite build inside container"

echo "Running: docker compose exec -T frontend-admin npm run build"
if docker compose exec -T frontend-admin npm run build; then
  echo "OK: TypeScript compile + Vite production build succeeded inside the container."
else
  fail "docker compose exec -T frontend-admin npm run build failed"
fi

section "12. Honesty note on curl vs browser rendering"

echo "This script verifies source structure, OpenAPI registration, proxy health,"
echo "SVG XML parseability, logo URL reachability, and a container TypeScript"
echo "build. It CANNOT execute React in a real browser, so it does not prove"
echo "that the login logo paints correctly on screen, that tenant selection"
echo "loads tokens interactively, or that the one-time raw-token panel appears"
echo "after clicking Create. Manually open $FRONTEND_BASE in a browser, confirm"
echo "the Kestrel logo on the login page, and smoke-test create/revoke as"
echo "platform_admin when ready."

section "13. Final validation verdict"

echo "Summary:"
echo "  - Activation-token API helpers exist; OpenAPI lists list/create/revoke."
echo "  - Appliances page includes Activation Tokens UI with platform_admin gating"
echo "    and the one-time raw-token warning."
echo "  - No console logging of secrets; no raw-token persistence in storage."
echo "  - Brand SVGs are reachable and parseable; login uses mark + onError fallback."
echo "  - backend-api/, postgres/init/, docker-compose.yml, and .env were untouched."
echo "  - Frontend build passed inside the container."
echo
echo "======================================================================"
echo "KB-019 ADMIN ACTIVATION TOKEN UI VALIDATION PASSED"
echo "======================================================================"
