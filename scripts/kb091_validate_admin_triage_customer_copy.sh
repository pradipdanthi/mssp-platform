#!/usr/bin/env bash
# KB-091: Admin triage can edit customer-visible summary + recommended action.
set -euo pipefail
cd /opt/mssp-control

fail() { echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "---- $1 ----"; }

section "1. Schema + API contracts"
grep -q 'ai_plain_summary' backend-api/app/schemas/triage.py \
  || fail "alert schema missing ai_plain_summary"
grep -q 'ai_recommended_action' backend-api/app/schemas/triage.py \
  || fail "alert schema missing ai_recommended_action"
grep -q 'customer_action_required' backend-api/app/schemas/triage.py \
  || fail "incident schema missing customer_action_required"
grep -q 'ai_plain_summary = %s' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "alert PATCH missing ai_plain_summary write"
grep -q 'ai_recommended_action = %s' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "alert PATCH missing ai_recommended_action write"
grep -q 'customer_action_required = %s' backend-api/app/api/routes/alert_incident_triage.py \
  || fail "incident PATCH missing customer_action_required write"
echo "OK: triage edit contracts present"

section "2. Admin frontend contracts"
grep -q 'ai_recommended_action' frontend-admin/src/pages/AlertDetailPage.tsx \
  || fail "alert triage UI missing recommended action"
grep -q 'Customer-visible summary' frontend-admin/src/pages/AlertDetailPage.tsx \
  || fail "alert triage UI missing customer summary"
grep -q 'customer_action_required' frontend-admin/src/pages/IncidentDetailPage.tsx \
  || fail "incident triage UI missing recommended action save"
grep -q 'Recommended action' frontend-admin/src/pages/IncidentDetailPage.tsx \
  || fail "incident triage UI missing recommended action field"
echo "OK: admin UI contracts present"

section "3. Unit check in API container"
docker exec -i mssp-backend-api python3 - <<'PY' || fail "unit check failed"
from app.schemas.triage import AlertTriageUpdateRequest, IncidentTriageUpdateRequest

a = AlertTriageUpdateRequest(
    ai_plain_summary="  Customer-ready summary  ",
    ai_recommended_action="  Call your SOC contact  ",
)
assert a.ai_plain_summary == "Customer-ready summary"
assert a.ai_recommended_action == "Call your SOC contact"

b = AlertTriageUpdateRequest(ai_plain_summary="   ")
assert b.ai_plain_summary is None

i = IncidentTriageUpdateRequest(
    customer_visible_summary=" Incident summary ",
    customer_action_required=" Reset passwords ",
)
assert i.customer_visible_summary == "Incident summary"
assert i.customer_action_required == "Reset passwords"
print("OK: triage schema normalization")
PY

section "4. Final"
echo "VALIDATION PASSED: Admin triage customer copy edits OK"
exit 0
