#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb015-body.json"

FAKE_APPLIANCE_NAME_1="kb015-validation-appliance-1"
FAKE_APPLIANCE_NAME_2="kb015-validation-appliance-2"
FAKE_TOKEN_SITE_NAME="KB015 Validation Site (fake, safe to delete)"

UUID_REGEX='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-015: Validate Admin Appliance Management API"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent backend-api logs:"
  docker compose logs --tail=80 backend-api || true
  cleanup_fake_data || true
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

# cleanup_fake_data: removes every piece of fake fixture data this script
# creates. Safe to call multiple times (idempotent, ignores "not found").
cleanup_fake_data() {
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM appliance_activation_tokens WHERE site_name = '${FAKE_TOKEN_SITE_NAME}';" >/dev/null 2>&1 || true
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM appliances WHERE appliance_name IN ('${FAKE_APPLIANCE_NAME_1}', '${FAKE_APPLIANCE_NAME_2}');" >/dev/null 2>&1 || true
}

cleanup() {
  rm -f "$BODY_FILE"
  cleanup_fake_data
  unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD \
        CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD \
        PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN \
        CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN \
        ACTIVATION_RAW_TOKEN 2>/dev/null || true
}
trap cleanup EXIT

# psql_scalar <sql>
# Runs a single SQL statement via psql in quiet (-q), tuples-only (-t),
# unaligned (-A) mode, with -X (skip ~/.psqlrc) and ON_ERROR_STOP=1 (a real
# SQL error stops immediately instead of being silently swallowed), and
# returns exactly one trimmed, non-blank line of output.
#
# KB-015 validation bug fix: this replaces the earlier pattern of piping
# `psql -tA -c "INSERT ... RETURNING id;"` straight through
# `tr -d '[:space:]'`. For a non-SELECT statement, psql prints the
# RETURNING value on one line AND a separate command-tag line (e.g.
# "INSERT 0 1") on the next; stripping *all* whitespace - including the
# newline between those two lines - concatenated them into a single
# corrupted string such as "<uuid>INSERT01", which the API correctly
# rejected with a 422 uuid_parsing error. That was a validation-script
# bug, not an API bug. The fix is two-fold: (1) every write query below is
# wrapped as `WITH inserted AS (INSERT ... RETURNING ...) SELECT ... FROM
# inserted;` so the statement psql actually executes is a SELECT, which
# never produces a row-count command tag to begin with, and (2) output
# here is only ever trimmed line-by-line (blank lines dropped, a trailing
# \r stripped) - never merged across lines - and is required to be
# exactly one line, or this function fails loudly instead of returning
# corrupted data.
psql_scalar() {
  local sql="$1"
  local raw

  raw="$(docker compose exec -T postgres psql \
    -X -q -t -A \
    -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "$sql" 2>/dev/null)" || return 1

  raw="$(printf '%s\n' "$raw" | sed 's/\r$//' | grep -v '^[[:space:]]*$' || true)"

  local line_count
  line_count="$(printf '%s\n' "$raw" | grep -c '.' || true)"
  if [ "$line_count" != "1" ]; then
    echo "psql_scalar: expected exactly 1 non-blank output line, got $line_count, for: $sql" >&2
    return 1
  fi

  printf '%s' "$raw"
}

# validate_uuid <value> <label>
# Fails immediately - before any API call is made with it - if $value is
# not a strict, well-formed UUID string. This is the direct safeguard
# against a repeat of the command-tag corruption bug described above:
# even if psql_scalar's own line-count check were somehow bypassed, a
# corrupted id like "<uuid>INSERT01" would still be caught here.
validate_uuid() {
  local value="$1"
  local label="$2"
  if [[ ! "$value" =~ $UUID_REGEX ]]; then
    fail "$label is not a valid UUID (got: '$value') - refusing to call the API with a corrupted id"
  fi
}

# print_body_redacted <body_file>
# Prints a response body for debugging with any sensitive JSON object key's
# value replaced by "<redacted>" - never prints a password, access token,
# activation token, or token hash.
print_body_redacted() {
  local file="$1"
  local redacted
  redacted="$(jq '
      walk(
        if type == "object" then
          with_entries(
            if (.key | ascii_downcase) as $k
               | ($k == "password" or $k == "new_password" or $k == "password_hash"
                  or $k == "access_token" or $k == "token" or $k == "token_hash"
                  or $k == "jwt" or $k == "secret" or $k == "jwt_secret")
            then .value = "<redacted>"
            else .
            end
          )
        else .
        end
      )
    ' "$file" 2>/dev/null)"
  if [ -n "$redacted" ]; then
    echo "$redacted"
  else
    echo "(response body omitted - could not be parsed/redacted safely)"
  fi
}

# response_has_sensitive_string <body_file>
# Fails if the literal strings "token_hash" or "password_hash" appear
# anywhere in the body. Neither string has any legitimate reason to ever
# appear in any response - unlike the word "password"/"token" alone, these
# specific strings never show up in a URL path or a validation error's
# "loc"/"type"/"msg" field, so a plain substring search is safe here.
response_has_sensitive_string() {
  local file="$1"
  grep -qi "token_hash" "$file" 2>/dev/null && return 0
  grep -qi "password_hash" "$file" 2>/dev/null && return 0
  return 1
}

# response_has_raw_activation_token <body_file>
# Fails if the one-time raw activation token (captured earlier into
# ACTIVATION_RAW_TOKEN, once it exists) appears anywhere in the given body.
# Called on every check *after* token creation - the creation response
# itself is verified separately, before this variable is set.
response_has_raw_activation_token() {
  local file="$1"
  [ -n "${ACTIVATION_RAW_TOKEN:-}" ] || return 1
  grep -qF -- "$ACTIVATION_RAW_TOKEN" "$file" 2>/dev/null
}

# check_status <description> <expected_http_code> <method> <url> [token] [json_body]
check_status() {
  local description="$1"
  local expected="$2"
  local method="$3"
  local url="$4"
  local token="${5:-}"
  local body="${6:-}"
  local actual
  local args=(-s -o "$BODY_FILE" -w '%{http_code}' -X "$method")

  if [ -n "$token" ]; then
    args+=(-H "Authorization: Bearer $token")
  fi
  if [ -n "$body" ]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi

  actual="$(curl "${args[@]}" "$url")"

  if [ "$actual" = "$expected" ]; then
    echo "OK   [$actual] $description"
  else
    echo "FAIL [$actual, expected $expected] $description"
    echo "Response body (redacted):"
    print_body_redacted "$BODY_FILE"
    echo
    fail "$description expected HTTP $expected but got $actual"
  fi

  if response_has_sensitive_string "$BODY_FILE"; then
    fail "$description leaked the string token_hash or password_hash in the response body"
  fi
  if response_has_raw_activation_token "$BODY_FILE"; then
    fail "$description leaked the raw activation token in the response body"
  fi
}

section "1. File checks"

for f in \
  backend-api/app/schemas/appliances.py \
  backend-api/app/api/routes/appliance_management.py \
  backend-api/app/api/routes/admin.py \
  backend-api/app/api/routes/tenant_management.py \
  backend-api/app/api/routes/user_management.py
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q '@router.get("/appliances")' backend-api/app/api/routes/admin.py \
  || fail "admin.py no longer defines GET /appliances - existing endpoint may have been modified"
echo "OK: admin.py still defines the original GET /appliances handler"

grep -q "appliance_management_router" backend-api/app/main.py \
  || fail "main.py does not include appliance_management_router"
echo "OK: main.py includes appliance_management_router"

section "2. Docker Compose and service health"

docker compose ps

backend_state="$(docker inspect -f '{{.State.Status}}' mssp-backend-api 2>/dev/null || echo 'missing')"
postgres_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-postgres 2>/dev/null || echo 'missing')"
redis_health="$(docker inspect -f '{{.State.Health.Status}}' mssp-redis 2>/dev/null || echo 'missing')"

echo
echo "mssp-backend-api state: $backend_state"
echo "mssp-postgres health:   $postgres_health"
echo "mssp-redis health:      $redis_health"

[ "$backend_state" = "running" ] || fail "backend-api container is not running (did you rebuild it after this change?)"
[ "$postgres_health" = "healthy" ] || fail "postgres is not healthy"
[ "$redis_health" = "healthy" ] || fail "redis is not healthy"

section "3. Public endpoints must remain public; existing /admin/appliances stays protected"

check_status "GET /health (public)" 200 GET "$API_BASE/health"
check_status "GET /auth/roles (public)" 200 GET "$API_BASE/auth/roles"
check_status "GET /docs (public, dev docs)" 200 GET "$API_BASE/docs"
check_status "GET /admin/appliances with no token (existing endpoint, must still be protected)" 401 GET "$API_BASE/admin/appliances"

section "4. Enter demo passwords (input hidden, never logged)"

read -rs -p "Enter the password for platform.admin@example.local: " PLATFORM_ADMIN_PASSWORD
echo
read -rs -p "Enter the password for soc.manager@example.local: " SOC_MANAGER_PASSWORD
echo
read -rs -p "Enter the password for soc.analyst@example.local: " SOC_ANALYST_PASSWORD
echo
read -rs -p "Enter the password for customer.admin@demo2.local: " CUSTOMER_ADMIN_PASSWORD
echo
read -rs -p "Enter the password for customer.viewer@demo.local: " CUSTOMER_VIEWER_PASSWORD
echo

for pw_name in PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD; do
  [ -n "${!pw_name}" ] || fail "$pw_name cannot be empty."
done

section "5. Logging in as all 5 roles"

login() {
  local email="$1"
  local password="$2"
  local expected_role="$3"
  local body
  body="$(jq -n --arg email "$email" --arg password "$password" '{email:$email,password:$password}')"
  local response
  response="$(curl -fsS -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "$body")"
  echo "$response" | jq 'del(.access_token)' >&2
  echo "$response" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null \
    || fail "Login for $email did not return expected role $expected_role"
  echo "$response" | grep -qi "password_hash" && fail "Login response for $email leaked password_hash"
  echo "$response" | jq -r '.access_token'
}

echo "Logging in as platform_admin..."
PLATFORM_ADMIN_TOKEN="$(login "platform.admin@example.local" "$PLATFORM_ADMIN_PASSWORD" "platform_admin")"

echo "Logging in as soc_manager..."
SOC_MANAGER_TOKEN="$(login "soc.manager@example.local" "$SOC_MANAGER_PASSWORD" "soc_manager")"

echo "Logging in as soc_analyst..."
SOC_ANALYST_TOKEN="$(login "soc.analyst@example.local" "$SOC_ANALYST_PASSWORD" "soc_analyst")"

echo "Logging in as customer_admin (tenant DEMO2)..."
CUSTOMER_ADMIN_TOKEN="$(login "customer.admin@demo2.local" "$CUSTOMER_ADMIN_PASSWORD" "customer_admin")"

echo "Logging in as customer_viewer (tenant DEMO)..."
CUSTOMER_VIEWER_TOKEN="$(login "customer.viewer@demo.local" "$CUSTOMER_VIEWER_PASSWORD" "customer_viewer")"

unset PLATFORM_ADMIN_PASSWORD SOC_MANAGER_PASSWORD SOC_ANALYST_PASSWORD CUSTOMER_ADMIN_PASSWORD CUSTOMER_VIEWER_PASSWORD

for tok_name in PLATFORM_ADMIN_TOKEN SOC_MANAGER_TOKEN SOC_ANALYST_TOKEN CUSTOMER_ADMIN_TOKEN CUSTOMER_VIEWER_TOKEN; do
  [ -n "${!tok_name}" ] || fail "$tok_name was not obtained - login must have failed."
done

echo "All 5 logins succeeded and returned tokens (not displayed)."

section "6. Resolve an existing tenant id (DEMO)"

DEMO_LOOKUP="$(curl -fsS -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" "$API_BASE/admin/tenants")"
DEMO_TENANT_ID="$(echo "$DEMO_LOOKUP" | jq -r '.tenants[] | select(.short_code=="DEMO") | .id')"
[ -n "$DEMO_TENANT_ID" ] && [ "$DEMO_TENANT_ID" != "null" ] || fail "Could not resolve tenant id for short_code DEMO from GET /admin/tenants"
echo "Resolved DEMO tenant id: $DEMO_TENANT_ID"

section "7. Create fake validation appliances (direct SQL fixtures)"

cleanup_fake_data

FAKE_APPLIANCE_ID_1="$(psql_scalar "WITH inserted AS (
  INSERT INTO appliances (tenant_id, appliance_name, site_name, status)
  VALUES ('${DEMO_TENANT_ID}', '${FAKE_APPLIANCE_NAME_1}', 'KB015 Validation Site', 'registered')
  RETURNING id::text
) SELECT id FROM inserted;")" || fail "Could not create fake validation appliance 1 (psql error - see output above)"
validate_uuid "$FAKE_APPLIANCE_ID_1" "FAKE_APPLIANCE_ID_1"
echo "Created fake validation appliance 1: $FAKE_APPLIANCE_ID_1"

FAKE_APPLIANCE_ID_2="$(psql_scalar "WITH inserted AS (
  INSERT INTO appliances (tenant_id, appliance_name, site_name, status)
  VALUES ('${DEMO_TENANT_ID}', '${FAKE_APPLIANCE_NAME_2}', 'KB015 Validation Site', 'registered')
  RETURNING id::text
) SELECT id FROM inserted;")" || fail "Could not create fake validation appliance 2 (psql error - see output above)"
validate_uuid "$FAKE_APPLIANCE_ID_2" "FAKE_APPLIANCE_ID_2"
echo "Created fake validation appliance 2: $FAKE_APPLIANCE_ID_2"

section "8. New endpoints must return 401 with no/garbage token"

check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID_1 with no token" 401 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1"
check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID_1 with garbage token" 401 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "not-a-real-token"
check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 with no token" 401 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "" '{"site_name":"x"}'
check_status "POST .../appliance-activation-tokens with no token" 401 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "" '{"site_name":"x"}'
check_status "GET .../appliance-activation-tokens with no token" 401 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens"
check_status "PATCH .../revoke with no token" 401 PATCH "$API_BASE/admin/appliance-activation-tokens/00000000-0000-0000-0000-000000000000/revoke"
check_status "PATCH .../revoke with garbage token" 401 PATCH "$API_BASE/admin/appliance-activation-tokens/00000000-0000-0000-0000-000000000000/revoke" "not-a-real-token"

section "9. Customer roles must be denied with 403 on all new endpoints"

for CTOK in "$CUSTOMER_VIEWER_TOKEN" "$CUSTOMER_ADMIN_TOKEN"; do
  check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID_1 as customer role (must be denied)" 403 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$CTOK"
  check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 as customer role (must be denied)" 403 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$CTOK" '{"site_name":"x"}'
  check_status "POST .../appliance-activation-tokens as customer role (must be denied)" 403 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$CTOK" '{"site_name":"x"}'
  check_status "GET .../appliance-activation-tokens as customer role (must be denied)" 403 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$CTOK"
  check_status "PATCH .../revoke as customer role (must be denied)" 403 PATCH "$API_BASE/admin/appliance-activation-tokens/00000000-0000-0000-0000-000000000000/revoke" "$CTOK"
done

section "10. soc_manager and soc_analyst can read appliance detail and token list"

check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID_1 as soc_manager" 200 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$SOC_MANAGER_TOKEN"
check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID_1 as soc_analyst" 200 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$SOC_ANALYST_TOKEN"
check_status "GET .../appliance-activation-tokens as soc_manager" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$SOC_MANAGER_TOKEN"
check_status "GET .../appliance-activation-tokens as soc_analyst" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$SOC_ANALYST_TOKEN"

section "11. soc_manager and soc_analyst cannot write (403)"

for STOK in "$SOC_MANAGER_TOKEN" "$SOC_ANALYST_TOKEN"; do
  check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 as soc role (must be denied)" 403 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$STOK" '{"site_name":"x"}'
  check_status "POST .../appliance-activation-tokens as soc role (must be denied)" 403 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$STOK" '{"site_name":"x"}'
  check_status "PATCH .../revoke as soc role (must be denied)" 403 PATCH "$API_BASE/admin/appliance-activation-tokens/00000000-0000-0000-0000-000000000000/revoke" "$STOK"
done

section "12. Invalid UUID path parameters must be a clean 422"

check_status "GET /admin/appliances/not-a-uuid as platform_admin" 422 GET "$API_BASE/admin/appliances/not-a-uuid" "$PLATFORM_ADMIN_TOKEN"
check_status "PATCH /admin/appliances/not-a-uuid as platform_admin" 422 PATCH "$API_BASE/admin/appliances/not-a-uuid" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"x"}'
check_status "POST /admin/tenants/not-a-uuid/appliance-activation-tokens as platform_admin" 422 POST "$API_BASE/admin/tenants/not-a-uuid/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"x"}'
check_status "GET /admin/tenants/not-a-uuid/appliance-activation-tokens as platform_admin" 422 GET "$API_BASE/admin/tenants/not-a-uuid/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN"
check_status "PATCH /admin/appliance-activation-tokens/not-a-uuid/revoke as platform_admin" 422 PATCH "$API_BASE/admin/appliance-activation-tokens/not-a-uuid/revoke" "$PLATFORM_ADMIN_TOKEN"

section "13. Unknown valid UUID must be a clean 404"

check_status "GET /admin/appliances/<unknown uuid> as platform_admin" 404 GET "$API_BASE/admin/appliances/00000000-0000-0000-0000-000000000000" "$PLATFORM_ADMIN_TOKEN"
check_status "PATCH /admin/appliances/<unknown uuid> as platform_admin" 404 PATCH "$API_BASE/admin/appliances/00000000-0000-0000-0000-000000000000" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"x"}'
check_status "POST /admin/tenants/<unknown uuid>/appliance-activation-tokens as platform_admin" 404 POST "$API_BASE/admin/tenants/00000000-0000-0000-0000-000000000000/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"x"}'
check_status "GET /admin/tenants/<unknown uuid>/appliance-activation-tokens as platform_admin" 404 GET "$API_BASE/admin/tenants/00000000-0000-0000-0000-000000000000/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN"
check_status "PATCH /admin/appliance-activation-tokens/<unknown uuid>/revoke as platform_admin" 404 PATCH "$API_BASE/admin/appliance-activation-tokens/00000000-0000-0000-0000-000000000000/revoke" "$PLATFORM_ADMIN_TOKEN"

section "14. platform_admin can GET appliance detail"

check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID_1 as platform_admin" 200 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$PLATFORM_ADMIN_TOKEN"
jq -e --arg name "$FAKE_APPLIANCE_NAME_1" '.appliance_name == $name' "$BODY_FILE" >/dev/null \
  || fail "Appliance detail response did not return the expected appliance_name"
jq -e '.status == "registered"' "$BODY_FILE" >/dev/null || fail "Appliance detail response did not return status=registered"
jq -e '.protected_assets == 0' "$BODY_FILE" >/dev/null || fail "Appliance detail response should report protected_assets == 0 for a brand-new fake appliance"

section "15. platform_admin can PATCH appliance metadata/status"

check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 (update site_name+status) as platform_admin" 200 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"KB015 Validation Site (updated)","status":"maintenance"}'
jq -e '.site_name == "KB015 Validation Site (updated)"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist the site_name change"
jq -e '.status == "maintenance"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist the status change"

section "16. Invalid appliance PATCH payloads must be rejected with 422"

check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 empty body" 422 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$PLATFORM_ADMIN_TOKEN" '{}'
check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 invalid status" 422 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$PLATFORM_ADMIN_TOKEN" '{"status":"not_a_real_status"}'

section "17. Duplicate appliance_name within the same tenant must return a clean 409"

check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID_1 rename to appliance-2's name (must conflict)" 409 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID_1" "$PLATFORM_ADMIN_TOKEN" "{\"appliance_name\":\"$FAKE_APPLIANCE_NAME_2\"}"

section "18. Invalid activation token creation payloads must be rejected with 422"

check_status "POST .../appliance-activation-tokens missing site_name" 422 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" '{}'
check_status "POST .../appliance-activation-tokens expires_in_hours too low" 422 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"x","expires_in_hours":0}'
check_status "POST .../appliance-activation-tokens expires_in_hours too high" 422 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" '{"site_name":"x","expires_in_hours":721}'

section "19. platform_admin can create a clearly fake activation token for DEMO tenant"

CREATE_TOKEN_BODY="$(jq -n --arg site "$FAKE_TOKEN_SITE_NAME" '{site_name: $site, expires_in_hours: 24}')"
check_status "POST .../appliance-activation-tokens as platform_admin" 201 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" "$CREATE_TOKEN_BODY"

ACTIVATION_RAW_TOKEN="$(jq -r '.token' "$BODY_FILE")"
[ -n "$ACTIVATION_RAW_TOKEN" ] && [ "$ACTIVATION_RAW_TOKEN" != "null" ] || fail "Token creation response did not include a raw token"
echo "Raw activation token received (not displayed) and stored only in a shell variable for leak-checking."

FAKE_TOKEN_ID="$(jq -r '.metadata.id' "$BODY_FILE")"
[ -n "$FAKE_TOKEN_ID" ] && [ "$FAKE_TOKEN_ID" != "null" ] || fail "Token creation response did not include metadata.id"
echo "Created fake validation activation token id: $FAKE_TOKEN_ID"

jq -e --arg site "$FAKE_TOKEN_SITE_NAME" '.metadata.site_name == $site' "$BODY_FILE" >/dev/null || fail "Token metadata.site_name did not match"
jq -e '.metadata.status == "pending"' "$BODY_FILE" >/dev/null || fail "Newly created token should have status=pending"
jq -e '.metadata.token_hint != null and (.metadata.token_hint | length) > 0' "$BODY_FILE" >/dev/null || fail "Token metadata.token_hint was missing/empty"
jq -e 'has("metadata") and (.metadata | has("token_hash") | not)' "$BODY_FILE" >/dev/null || fail "Token creation response's metadata must not have a token_hash key"

section "20. Listing activation tokens must expose metadata only, never the raw token or hash"

check_status "GET .../appliance-activation-tokens as platform_admin (list)" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN"
jq -e --arg id "$FAKE_TOKEN_ID" '.tokens[] | select(.id == $id)' "$BODY_FILE" >/dev/null || fail "Fake validation token was not found in the tenant's token list"
jq -e --arg id "$FAKE_TOKEN_ID" '[.tokens[] | select(.id == $id)][0] | has("token") or has("token_hash") | not' "$BODY_FILE" >/dev/null \
  || fail "Token list entry must not have a token or token_hash key"

section "21. Revoke works for a pending token"

check_status "PATCH .../revoke as platform_admin (first revoke)" 200 PATCH "$API_BASE/admin/appliance-activation-tokens/$FAKE_TOKEN_ID/revoke" "$PLATFORM_ADMIN_TOKEN"
jq -e '.status == "revoked"' "$BODY_FILE" >/dev/null || fail "Revoke did not persist status=revoked"
jq -e 'has("token") or has("token_hash") | not' "$BODY_FILE" >/dev/null || fail "Revoke response must not have a token or token_hash key"

section "22. Revoking the same token again must return a clean 409"

check_status "PATCH .../revoke as platform_admin (second revoke, must conflict)" 409 PATCH "$API_BASE/admin/appliance-activation-tokens/$FAKE_TOKEN_ID/revoke" "$PLATFORM_ADMIN_TOKEN"

section "23. Clean up fake validation appliances and activation token"

cleanup_fake_data

REMAINING_APPLIANCES="$(psql_scalar "SELECT count(*) FROM appliances WHERE appliance_name IN ('${FAKE_APPLIANCE_NAME_1}', '${FAKE_APPLIANCE_NAME_2}');")" \
  || fail "Could not verify fake validation appliance cleanup (psql error)"
[ "$REMAINING_APPLIANCES" = "0" ] || fail "Fake validation appliances were not cleaned up (found $REMAINING_APPLIANCES rows)"

REMAINING_TOKENS="$(psql_scalar "SELECT count(*) FROM appliance_activation_tokens WHERE site_name = '${FAKE_TOKEN_SITE_NAME}';")" \
  || fail "Could not verify fake validation activation token cleanup (psql error)"
[ "$REMAINING_TOKENS" = "0" ] || fail "Fake validation activation token was not cleaned up (found $REMAINING_TOKENS rows)"

echo "OK: all fake validation appliance/activation-token fixtures removed, no leftover data."

section "24. Behavior regression gate: scripts/kb014_validate_admin_user_management.sh"

echo "Running the full, unmodified KB-014 validation script now (which itself"
echo "reruns KB-013, and through it KB-012 and KB-011). It will ask for the 5"
echo "demo passwords again."
echo

if ! ./scripts/kb014_validate_admin_user_management.sh; then
  fail "scripts/kb014_validate_admin_user_management.sh did not pass after adding appliance management - this is a real regression"
fi

section "25. Final validation verdict"

echo "KB-015 ADMIN APPLIANCE MANAGEMENT VALIDATION PASSED"
echo
echo "Summary:"
echo "  - /health, /auth/roles, /docs remain public."
echo "  - Existing GET /admin/appliances still requires a valid token (401 enforced, unmodified)."
echo "  - GET/PATCH /admin/appliances/{id} and the activation-token endpoints all require a valid token (401 enforced)."
echo "  - Customer roles are denied with 403 on all 5 new endpoints."
echo "  - soc_manager/soc_analyst can read appliance detail and token lists but cannot write (403)."
echo "  - platform_admin can read/update appliance metadata (appliance_name/site_name/status only)."
echo "  - Invalid UUID path parameters return a clean 422, never a raw DB error; unknown valid UUIDs return a clean 404."
echo "  - Duplicate appliance_name within the same tenant returns a clean 409."
echo "  - platform_admin can create an activation token; the raw token appeared exactly once, in the creation response."
echo "  - No response ever contained token_hash, the raw activation token (outside its one creation response), or password_hash."
echo "  - Revoke worked for a pending token; revoking the same token again returned a clean 409."
echo "  - All fake validation appliance/activation-token fixtures were cleaned up - no leftover data."
echo "  - scripts/kb014_validate_admin_user_management.sh passed unmodified - no observable"
echo "    behavior change to user management, tenant management, route structure, auth, RBAC,"
echo "    tenant isolation, or validation-error redaction."
echo
echo "======================================================================"
echo "KB-015 validation completed successfully."
echo "======================================================================"
