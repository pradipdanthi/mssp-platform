#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"

cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-020: Validate Production Bootstrap and Demo Data Separation"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

section "1. Required files exist"

REQUIRED=(
  "postgres/seed/dev/README.md"
  "scripts/seed_demo_data.sh"
  "scripts/bootstrap_platform_admin.sh"
  "scripts/kb020_validate_production_bootstrap_demo_separation.sh"
  "docs/KB020_PRODUCTION_BOOTSTRAP_AND_DEMO_SEPARATION.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. New scripts are executable"

[ -x scripts/seed_demo_data.sh ] || fail "scripts/seed_demo_data.sh is not executable (chmod +x)"
[ -x scripts/bootstrap_platform_admin.sh ] || fail "scripts/bootstrap_platform_admin.sh is not executable (chmod +x)"
[ -x scripts/kb020_validate_production_bootstrap_demo_separation.sh ] \
  || fail "scripts/kb020_validate_production_bootstrap_demo_separation.sh is not executable (chmod +x)"
echo "OK: new scripts are executable."

section "3. Bash syntax checks"

bash -n scripts/seed_demo_data.sh || fail "bash -n failed for seed_demo_data.sh"
bash -n scripts/bootstrap_platform_admin.sh || fail "bash -n failed for bootstrap_platform_admin.sh"
bash -n scripts/kb020_validate_production_bootstrap_demo_separation.sh \
  || fail "bash -n failed for this validation script"
echo "OK: bash -n passed for all new scripts."

section "4. postgres/init remains schema-only (no demo seed INSERTs)"

INIT_DIR="postgres/init"
[ -d "$INIT_DIR" ] || fail "$INIT_DIR is missing"

# Demo identifiers that must not appear as seed material in init SQL.
if grep -RInE \
  "DEMO2|example\.local|demo\.local|INC-DEMO|demo-wazuh|Demo SOC|Demo Customer|short_code\s*=\s*'DEMO'|short_code\s*=\s*\"DEMO\"" \
  "$INIT_DIR"/*.sql 2>/dev/null; then
  fail "postgres/init/*.sql appears to contain demo seed identifiers — init must stay schema/migration only"
fi

# No INSERT INTO for tenant/user/alert/incident tables with demo smell via INSERT blocks.
if grep -RInE "INSERT[[:space:]]+INTO[[:space:]]+(tenants|platform_users|security_alerts|incidents)" \
  "$INIT_DIR"/*.sql 2>/dev/null; then
  fail "postgres/init/*.sql contains INSERT INTO tenants/platform_users/security_alerts/incidents — unexpected for schema-only init"
fi

echo "OK: postgres/init/*.sql has no demo seed INSERTs for DEMO/DEMO2/example.local/etc."

section "5. docker-compose does not mount postgres/seed/dev into initdb"

grep -q './postgres/init:/docker-entrypoint-initdb.d' docker-compose.yml \
  || fail "docker-compose.yml does not mount ./postgres/init to docker-entrypoint-initdb.d as expected"

if grep -E 'postgres/seed/dev|seed/dev:' docker-compose.yml >/dev/null 2>&1; then
  fail "docker-compose.yml references postgres/seed/dev — demo seed must not be mounted into the runtime"
fi

echo "OK: compose mounts only postgres/init for initdb; seed/dev is not mounted."

section "6. postgres/seed/dev README warns development-only"

grep -qi "development" postgres/seed/dev/README.md \
  || fail "postgres/seed/dev/README.md does not mention development"
grep -qi "must not" postgres/seed/dev/README.md \
  || fail "postgres/seed/dev/README.md is missing 'must not' safety language"
grep -qi "docker-entrypoint-initdb.d" postgres/seed/dev/README.md \
  || fail "postgres/seed/dev/README.md must warn against mounting into docker-entrypoint-initdb.d"
grep -qi "production" postgres/seed/dev/README.md \
  || fail "postgres/seed/dev/README.md must mention production exclusion"
echo "OK: seed/dev README contains development-only warnings."

if [ -f postgres/seed/dev/001_demo_seed.sql ]; then
  echo "NOTE: postgres/seed/dev/001_demo_seed.sql is present."
  if grep -qiE 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''.\" ]{4,}' postgres/seed/dev/001_demo_seed.sql; then
    fail "001_demo_seed.sql appears to contain a plaintext password assignment — not allowed"
  fi
else
  echo "NOTE: 001_demo_seed.sql is deferred (acceptable for KB-020)."
fi

section "7. seed_demo_data.sh guards"

grep -q 'APP_ENV' scripts/seed_demo_data.sh || fail "seed_demo_data.sh missing APP_ENV check"
grep -q 'production' scripts/seed_demo_data.sh || fail "seed_demo_data.sh missing production refuse path"
grep -q -- '--yes-dev-demo' scripts/seed_demo_data.sh || fail "seed_demo_data.sh missing --yes-dev-demo requirement"
grep -qi 'DEVELOPMENT' scripts/seed_demo_data.sh || fail "seed_demo_data.sh should label itself as development/lab"
# Ensure it does not contain a destructive unconditional delete of demo tenants as its main action.
if grep -Eiq 'DELETE[[:space:]]+FROM[[:space:]]+tenants' scripts/seed_demo_data.sh; then
  fail "seed_demo_data.sh must not DELETE FROM tenants (KB-020 is non-destructive)"
fi
echo "OK: seed_demo_data.sh has APP_ENV=production guard and --yes-dev-demo."

section "8. bootstrap_platform_admin.sh safety"

grep -q 'BOOTSTRAP_ADMIN_EMAIL' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh missing BOOTSTRAP_ADMIN_EMAIL support"
grep -q 'BOOTSTRAP_ADMIN_FULL_NAME' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh missing BOOTSTRAP_ADMIN_FULL_NAME support"
grep -q 'BOOTSTRAP_ADMIN_PASSWORD' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh missing BOOTSTRAP_ADMIN_PASSWORD support"
grep -q 'read -rs' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh missing hidden password prompt (read -rs)"
grep -q 'hash_password' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh must use app.core.security.hash_password"
grep -q "platform_admin" scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh must create platform_admin"
grep -q 'tenant_id' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh must set tenant_id (NULL) explicitly"
grep -q -- '--force' scripts/bootstrap_platform_admin.sh \
  || fail "bootstrap_platform_admin.sh missing --force guard for existing platform_admin"

# No hardcoded plaintext password literals that look like assignments.
if grep -Eiq 'password[[:space:]]*=[[:space:]]*['\''\"][^$'\''\"]{8,}['\''\"]' scripts/bootstrap_platform_admin.sh; then
  fail "bootstrap_platform_admin.sh appears to hardcode a plaintext password literal"
fi

# Must not echo password or hash variables.
if grep -En 'echo.*(ADMIN_PASSWORD|ADMIN_HASH|BOOTSTRAP_ADMIN_PASSWORD)' scripts/bootstrap_platform_admin.sh \
  | grep -v 'not displayed' | grep -v 'never' | grep -v 'Password hash computed' | grep -v 'Using BOOTSTRAP_ADMIN_PASSWORD'; then
  fail "bootstrap_platform_admin.sh may echo password/hash material"
fi

echo "OK: bootstrap_platform_admin.sh uses hidden/env password input, approved hash_password, platform_admin only."

section "9. Documentation exists"

[ -s docs/KB020_PRODUCTION_BOOTSTRAP_AND_DEMO_SEPARATION.md ] \
  || fail "docs/KB020_PRODUCTION_BOOTSTRAP_AND_DEMO_SEPARATION.md is missing or empty"
grep -qi 'bootstrap_platform_admin' docs/KB020_PRODUCTION_BOOTSTRAP_AND_DEMO_SEPARATION.md \
  || fail "KB-020 doc does not document bootstrap_platform_admin.sh"
grep -qi 'lab' docs/KB020_PRODUCTION_BOOTSTRAP_AND_DEMO_SEPARATION.md \
  || fail "KB-020 doc should explain lab DB behavior"
echo "OK: KB-020 documentation is present."

section "10. Protected paths were not modified by this module"

PROTECTED=(
  "backend-api/"
  "frontend-admin/"
  "docker-compose.yml"
  "postgres/init/"
)

for p in "${PROTECTED[@]}"; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-020 must not modify it"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-020 must not modify it"
  echo "OK: $p unmodified (no working-tree or staged diff)"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked — must not be touched"
fi
echo "OK: .env not showing as changed/untracked."

section "11. No obvious committed production secrets in new KB-020 files"

# Look for JWT-looking strings or password= assignments in new artifacts only.
SCAN_PATHS=(
  postgres/seed/dev
  scripts/seed_demo_data.sh
  scripts/bootstrap_platform_admin.sh
  scripts/kb020_validate_production_bootstrap_demo_separation.sh
  docs/KB020_PRODUCTION_BOOTSTRAP_AND_DEMO_SEPARATION.md
)

for p in "${SCAN_PATHS[@]}"; do
  if [ -e "$p" ]; then
    if grep -REn 'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}' "$p" 2>/dev/null; then
      fail "JWT-looking string found under $p"
    fi
  fi
done
echo "OK: no JWT-looking strings found in new KB-020 artifacts."

section "12. Honesty note — live lab database"

echo "KB-020 separates demo/development seed material from production bootstrap"
echo "in the repository and process documentation."
echo
echo "This validation does NOT wipe the running PostgreSQL database and does"
echo "NOT prove that the current lab DB is free of DEMO / DEMO2 / example.local"
echo "rows. Those rows may still exist from prior KB modules so lab validation"
echo "keeps working. A future, explicitly approved module would be required to"
echo "reset or clean a live volume for production-like cutover."
echo
echo "This script also does NOT execute seed_demo_data.sh or"
echo "bootstrap_platform_admin.sh (both would change database state)."

section "13. Final validation verdict"

echo "Summary:"
echo "  - postgres/init stays schema-only; compose does not mount seed/dev."
echo "  - seed/dev README + seed_demo_data.sh guard production misuse."
echo "  - bootstrap_platform_admin.sh creates first platform_admin safely."
echo "  - docs and validation script present; protected trees untouched."
echo "  - Current lab DB may still contain demo rows (by design for KB-020)."
echo
echo "======================================================================"
echo "KB-020 PRODUCTION BOOTSTRAP AND DEMO SEPARATION VALIDATION PASSED"
echo "======================================================================"
