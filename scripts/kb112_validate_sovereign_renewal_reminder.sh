#!/usr/bin/env bash
# KB-112 Step 4: Validate Sovereign Edge offline renewal reminders.
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"
APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"

pass=0
fail=0
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

test -f kevantic-appliance/appliance/sovereign/renewal_reminder.py && ok "renewal_reminder.py" || bad "renewal_reminder.py"
grep -q renewal-status kevantic-appliance/cli/kevantic-cli/kevantic_cli/cli.py && ok "cli renewal-status" || bad "cli renewal-status"

if docker compose exec -T backend-api python -m unittest tests.test_sovereign_renewal_reminder -q 2>/dev/null; then
  ok "unit tests"
else
  (cd backend-api && PYTHONPATH=../kevantic-appliance/appliance python3 -m unittest tests.test_sovereign_renewal_reminder -q) \
    && ok "unit tests (host)" || bad "unit tests"
fi

if ssh -i "$APPLIANCE_KEY" -o ConnectTimeout=5 -o BatchMode=yes "${APPLIANCE_USER}@${APPLIANCE_HOST}" 'echo ok' >/dev/null 2>&1; then
  REMINDER="$(ssh -i "$APPLIANCE_KEY" "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
    'sudo -n env PYTHONPATH=/opt/junexis/cli:/opt/junexis:/opt/junexis/appliance-src python3 -c "
import json
from junexis_cli import license_ops
print(json.dumps(license_ops.renewal_status()))
"')"
  echo "$REMINDER" | jq -e '.customer_may_apply_license == false' >/dev/null && ok "customer cannot apply renewal" || bad "customer apply flag"
  echo "$REMINDER" | jq -e '.exp != null' >/dev/null && ok "reminder includes license exp" || bad "missing exp"
  ssh -i "$APPLIANCE_KEY" "${APPLIANCE_USER}@${APPLIANCE_HOST}" \
    'sudo -n test -f /var/lib/junexis/renewal-reminder.json || sudo -n test -f /var/lib/kevantic/renewal-reminder.json' \
    && ok "renewal-reminder.json on appliance" || bad "reminder file missing"
else
  echo "SKIP: appliance offline"
fi

if [[ "$fail" -eq 0 ]]; then
  echo "KB-112 SOVEREIGN RENEWAL REMINDER VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-112 SOVEREIGN RENEWAL REMINDER VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
