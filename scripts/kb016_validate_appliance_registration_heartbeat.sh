#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
API_BASE="http://localhost:8000"
BODY_FILE="/tmp/kb016-body.json"

FAKE_APPLIANCE_NAME="kb016-validation-appliance"
FAKE_TOKEN_SITE_NAME="KB016 Validation Site (fake, safe to delete)"

UUID_REGEX='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-016: Validate Appliance Registration and Heartbeat Receiver"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1"
  echo "Recent backend-api logs (best-effort redacted, never trust logs to contain secrets in the first place):"
  docker compose logs --tail=80 backend-api 2>/dev/null | sed -E \
    -e 's/("?(activation_token|appliance_api_key|api_key|password|new_password|token|secret)"?[[:space:]]*[:=][[:space:]]*)("[^"]*"|[^,}[:space:]]+)/\1"<redacted>"/gI' \
    || true
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
# Deleting the fake appliance cascades to its appliance_heartbeats rows
# (ON DELETE CASCADE, see postgres/init/001_mssp_core_schema.sql).
cleanup_fake_data() {
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM appliances WHERE appliance_name = '${FAKE_APPLIANCE_NAME}';" >/dev/null 2>&1 || true
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-mssp_admin}" -d "${POSTGRES_DB:-mssp_control}" \
    -c "DELETE FROM appliance_activation_tokens WHERE site_name = '${FAKE_TOKEN_SITE_NAME}';" >/dev/null 2>&1 || true
}

cleanup() {
  rm -f "$BODY_FILE"
  cleanup_fake_data
  unset PLATFORM_ADMIN_PASSWORD PLATFORM_ADMIN_TOKEN ACTIVATION_RAW_TOKEN \
        APPLIANCE_RAW_API_KEY FAKE_APPLIANCE_ID FAKE_TOKEN_ID DEMO_TENANT_ID 2>/dev/null || true
}
trap cleanup EXIT

# psql_scalar <sql>
# Same fixed pattern introduced in scripts/kb015_validate_admin_appliance_management.sh:
# quiet/tuples-only/unaligned psql output, trimmed line-by-line, and it is a
# hard failure if the statement does not produce exactly one non-blank
# output line. For any write statement this is called with, the query text
# itself must be a SELECT (e.g. `WITH inserted AS (INSERT ... RETURNING
# ...) SELECT ... FROM inserted;`) so psql never prints a row-count command
# tag that could get concatenated onto the value.
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
# Fails immediately - before any API/SQL call is made with it - if $value
# is not a strict, well-formed UUID string.
validate_uuid() {
  local value="$1"
  local label="$2"
  if [[ ! "$value" =~ $UUID_REGEX ]]; then
    fail "$label is not a valid UUID (got: '$value') - refusing to use a corrupted id"
  fi
}

# print_body_redacted <body_file>
# Prints a response body for debugging with any sensitive JSON object key's
# value replaced by "<redacted>" - never prints a password, access token,
# activation token, appliance API key, or any hash.
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
                  or $k == "activation_token" or $k == "appliance_api_key"
                  or $k == "appliance_api_key_hash" or $k == "api_key"
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
# Fails if a hash/secret-shaped field name appears anywhere in the body.
# None of these strings has any legitimate reason to ever appear in any
# response.
response_has_sensitive_string() {
  local file="$1"
  grep -qi "token_hash" "$file" 2>/dev/null && return 0
  grep -qi "password_hash" "$file" 2>/dev/null && return 0
  grep -qi "appliance_api_key_hash" "$file" 2>/dev/null && return 0
  return 1
}

# response_has_raw_activation_token <body_file>
# Fails if the one-time raw activation token (captured into
# ACTIVATION_RAW_TOKEN once it exists) appears anywhere in the given body.
response_has_raw_activation_token() {
  local file="$1"
  [ -n "${ACTIVATION_RAW_TOKEN:-}" ] || return 1
  grep -qF -- "$ACTIVATION_RAW_TOKEN" "$file" 2>/dev/null
}

# response_has_raw_appliance_api_key <body_file>
# Fails if the one-time raw appliance API key (captured into
# APPLIANCE_RAW_API_KEY once it exists) appears anywhere in the given body.
response_has_raw_appliance_api_key() {
  local file="$1"
  [ -n "${APPLIANCE_RAW_API_KEY:-}" ] || return 1
  grep -qF -- "$APPLIANCE_RAW_API_KEY" "$file" 2>/dev/null
}

# check_status <description> <expected_http_code> <method> <url> [token] [json_body]
# For human-JWT-authenticated calls (Authorization: Bearer <token>) and for
# POST /appliance/register (no auth header at all - pass "" for token).
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
    fail "$description leaked a sensitive hash string in the response body"
  fi
  if response_has_raw_activation_token "$BODY_FILE"; then
    fail "$description leaked the raw activation token in the response body"
  fi
  if response_has_raw_appliance_api_key "$BODY_FILE"; then
    fail "$description leaked the raw appliance API key in the response body"
  fi
}

# check_appliance_status <description> <expected_http_code> <appliance_id_header> <api_key_header> <json_body>
# For POST /appliance/heartbeat, which authenticates via
# X-Appliance-ID/X-Appliance-API-Key headers instead of Authorization.
# Pass "" for either header value to omit it entirely.
check_appliance_status() {
  local description="$1"
  local expected="$2"
  local aid_header="$3"
  local akey_header="$4"
  local body="$5"
  local actual
  local args=(-s -o "$BODY_FILE" -w '%{http_code}' -X POST -H "Content-Type: application/json")

  if [ -n "$aid_header" ]; then
    args+=(-H "X-Appliance-ID: $aid_header")
  fi
  if [ -n "$akey_header" ]; then
    args+=(-H "X-Appliance-API-Key: $akey_header")
  fi
  args+=(-d "$body")

  actual="$(curl "${args[@]}" "$API_BASE/appliance/heartbeat")"

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
    fail "$description leaked a sensitive hash string in the response body"
  fi
  if response_has_raw_activation_token "$BODY_FILE"; then
    fail "$description leaked the raw activation token in the response body"
  fi
  if response_has_raw_appliance_api_key "$BODY_FILE"; then
    fail "$description leaked the raw appliance API key in the response body"
  fi
}

section "1. File checks"

for f in \
  postgres/init/003_kb016_appliance_registration_heartbeat.sql \
  scripts/kb016_create_appliance_registration_heartbeat.sh \
  backend-api/app/schemas/appliance_agent.py \
  backend-api/app/services/appliance_auth_service.py \
  backend-api/app/api/routes/appliance_agent.py
do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

grep -q "appliance_agent_router" backend-api/app/main.py \
  || fail "main.py does not include appliance_agent_router"
echo "OK: main.py includes appliance_agent_router"

grep -q "def db_transaction" backend-api/app/db/session.py \
  || fail "db/session.py does not define db_transaction()"
echo "OK: db/session.py defines db_transaction()"

grep -q '"activation_token"' backend-api/app/core/error_handlers.py \
  || fail "error_handlers.py SENSITIVE_KEYS does not include activation_token"
grep -q '"appliance_api_key"' backend-api/app/core/error_handlers.py \
  || fail "error_handlers.py SENSITIVE_KEYS does not include appliance_api_key"
grep -q '"api_key"' backend-api/app/core/error_handlers.py \
  || fail "error_handlers.py SENSITIVE_KEYS does not include api_key"
echo "OK: error_handlers.py SENSITIVE_KEYS extended for KB-016 fields"

grep -q '@router.get("/appliances")' backend-api/app/api/routes/admin.py \
  || fail "admin.py no longer defines GET /appliances - existing endpoint may have been modified"
echo "OK: admin.py still defines the original GET /appliances handler (unmodified)"

section "2. Verify KB-016 database migration has been applied"

MIGRATION_COLUMN_COUNT="$(psql_scalar "SELECT count(*) FROM information_schema.columns WHERE table_name='appliances' AND column_name IN ('appliance_api_key_hash','appliance_api_key_hint','appliance_key_created_at','appliance_key_last_used_at');")" \
  || fail "Could not check appliances table columns (psql error)"
if [ "$MIGRATION_COLUMN_COUNT" != "4" ]; then
  fail "KB-016 migration has not been applied (found $MIGRATION_COLUMN_COUNT/4 expected columns on appliances). Run ./scripts/kb016_create_appliance_registration_heartbeat.sh first."
fi
echo "OK: all 4 KB-016 appliance credential columns exist."

MIGRATION_CONSTRAINT_COUNT="$(psql_scalar "SELECT count(*) FROM pg_constraint WHERE conname='appliances_appliance_api_key_hash_key';")" \
  || fail "Could not check appliances unique constraint (psql error)"
[ "$MIGRATION_CONSTRAINT_COUNT" = "1" ] || fail "KB-016 unique constraint appliances_appliance_api_key_hash_key is missing. Run ./scripts/kb016_create_appliance_registration_heartbeat.sh first."
echo "OK: unique constraint appliances_appliance_api_key_hash_key exists."

section "3. Docker Compose and service health"

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

section "4. Public endpoints must remain public"

check_status "GET /health (public)" 200 GET "$API_BASE/health"
check_status "GET /auth/roles (public)" 200 GET "$API_BASE/auth/roles"
check_status "GET /docs (public, dev docs)" 200 GET "$API_BASE/docs"

section "5. Enter platform_admin password (input hidden, never logged)"

read -rs -p "Enter the password for platform.admin@example.local: " PLATFORM_ADMIN_PASSWORD
echo
[ -n "$PLATFORM_ADMIN_PASSWORD" ] || fail "PLATFORM_ADMIN_PASSWORD cannot be empty."

section "6. Logging in as platform_admin"

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
  echo "$response" | jq -e --arg role "$expected_role" '.user.role == $role' >/dev/null \
    || fail "Login for $email did not return expected role $expected_role"
  echo "$response" | grep -qi "password_hash" && fail "Login response for $email leaked password_hash"
  echo "$response" | jq -r '.access_token'
}

PLATFORM_ADMIN_TOKEN="$(login "platform.admin@example.local" "$PLATFORM_ADMIN_PASSWORD" "platform_admin")"
unset PLATFORM_ADMIN_PASSWORD

[ -n "$PLATFORM_ADMIN_TOKEN" ] || fail "PLATFORM_ADMIN_TOKEN was not obtained - login must have failed."
echo "Login succeeded (token not displayed)."

section "7. Resolve an existing tenant id (DEMO)"

DEMO_LOOKUP="$(curl -fsS -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" "$API_BASE/admin/tenants")"
DEMO_TENANT_ID="$(echo "$DEMO_LOOKUP" | jq -r '.tenants[] | select(.short_code=="DEMO") | .id')"
[ -n "$DEMO_TENANT_ID" ] && [ "$DEMO_TENANT_ID" != "null" ] || fail "Could not resolve tenant id for short_code DEMO from GET /admin/tenants"
validate_uuid "$DEMO_TENANT_ID" "DEMO_TENANT_ID"
echo "Resolved DEMO tenant id: $DEMO_TENANT_ID"

section "8. POST /appliance/register input validation"

MISSING_TOKEN_BODY='{"appliance_name":"kb016-missing-token-test"}'
check_status "POST /appliance/register missing activation_token" 422 POST "$API_BASE/appliance/register" "" "$MISSING_TOKEN_BODY"

GARBAGE_TOKEN_BODY="$(jq -n --arg name "kb016-garbage-token-test" '{activation_token:"this-is-not-a-real-activation-token-value", appliance_name: $name}')"
check_status "POST /appliance/register with garbage activation_token" 401 POST "$API_BASE/appliance/register" "" "$GARBAGE_TOKEN_BODY"

section "9. platform_admin creates a fake activation token for DEMO tenant (KB-015 admin API)"

cleanup_fake_data

CREATE_TOKEN_BODY="$(jq -n --arg site "$FAKE_TOKEN_SITE_NAME" '{site_name: $site, expires_in_hours: 24}')"
check_status "POST .../appliance-activation-tokens as platform_admin" 201 POST "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN" "$CREATE_TOKEN_BODY"

ACTIVATION_RAW_TOKEN="$(jq -r '.token' "$BODY_FILE")"
[ -n "$ACTIVATION_RAW_TOKEN" ] && [ "$ACTIVATION_RAW_TOKEN" != "null" ] || fail "Token creation response did not include a raw token"
echo "Raw activation token received (not displayed) and stored only in a shell variable for leak-checking."

FAKE_TOKEN_ID="$(jq -r '.metadata.id' "$BODY_FILE")"
[ -n "$FAKE_TOKEN_ID" ] && [ "$FAKE_TOKEN_ID" != "null" ] || fail "Token creation response did not include metadata.id"
validate_uuid "$FAKE_TOKEN_ID" "FAKE_TOKEN_ID"
echo "Created fake validation activation token id: $FAKE_TOKEN_ID"

section "10. POST /appliance/register with the fake raw activation token succeeds"

REGISTER_BODY="$(jq -n --arg token "$ACTIVATION_RAW_TOKEN" --arg name "$FAKE_APPLIANCE_NAME" \
  '{activation_token: $token, appliance_name: $name, agent_version: "kb016-test-1.0.0"}')"
check_status "POST /appliance/register with valid activation token" 201 POST "$API_BASE/appliance/register" "" "$REGISTER_BODY"

section "11. Capture registration response fields (not displayed) and check their shape"

APPLIANCE_RAW_API_KEY="$(jq -r '.appliance_api_key' "$BODY_FILE")"
[ -n "$APPLIANCE_RAW_API_KEY" ] && [ "$APPLIANCE_RAW_API_KEY" != "null" ] || fail "Registration response did not include appliance_api_key"

FAKE_APPLIANCE_ID="$(jq -r '.appliance_id' "$BODY_FILE")"
[ -n "$FAKE_APPLIANCE_ID" ] && [ "$FAKE_APPLIANCE_ID" != "null" ] || fail "Registration response did not include appliance_id"
validate_uuid "$FAKE_APPLIANCE_ID" "FAKE_APPLIANCE_ID"

jq -e --arg name "$FAKE_APPLIANCE_NAME" '.appliance_name == $name' "$BODY_FILE" >/dev/null || fail "Registration response appliance_name mismatch"
jq -e --arg site "$FAKE_TOKEN_SITE_NAME" '.site_name == $site' "$BODY_FILE" >/dev/null || fail "Registration response site_name did not come from the activation token"
jq -e --arg tenant "$DEMO_TENANT_ID" '.tenant_id == $tenant' "$BODY_FILE" >/dev/null || fail "Registration response tenant_id did not come from the activation token"
jq -e '.tenant_short_code == "DEMO"' "$BODY_FILE" >/dev/null || fail "Registration response tenant_short_code mismatch"
jq -e '.status == "registered"' "$BODY_FILE" >/dev/null || fail "Registration response status should be 'registered'"
jq -e '.appliance_uuid != null and (.appliance_uuid | length) > 0' "$BODY_FILE" >/dev/null || fail "Registration response appliance_uuid was missing/empty (server should generate one when omitted)"
jq -e '.api_key_hint != null and (.api_key_hint | length) > 0' "$BODY_FILE" >/dev/null || fail "Registration response api_key_hint was missing/empty"
jq -e '(has("appliance_api_key_hash") or has("token_hash")) | not' "$BODY_FILE" >/dev/null || fail "Registration response must not have appliance_api_key_hash or token_hash keys"

echo "Captured appliance_id and raw appliance_api_key into shell variables (not displayed)."

section "12. Reusing the same activation token must fail with 401"

REUSE_BODY="$(jq -n --arg token "$ACTIVATION_RAW_TOKEN" --arg name "kb016-reuse-attempt" '{activation_token: $token, appliance_name: $name}')"
check_status "POST /appliance/register reusing an already-used activation token" 401 POST "$API_BASE/appliance/register" "" "$REUSE_BODY"

section "13. Activation token status is now 'used' (visible via KB-015 admin token list)"

check_status "GET .../appliance-activation-tokens as platform_admin" 200 GET "$API_BASE/admin/tenants/$DEMO_TENANT_ID/appliance-activation-tokens" "$PLATFORM_ADMIN_TOKEN"
jq -e --arg id "$FAKE_TOKEN_ID" '[.tokens[] | select(.id == $id)][0].status == "used"' "$BODY_FILE" >/dev/null \
  || fail "Fake validation activation token status is not 'used' after registration"
jq -e --arg id "$FAKE_TOKEN_ID" '[.tokens[] | select(.id == $id)][0].used_at != null' "$BODY_FILE" >/dev/null \
  || fail "Fake validation activation token used_at was not set"

section "14. POST /appliance/heartbeat without credentials must fail with 401"

check_appliance_status "Heartbeat with no headers" 401 "" "" '{}'

section "15. POST /appliance/heartbeat with wrong API key must fail with 401"

check_appliance_status "Heartbeat with correct X-Appliance-ID but wrong X-Appliance-API-Key" 401 "$FAKE_APPLIANCE_ID" "not-the-real-key-0000000000000000000000000" '{}'

section "16. POST /appliance/heartbeat with valid credentials succeeds"

HEARTBEAT_BODY='{"health_status":"healthy","cpu_percent":12.5,"memory_percent":40.1,"disk_percent":55.0,"agent_version":"kb016-test-1.0.0"}'
check_appliance_status "Heartbeat with valid credentials" 200 "$FAKE_APPLIANCE_ID" "$APPLIANCE_RAW_API_KEY" "$HEARTBEAT_BODY"

jq -e --arg id "$FAKE_APPLIANCE_ID" '.appliance_id == $id' "$BODY_FILE" >/dev/null || fail "Heartbeat response appliance_id mismatch"
jq -e '.status == "online"' "$BODY_FILE" >/dev/null || fail "Heartbeat response status should be 'online'"
jq -e '.heartbeat_at != null and (.heartbeat_at | length) > 0' "$BODY_FILE" >/dev/null || fail "Heartbeat response heartbeat_at was missing/empty"

section "17. Direct SQL verification of heartbeat insert and appliance updates"

HEARTBEAT_ROWS="$(psql_scalar "SELECT count(*) FROM appliance_heartbeats WHERE appliance_id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not count appliance_heartbeats rows (psql error)"
[ "$HEARTBEAT_ROWS" -ge "1" ] 2>/dev/null || fail "Expected at least 1 appliance_heartbeats row for the fake appliance, found $HEARTBEAT_ROWS"
echo "OK: $HEARTBEAT_ROWS appliance_heartbeats row(s) found for the fake appliance."

LAST_SEEN_NOT_NULL="$(psql_scalar "SELECT (last_seen_at IS NOT NULL) FROM appliances WHERE id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not check appliances.last_seen_at (psql error)"
[ "$LAST_SEEN_NOT_NULL" = "t" ] || fail "appliances.last_seen_at was not set after heartbeat"
echo "OK: appliances.last_seen_at is set."

KEY_LAST_USED_NOT_NULL="$(psql_scalar "SELECT (appliance_key_last_used_at IS NOT NULL) FROM appliances WHERE id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not check appliances.appliance_key_last_used_at (psql error)"
[ "$KEY_LAST_USED_NOT_NULL" = "t" ] || fail "appliances.appliance_key_last_used_at was not set after heartbeat"
echo "OK: appliances.appliance_key_last_used_at is set."

section "18. Admin GET /admin/appliances/{appliance_id} can see the registered appliance"

check_status "GET /admin/appliances/$FAKE_APPLIANCE_ID as platform_admin" 200 GET "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID" "$PLATFORM_ADMIN_TOKEN"
jq -e --arg name "$FAKE_APPLIANCE_NAME" '.appliance_name == $name' "$BODY_FILE" >/dev/null || fail "Admin appliance detail did not show the expected appliance_name"
jq -e '.status == "online"' "$BODY_FILE" >/dev/null || fail "Admin appliance detail should show status=online after heartbeat"
jq -e '.latest_heartbeat_at != null' "$BODY_FILE" >/dev/null || fail "Admin appliance detail should show a latest_heartbeat_at after heartbeat"

section "19. Existing GET /admin/appliances list still works unmodified"

check_status "GET /admin/appliances as platform_admin" 200 GET "$API_BASE/admin/appliances" "$PLATFORM_ADMIN_TOKEN"

section "20. Retired appliance must reject heartbeat with 403 (Decision D)"

check_status "PATCH /admin/appliances/$FAKE_APPLIANCE_ID set status=retired as platform_admin" 200 PATCH "$API_BASE/admin/appliances/$FAKE_APPLIANCE_ID" "$PLATFORM_ADMIN_TOKEN" '{"status":"retired"}'
jq -e '.status == "retired"' "$BODY_FILE" >/dev/null || fail "PATCH did not persist status=retired"

check_appliance_status "Heartbeat from a retired appliance (valid credentials)" 403 "$FAKE_APPLIANCE_ID" "$APPLIANCE_RAW_API_KEY" '{"health_status":"healthy"}'

section "21. Clean up fake KB-016 validation appliance, heartbeats, and activation token"

cleanup_fake_data

REMAINING_APPLIANCES="$(psql_scalar "SELECT count(*) FROM appliances WHERE appliance_name = '${FAKE_APPLIANCE_NAME}';")" \
  || fail "Could not verify fake validation appliance cleanup (psql error)"
[ "$REMAINING_APPLIANCES" = "0" ] || fail "Fake validation appliance was not cleaned up (found $REMAINING_APPLIANCES rows)"

REMAINING_HEARTBEATS="$(psql_scalar "SELECT count(*) FROM appliance_heartbeats WHERE appliance_id = '${FAKE_APPLIANCE_ID}';")" \
  || fail "Could not verify fake validation heartbeat cleanup (psql error)"
[ "$REMAINING_HEARTBEATS" = "0" ] || fail "Fake validation heartbeat rows were not cleaned up via cascade (found $REMAINING_HEARTBEATS rows)"

REMAINING_TOKENS="$(psql_scalar "SELECT count(*) FROM appliance_activation_tokens WHERE site_name = '${FAKE_TOKEN_SITE_NAME}';")" \
  || fail "Could not verify fake validation activation token cleanup (psql error)"
[ "$REMAINING_TOKENS" = "0" ] || fail "Fake validation activation token was not cleaned up (found $REMAINING_TOKENS rows)"

echo "OK: all fake KB-016 validation appliance/heartbeat/activation-token fixtures removed, no leftover data."

section "22. Behavior regression gate: scripts/kb015_validate_admin_appliance_management.sh"

echo "Running the full, unmodified KB-015 validation script now (which itself"
echo "reruns KB-014, and through it KB-013, KB-012, and KB-011). It will ask"
echo "for all 5 demo passwords again."
echo

if ! ./scripts/kb015_validate_admin_appliance_management.sh; then
  fail "scripts/kb015_validate_admin_appliance_management.sh did not pass after adding appliance registration/heartbeat - this is a real regression"
fi

section "23. Final validation verdict"

echo "KB-016 APPLIANCE REGISTRATION AND HEARTBEAT VALIDATION PASSED"
echo
echo "Summary:"
echo "  - /health, /auth/roles, /docs remain public."
echo "  - POST /appliance/register rejects a missing activation_token with a clean"
echo "    422, and rejects an invalid/garbage activation_token with a generic 401."
echo "  - A real activation token (created via the existing KB-015 admin API) was"
echo "    redeemed successfully: POST /appliance/register returned 201, with"
echo "    tenant_id and site_name derived from the token (never from the request"
echo "    body), and a server-generated appliance_uuid."
echo "  - The one-time appliance_api_key appeared exactly once, in the registration"
echo "    response; no response ever contained token_hash, appliance_api_key_hash,"
echo "    the raw activation token (outside its one creation response), the raw"
echo "    appliance API key (outside its one registration response), password_hash,"
echo "    or a password value."
echo "  - The same activation token could not be redeemed twice (401 on reuse); its"
echo "    status is 'used' with used_at set, visible via the existing KB-015 admin"
echo "    token list."
echo "  - POST /appliance/heartbeat rejects missing credentials and a wrong API key"
echo "    with a generic 401, accepts valid credentials with 200, records a new"
echo "    appliance_heartbeats row, and updates appliances.last_seen_at and"
echo "    appliances.appliance_key_last_used_at."
echo "  - A retired appliance's heartbeat is rejected with 403 even with a valid key."
echo "  - The registered appliance is visible via the existing"
echo "    GET /admin/appliances/{appliance_id} and GET /admin/appliances endpoints,"
echo "    unmodified."
echo "  - All fake KB-016 validation appliance/heartbeat/activation-token fixtures"
echo "    were cleaned up - no leftover data."
echo "  - scripts/kb015_validate_admin_appliance_management.sh passed unmodified -"
echo "    no observable behavior change to admin appliance management, user"
echo "    management, tenant management, route structure, auth, RBAC, tenant"
echo "    isolation, or validation-error redaction."
echo
echo "======================================================================"
echo "KB-016 validation completed successfully."
echo "======================================================================"
