#!/usr/bin/env bash
set -euo pipefail
cd /opt/mssp-control
fail(){ echo; echo "VALIDATION FAILED: $1" >&2; exit 1; }
section(){ echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Files"
for f in \
  docs/KB062_ADMIN_RECOMMENDATIONS_NOTIFICATIONS.md \
  scripts/kb062_validate_admin_recommendations_notifications.sh \
  scripts/kb062_shuffle_control_plane_hop_helper.sh \
  frontend-admin/src/pages/RecommendationsPage.tsx \
  frontend-admin/src/pages/NotificationsPage.tsx
 do
  [ -f "$f" ] || fail "$f missing"
  echo "found: $f"
done

section "2. Wiring"
grep -q 'def admin_recommendations' backend-api/app/api/routes/admin.py || fail "admin recommendations route missing"
grep -q 'def admin_notifications' backend-api/app/api/routes/admin.py || fail "admin notifications route missing"
grep -q 'getRecommendations' frontend-admin/src/api/admin.ts || fail "frontend API getRecommendations missing"
grep -q 'getNotifications' frontend-admin/src/api/admin.ts || fail "frontend API getNotifications missing"
grep -q '/recommendations' frontend-admin/src/App.tsx || fail "App route recommendations missing"
grep -q '/notifications' frontend-admin/src/App.tsx || fail "App route notifications missing"
grep -q 'to="/recommendations"' frontend-admin/src/pages/DashboardPage.tsx || fail "KPI recommendations link missing"
grep -q 'to="/notifications"' frontend-admin/src/pages/DashboardPage.tsx || fail "KPI notifications link missing"
grep -q 'Recommendations' frontend-admin/src/components/Layout.tsx || fail "nav Recommendations missing"
# notifications list must not select recipient_address
! grep -n 'recipient_address' backend-api/app/api/routes/admin.py | grep -q admin_notifications \
  || true
python3 - <<'PY'
from pathlib import Path
text=Path('backend-api/app/api/routes/admin.py').read_text()
start=text.find('def admin_notifications')
chunk=text[start:start+800]
if 'recipient_address' in chunk or 'recipient_name' in chunk:
    raise SystemExit('notifications query must not expose recipient fields')
print('OK: notifications omit recipient fields')
PY

section "3. Live OpenAPI + auth gate"
curl -fsS http://127.0.0.1:8000/health >/dev/null || fail "health failed"
OPENAPI=$(curl -fsS http://127.0.0.1:8000/openapi.json)
echo "$OPENAPI" | jq -e '.paths|has("/admin/recommendations")' >/dev/null || fail "openapi missing recommendations"
echo "$OPENAPI" | jq -e '.paths|has("/admin/notifications")' >/dev/null || fail "openapi missing notifications"
CODE=$(curl -sS -o /tmp/kb062_unauth.json -w '%{http_code}' http://127.0.0.1:8000/admin/recommendations || true)
[[ "$CODE" == "401" || "$CODE" == "403" ]] || fail "expected 401/403 without auth, got $CODE"
echo "OK: unauthenticated recommendations rejected ($CODE)"

section "4. Verdict"
echo "======================================================================"
echo "KB-062 ADMIN RECOMMENDATIONS NOTIFICATIONS VALIDATION PASSED"
echo "======================================================================"
