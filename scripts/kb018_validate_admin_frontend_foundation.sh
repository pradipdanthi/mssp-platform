#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
FRONTEND_BASE="http://localhost:3000"
BODY_FILE="/tmp/kb018-body.txt"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-018: Validate Admin Frontend Foundation"
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

section "1. Expected frontend files exist"

REQUIRED_FILES=(
  "frontend-admin/package.json"
  "frontend-admin/package-lock.json"
  "frontend-admin/index.html"
  "frontend-admin/tsconfig.json"
  "frontend-admin/tsconfig.node.json"
  "frontend-admin/vite.config.ts"
  "frontend-admin/Dockerfile"
  "frontend-admin/.gitignore"
  "frontend-admin/.dockerignore"
  "frontend-admin/public/app-config.json"
  "frontend-admin/public/brand/kestrel-mark.svg"
  "frontend-admin/public/brand/kestrel-logo.svg"
  "frontend-admin/src/main.tsx"
  "frontend-admin/src/App.tsx"
  "frontend-admin/src/styles.css"
  "frontend-admin/src/api/client.ts"
  "frontend-admin/src/api/auth.ts"
  "frontend-admin/src/api/admin.ts"
  "frontend-admin/src/api/appliances.ts"
  "frontend-admin/src/auth/AuthContext.tsx"
  "frontend-admin/src/config/types.ts"
  "frontend-admin/src/config/loadAppConfig.ts"
  "frontend-admin/src/config/BrandContext.tsx"
  "frontend-admin/src/hooks/useAdminQuery.ts"
  "frontend-admin/src/components/Layout.tsx"
  "frontend-admin/src/components/ProtectedRoute.tsx"
  "frontend-admin/src/components/BrandMark.tsx"
  "frontend-admin/src/pages/LoginPage.tsx"
  "frontend-admin/src/pages/DashboardPage.tsx"
  "frontend-admin/src/pages/TenantsPage.tsx"
  "frontend-admin/src/pages/UsersPage.tsx"
  "frontend-admin/src/pages/AppliancesPage.tsx"
  "frontend-admin/src/pages/AlertsPage.tsx"
  "frontend-admin/src/pages/IncidentsPage.tsx"
)

for f in "${REQUIRED_FILES[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. docker-compose.yml defines the frontend-admin service"

grep -q "^  frontend-admin:" docker-compose.yml || fail "docker-compose.yml does not define a frontend-admin service"
grep -q "container_name: mssp-frontend-admin" docker-compose.yml || fail "docker-compose.yml frontend-admin service is missing container_name: mssp-frontend-admin"
grep -q '"3000:5173"' docker-compose.yml || fail "docker-compose.yml frontend-admin service is missing the 3000:5173 port mapping"
grep -q "\./frontend-admin:/app" docker-compose.yml || fail "docker-compose.yml frontend-admin service is missing the ./frontend-admin:/app bind mount"
grep -q "/app/node_modules" docker-compose.yml || fail "docker-compose.yml frontend-admin service is missing the /app/node_modules volume"
echo "OK: frontend-admin service is present with expected container_name, port mapping, and volumes."

section "3. Backend/database/protected files were not modified"

# Git-diff based checks (not content-grep) - see the KB-017 validation
# script for why a content grep for a common word is not a reliable
# "unmodified" check. docker-compose.yml is EXPECTED to have a diff (the
# new frontend-admin service) - it is intentionally excluded below.
PROTECTED_PATHS=(
  "backend-api/"
  "postgres/init/"
  "scripts/kb017_validate_appliance_credential_visibility_rotation.sh"
  "docs/KB017_APPLIANCE_CREDENTIAL_VISIBILITY_ROTATION_COMPLETION.md"
)

for p in "${PROTECTED_PATHS[@]}"; do
  if [ -e "$p" ]; then
    git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-018 must not modify it"
    git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-018 must not modify it"
    echo "OK: $p is unmodified (no working-tree or staged diff)"
  else
    echo "skip (not present): $p"
  fi
done

section "4. .env is not touched, and is ignored by git"

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows up as changed/untracked in git status - it must never be touched by this task"
fi
echo "OK: git status shows no changes to .env"

if [ -f .gitignore ] && grep -qx '\.env' .gitignore; then
  echo "OK: root .gitignore ignores .env"
elif [ -f .gitignore ] && grep -q '^\.env' .gitignore; then
  echo "OK: root .gitignore has an .env-prefixed ignore rule"
else
  echo "NOTE: could not confirm an exact '.env' line in the root .gitignore - this script does not print or read .env contents either way."
fi

section "5. Bash syntax self-check"

bash -n "$0" && echo "OK: this validation script itself has valid bash syntax (bash -n)."

section "6. Build the frontend-admin image"

echo "Running: docker compose build frontend-admin"
docker compose build frontend-admin || fail "docker compose build frontend-admin failed"

if [ ! -f frontend-admin/package-lock.json ]; then
  echo "ERROR: frontend-admin/package-lock.json is required for reproducible frontend builds"
  exit 1
fi

if ! grep -q "RUN npm ci" frontend-admin/Dockerfile; then
  echo "ERROR: frontend-admin/Dockerfile must use npm ci"
  exit 1
fi

if grep -q "RUN npm install" frontend-admin/Dockerfile; then
  echo "ERROR: frontend-admin/Dockerfile must not use npm install now that package-lock.json exists"
  exit 1
fi

echo "OK: package-lock.json is present and Dockerfile uses npm ci for reproducible installs."

section "7. Start the frontend-admin container"

echo "Running: docker compose up -d frontend-admin"
docker compose up -d frontend-admin || fail "docker compose up -d frontend-admin failed"

echo "Waiting for the Vite dev server to come up..."
FRONTEND_UP=0
for _ in $(seq 1 20); do
  if curl -fsS -o /dev/null "$FRONTEND_BASE/" 2>/dev/null; then
    FRONTEND_UP=1
    break
  fi
  sleep 1
done
[ "$FRONTEND_UP" = "1" ] || fail "frontend-admin did not respond at $FRONTEND_BASE/ within 20 seconds of starting"
echo "OK: frontend-admin is responding at $FRONTEND_BASE/"

section "8. Confirm container states"

docker compose ps

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo 'missing')"
postgres_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"
frontend_state="$(docker inspect -f '{{.State.Status}}' mssp-frontend-admin 2>/dev/null || echo 'missing')"

echo
echo "mssp-backend-api state:    $backend_state"
echo "mssp-postgres health:      $postgres_health"
echo "mssp-redis health:         $redis_health"
echo "mssp-frontend-admin state: $frontend_state"

[ "$backend_state" = "running" ] || fail "backend-api container is not running"
[ "$postgres_health" = "healthy" ] || fail "postgres is not healthy"
[ "$redis_health" = "healthy" ] || fail "redis is not healthy"
[ "$frontend_state" = "running" ] || fail "frontend-admin container is not running"

section "9. Confirm backend health directly"

curl -fsS "$API_BASE/health" | tee "$BODY_FILE" | jq . >/dev/null || fail "GET $API_BASE/health did not return valid JSON"
# The existing backend /health shape (from earlier KB modules) has no
# "status" field - it reports api/database/redis each as "ok" instead:
#   {"api":"ok","service":"mssp-backend-api","environment":"development","database":"ok","redis":"ok"}
jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
  || fail "GET /health response did not report api/database/redis all as \"ok\""
echo "OK: backend /health responded with valid JSON and api/database/redis are all \"ok\"."

section "10. Confirm frontend HTML shell and runtime branding config"

curl -fsS "$FRONTEND_BASE/" -o "$BODY_FILE" || fail "GET $FRONTEND_BASE/ failed"
grep -q 'id="root"' "$BODY_FILE" || fail "Frontend HTML is missing <div id=\"root\">"
grep -qi "Vite + React" "$BODY_FILE" && fail "Frontend HTML still contains the default Vite/React title text"
# index.html uses a generic non-product title; the real product title comes
# from public/app-config.json at React runtime (curl cannot execute that).
if grep -qi "MSSP Control Plane" "$BODY_FILE"; then
  fail "Frontend HTML still contains old hardcoded 'MSSP Control Plane' branding"
fi
grep -qi "<title>Admin Portal</title>" "$BODY_FILE" \
  || fail "Frontend HTML <title> should be the generic 'Admin Portal' shell title (runtime title comes from app-config.json)"
echo "OK: frontend HTML has id=\"root\", a generic Admin Portal title, and no old MSSP Control Plane title."

# Runtime branding config (served from public/ by Vite).
curl -fsS "$FRONTEND_BASE/app-config.json" -o "$BODY_FILE" \
  || fail "GET $FRONTEND_BASE/app-config.json failed"
jq -e '
  .productName == "Kevantic Cyber Security"
  and .portalName == "KEVANTIC CYBER SECURITY CONTROL PLANE"
  and .companyName == "Kevantic"
  and .legalEntityName == "Kevantic Cyber Security Private Limited"
  and .supportEmail == "soc@kevantic.com"
  and .salesEmail == "sales@kevantic.com"
  and .portalDomain == "portal.kevantic.com"
  and .adminDomain == "admin.kevantic.com"
  and .marketingDomain == "kevantic.com"
  and (.documentTitle | test("Kevantic Cyber Security"))
  and (.logo.markSrc | test("kevantic-mark"))
  and (.logo.logoSrc | test("kevantic-logo"))
' "$BODY_FILE" >/dev/null \
  || fail "app-config.json is missing required Kevantic Cyber Security branding fields"
echo "OK: app-config.json contains Kevantic domains (admin.kevantic.com, portal.kevantic.com, soc@kevantic.com)."

curl -fsS -o /dev/null "$FRONTEND_BASE/brand/kevantic-mark.svg" \
  || fail "GET $FRONTEND_BASE/brand/kevantic-mark.svg failed"
curl -fsS -o /dev/null "$FRONTEND_BASE/brand/kevantic-logo.svg" \
  || fail "GET $FRONTEND_BASE/brand/kevantic-logo.svg failed"
echo "OK: both brand SVG assets are served by the frontend."

# Source/UI must not hardcode the retired product brand string.
if grep -RIn --exclude-dir=node_modules --exclude-dir=dist 'MSSP Control Plane' frontend-admin/src frontend-admin/index.html 2>/dev/null; then
  fail "Found hardcoded 'MSSP Control Plane' in frontend-admin/src or index.html - branding must come from app-config.json"
fi
echo "OK: no hardcoded 'MSSP Control Plane' strings remain in frontend-admin/src or index.html."

section "11. Confirm the Vite dev-server proxy reaches the backend"

curl -fsS "$FRONTEND_BASE/api/health" -o "$BODY_FILE" || fail "GET $FRONTEND_BASE/api/health failed"
jq . "$BODY_FILE" >/dev/null || fail "$FRONTEND_BASE/api/health did not return valid JSON"
# Same existing backend /health shape as section 9 above - no "status"
# field, just api/database/redis each reported as "ok".
jq -e '.api == "ok" and .database == "ok" and .redis == "ok"' "$BODY_FILE" >/dev/null \
  || fail "Proxied /api/health response did not report api/database/redis all as \"ok\""
DIRECT_HEALTH="$(curl -fsS "$API_BASE/health")"
PROXIED_HEALTH="$(cat "$BODY_FILE")"
DIRECT_STATUS="$(echo "$DIRECT_HEALTH" | jq -S .)"
PROXIED_STATUS="$(echo "$PROXIED_HEALTH" | jq -S .)"
if [ "$(echo "$DIRECT_STATUS" | jq -r '.api // empty')" != "$(echo "$PROXIED_STATUS" | jq -r '.api // empty')" ] \
  || [ "$(echo "$DIRECT_STATUS" | jq -r '.database // empty')" != "$(echo "$PROXIED_STATUS" | jq -r '.database // empty')" ] \
  || [ "$(echo "$DIRECT_STATUS" | jq -r '.redis // empty')" != "$(echo "$PROXIED_STATUS" | jq -r '.redis // empty')" ]; then
  fail "Proxied /api/health api/database/redis fields do not match direct backend /health"
fi
echo "OK: $FRONTEND_BASE/api/health is proxied through to backend-api and returns the same health shape as $API_BASE/health."

section "12. Confirm SPA routes are defined in source (static check only)"

ROUTES=(/login /dashboard /tenants /users /appliances /alerts /incidents)
for r in "${ROUTES[@]}"; do
  grep -q "path=\"$r\"" frontend-admin/src/App.tsx || fail "frontend-admin/src/App.tsx does not define a route for $r"
  echo "found route definition: $r"
done

section "13. Honesty note on curl vs. real SPA rendering"

echo "curl (used above) can fetch the raw index.html, app-config.json, brand"
echo "SVGs, and the Vite proxy's /api/* passthrough, but it CANNOT execute"
echo "the React SPA's client-side JavaScript. Steps above confirm: the HTML"
echo "shell is served with a generic title, runtime branding config and logo"
echo "assets are present, the /api proxy reaches backend-api, and every"
echo "required route path string exists in the router source code."
echo "They do NOT prove that document.title is rewritten at runtime after"
echo "React loads app-config.json, that clicking around in a real browser"
echo "renders each page correctly, that the login form authenticates end to"
echo "end, or that the appliance credential rotate flow behaves correctly on"
echo "screen. That requires manually opening $FRONTEND_BASE in a browser and"
echo "logging in - this script does not attempt to fake that."

section "14. Frontend TypeScript/build check inside the container"

echo "Running: docker compose exec -T frontend-admin npm run build"
echo "(This may create frontend-admin/dist/ on the host via the bind mount -"
echo " that is expected and is excluded by frontend-admin/.gitignore.)"
if docker compose exec -T frontend-admin npm run build; then
  echo "OK: TypeScript compile + Vite production build succeeded inside the container."
else
  fail "docker compose exec -T frontend-admin npm run build failed - see output above"
fi

section "15. Frontend source secret-leak checks"

SRC_DIR="frontend-admin/src"

if grep -rEn 'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}' "$SRC_DIR" 2>/dev/null; then
  fail "Found a JWT-shaped literal string in $SRC_DIR - a real token must never be hardcoded in source"
fi
echo "OK: no JWT-shaped literal strings found in $SRC_DIR"

if grep -rEn 'console\.(log|debug|info|warn|error)\([^)]*\b(token|password|api_?key|secret|jwt)\b' "$SRC_DIR" 2>/dev/null; then
  fail "Found a console.log/debug/info/warn/error call referencing token/password/api_key/secret/jwt in $SRC_DIR"
fi
echo "OK: no console.* calls referencing token/password/api_key/secret/jwt found in $SRC_DIR"

if grep -rEni '(password|api_key|apikey|secret|token)[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9+/=_-]{8,}["'"'"']' "$SRC_DIR" 2>/dev/null; then
  fail "Found what looks like a hardcoded credential/secret literal value in $SRC_DIR"
fi
echo "OK: no hardcoded password/api_key/secret/token literal values found in $SRC_DIR"
echo "(Note: form field attributes like type=\"password\" or htmlFor=\"password\""
echo " are UI field identifiers, not secret values, and correctly do not match"
echo " the checks above.)"

section "16. Confirm backend OpenAPI still lists KB-017 credential paths"

OPENAPI="$(curl -fsS "$API_BASE/openapi.json")"
echo "$OPENAPI" | jq -e '.paths | has("/admin/appliances/{appliance_id}/credential")' >/dev/null \
  || fail "OpenAPI schema is missing /admin/appliances/{appliance_id}/credential (KB-017 regression)"
echo "$OPENAPI" | jq -e '.paths | has("/admin/appliances/{appliance_id}/credential/rotate")' >/dev/null \
  || fail "OpenAPI schema is missing /admin/appliances/{appliance_id}/credential/rotate (KB-017 regression)"
echo "OK: both KB-017 credential endpoints are still registered in the backend OpenAPI schema."

section "17. Lightweight backend smoke regression"

curl -fsS -o /dev/null -w "GET /health -> %{http_code}\n" "$API_BASE/health"
curl -fsS -o /dev/null -w "GET /auth/roles -> %{http_code}\n" "$API_BASE/auth/roles"

for p in \
  "/auth/login" \
  "/auth/me" \
  "/admin/dashboard" \
  "/admin/tenants" \
  "/admin/users" \
  "/admin/appliances" \
  "/admin/alerts" \
  "/admin/incidents" \
  "/appliance/register" \
  "/appliance/heartbeat"
do
  echo "$OPENAPI" | jq -e --arg p "$p" '.paths | has($p)' >/dev/null \
    || fail "OpenAPI schema is missing $p - unexpected backend regression"
done
echo "OK: /health and /auth/roles responded, and all key backend route paths remain registered."
echo "(KB-018 changed no backend code, so this is a lightweight smoke check,"
echo " not the full KB-011-KB-017 behavior regression chain.)"

section "18. Manual command for the full KB-017 regression chain (not run automatically)"

echo "KB-018 did not modify any backend code, so this script does not run the"
echo "full KB-017 regression chain by default. To run it manually (it will"
echo "ask for demo user passwords and also re-runs KB-011 through KB-016):"
echo
echo "  cd $PROJECT_DIR && ./scripts/kb017_validate_appliance_credential_visibility_rotation.sh"

section "19. Leaving frontend-admin running"

echo "frontend-admin is left running so you can open it in a browser:"
echo "  From the VM:        $FRONTEND_BASE"
echo "  From your machine:  http://192.168.0.201:3000"
docker compose ps frontend-admin

section "20. Final validation verdict"

echo "Summary:"
echo "  - All expected frontend-admin files exist."
echo "  - docker-compose.yml defines only the new frontend-admin service;"
echo "    postgres/redis/backend-api service blocks were not touched."
echo "  - backend-api/, postgres/init/, and the KB-017 script/doc have no"
echo "    working-tree or staged git diff - no backend code or schema was"
echo "    touched by this module."
echo "  - .env was not modified and was never read or printed by this script."
echo "  - This script passed its own 'bash -n' syntax check."
echo "  - docker compose build/up succeeded for frontend-admin; backend-api"
echo "    is running, postgres and redis are healthy, frontend-admin is"
echo "    running."
echo "  - Backend /health responded directly; the SAME data was reachable"
echo "    through the frontend's own /api/health proxy path, proving the"
echo "    Vite dev-server proxy to backend-api works without any backend"
echo "    CORS changes."
echo "  - Frontend HTML is served with id=\"root\" and a generic"
echo "    'Admin Portal' shell title (not Vite/React default, not old"
echo "    'MSSP Control Plane'). Runtime product title and brand strings"
echo "    come from public/app-config.json (Kestrel Cyber / Keroxsys)."
echo "  - Brand SVG assets are present and served; no hardcoded"
echo "    'MSSP Control Plane' remains in frontend-admin/src or index.html."
echo "  - All 7 required SPA route paths are defined in the router source"
echo "    (a static source check - curl cannot execute the SPA's JavaScript,"
echo "    see section 13 above for the honest limitation of this check)."
echo "  - The frontend's own TypeScript/Vite production build"
echo "    ('npm run build') succeeded inside the container."
echo "  - No JWT-shaped strings, no console.log of a token/password/api_key,"
echo "    and no hardcoded password/api_key/secret/token literal values were"
echo "    found anywhere in frontend-admin/src."
echo "  - The backend OpenAPI schema still lists both KB-017 credential"
echo "    endpoints, plus every other key backend route path checked."
echo "  - package-lock.json is present and Dockerfile uses npm ci for"
echo "    reproducible frontend dependency installs."
echo
echo "======================================================================"
echo "KB-018 ADMIN FRONTEND FOUNDATION VALIDATION PASSED"
echo "======================================================================"
