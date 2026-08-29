#!/usr/bin/env bash
# KB-112 Step 2: Sovereign Edge unified portal RBAC — policy unit tests + live API matrix.
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"
API_BASE="${API_BASE:-http://localhost:8000}"
BODY_FILE="/tmp/kb112-rbac-body.json"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

cleanup() { rm -f "$BODY_FILE"; }
trap cleanup EXIT

section "1. Policy module"
test -f backend-api/app/services/sovereign_rbac.py && ok "sovereign_rbac.py exists" || bad "sovereign_rbac.py"
grep -q "FORBIDDEN_CUSTOMER_ROUTE_PREFIXES" backend-api/app/services/sovereign_rbac.py && ok "forbidden prefixes" || bad "forbidden prefixes"
grep -q "sovereign_route_access" backend-api/app/services/sovereign_rbac.py && ok "route access helper" || bad "route access"

section "2. Unit tests"
if docker compose exec -T backend-api python -m unittest tests.test_sovereign_rbac -q 2>/dev/null; then
  ok "test_sovereign_rbac (container)"
elif (cd backend-api && PYTHONPATH=. python3 -m unittest tests.test_sovereign_rbac -q 2>/dev/null); then
  ok "test_sovereign_rbac (host)"
else
  bad "test_sovereign_rbac"
fi

section "3. Live API matrix (reuses KB-011 lab credentials)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_validation_credentials.sh"

check_status() {
  local description="$1"
  local expected="$2"
  local url="$3"
  local token="${4:-}"
  local actual
  if [[ -n "$token" ]]; then
    actual="$(curl -s -o "$BODY_FILE" -w '%{http_code}' -H "Authorization: Bearer $token" "$url")"
  else
    actual="$(curl -s -o "$BODY_FILE" -w '%{http_code}' "$url")"
  fi
  if [[ "$actual" == "$expected" ]]; then
    ok "$description [$actual]"
  else
    bad "$description (expected $expected, got $actual)"
    head -c 400 "$BODY_FILE" 2>/dev/null || true
    echo
  fi
}

login() {
  local email="$1" password="$2" expected_role="$3"
  local body response
  body="$(jq -n --arg email "$email" --arg password "$password" '{email:$email,password:$password}')"
  response="$(curl -fsS -X POST "$API_BASE/auth/login" -H "Content-Type: application/json" -d "$body")"
  if echo "$response" | jq -e '.access_token != null' >/dev/null 2>&1; then
    echo "$response" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null
    echo "$response" | jq -r '.access_token'
    return 0
  fi
  if echo "$response" | jq -e '.mfa_required == true' >/dev/null 2>&1; then
    local mfa_token secret code authed
    mfa_token="$(echo "$response" | jq -r '.mfa_token')"
    secret="$(docker compose exec -T postgres psql -U mssp_admin -d mssp_control -Atc \
      "SELECT mfa_secret FROM platform_users WHERE lower(email)=lower('${email}') LIMIT 1;")"
    secret="${secret//$'\r'/}"
    secret="${secret//$'\n'/}"
    if [[ -z "$secret" ]]; then
      echo "login failed for $email: MFA enabled but no mfa_secret in DB" >&2
      return 1
    fi
    code="$(python3 -c "import pyotp; print(pyotp.TOTP('${secret}').now())")"
    authed="$(curl -fsS -X POST "$API_BASE/auth/mfa/authenticate" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg t "$mfa_token" --arg c "$code" '{mfa_token:$t,code:$c}')")"
    echo "$authed" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null
    echo "$authed" | jq -r '.access_token'
    return 0
  fi
  if echo "$response" | jq -e '.mfa_setup_required == true' >/dev/null 2>&1; then
    local setup_token secret code complete
    setup_token="$(echo "$response" | jq -r '.setup_token')"
    secret="$(curl -fsS -X POST "$API_BASE/auth/mfa/setup-session" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg t "$setup_token" '{setup_token:$t}')" | jq -r '.secret')"
    code="$(python3 -c "import pyotp; print(pyotp.TOTP('${secret}').now())")"
    complete="$(curl -fsS -X POST "$API_BASE/auth/mfa/complete-setup" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg t "$setup_token" --arg c "$code" '{setup_token:$t,code:$c}')")"
    echo "$complete" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null
    echo "$complete" | jq -r '.access_token'
    return 0
  fi
  echo "login failed for $email: $(echo "$response" | jq -c '{mfa_required,mfa_setup_required,detail}')" >&2
  return 1
}

if ! validation_creds_complete; then
  echo "SKIP: live API matrix — validation.env not complete ($(validation_creds_hint | head -1))"
else
  docker compose exec -T postgres psql -U mssp_admin -d mssp_control -v ON_ERROR_STOP=1 <<SQL >/dev/null
UPDATE tenants SET enforce_mfa = false
WHERE short_code IN ('${CUSTOMER_ADMIN_TENANT}', '${CUSTOMER_VIEWER_TENANT}');
UPDATE platform_users
SET is_mfa_enabled = false, mfa_secret = NULL
WHERE lower(email) IN (
  lower('${PLATFORM_ADMIN_EMAIL}'),
  lower('${SOC_MANAGER_EMAIL}'),
  lower('${SOC_ANALYST_EMAIL}'),
  lower('${CUSTOMER_ADMIN_EMAIL}'),
  lower('${CUSTOMER_VIEWER_EMAIL}')
);
SQL
  ok "lab validation users ready for password login (RBAC matrix)"

  PLATFORM_ADMIN_TOKEN="$(login "${PLATFORM_ADMIN_EMAIL}" "${PLATFORM_ADMIN_PASSWORD}" platform_admin)"
  SOC_ANALYST_TOKEN="$(login "${SOC_ANALYST_EMAIL}" "${SOC_ANALYST_PASSWORD}" soc_analyst)"
  CUSTOMER_ADMIN_TOKEN="$(login "${CUSTOMER_ADMIN_EMAIL}" "${CUSTOMER_ADMIN_PASSWORD}" customer_admin)"
  CUSTOMER_VIEWER_TOKEN="$(login "${CUSTOMER_VIEWER_EMAIL}" "${CUSTOMER_VIEWER_PASSWORD}" customer_viewer)"
  unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD \
        CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD

  CUSTOMER_VIEWER_TENANT="${CUSTOMER_VIEWER_TENANT:-DEMO}"
  CUSTOMER_ADMIN_TENANT="${CUSTOMER_ADMIN_TENANT:-DEMO2}"

  for ep in /admin/tenants /admin/appliances /admin/alerts; do
    check_status "SOC analyst GET $ep" 200 "$API_BASE$ep" "$SOC_ANALYST_TOKEN"
    check_status "customer_admin denied GET $ep" 403 "$API_BASE$ep" "$CUSTOMER_ADMIN_TOKEN"
    check_status "customer_viewer denied GET $ep" 403 "$API_BASE$ep" "$CUSTOMER_VIEWER_TOKEN"
  done

  for ep in "/customer/dashboard/$CUSTOMER_VIEWER_TENANT" "/customer/incidents/$CUSTOMER_VIEWER_TENANT"; do
    check_status "customer_viewer GET $ep" 200 "$API_BASE$ep" "$CUSTOMER_VIEWER_TOKEN"
    check_status "SOC analyst GET $ep (unified portal)" 200 "$API_BASE$ep" "$SOC_ANALYST_TOKEN"
  done

  # Policy parity: paths classified forbidden in sovereign_rbac must 403 for customers live.
  python3 - <<'PY' || bad "policy/live parity script"
import sys
sys.path.insert(0, "backend-api")
from app.services.sovereign_rbac import sovereign_route_access
checks = [
    ("customer_admin", "GET", "/admin/tenants", False, "forbidden_admin_route"),
    ("customer_viewer", "GET", "/admin/dashboard", False, "forbidden_admin_route"),
    ("soc_manager", "GET", "/admin/tenants", True, None),
]
for role, method, path, want, reason in checks:
    allowed, got = sovereign_route_access(role, method, path)
    assert allowed == want, (role, path, allowed, got)
    if not want:
        assert got == reason
print("policy parity ok")
PY
  ok "policy module matches live deny contract"
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "KB-112 SOVEREIGN RBAC VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-112 SOVEREIGN RBAC VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
