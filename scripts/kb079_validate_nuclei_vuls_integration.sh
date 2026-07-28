#!/usr/bin/env bash
# KB-079: Validate Nuclei+Vuls end-to-end integration (scripts, APIs, dashboards).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"
pass=0
fail=0
check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
}
file_has() { grep -qE "$2" "$1"; }

echo "======================================================================"
echo "KB-079: Validate Nuclei + Vuls Control-Plane Integration"
echo "======================================================================"

check "KB-079 doc" test -f docs/KB079_NUCLEI_VULS_CONTROL_PLANE_INTEGRATION.md
check "scan targets config" test -f config/vuln_scan_targets.yml
check "pull nuclei script" test -x scripts/kb079_pull_nuclei_findings.sh
check "pull vuls script" test -x scripts/kb079_pull_vuls_findings.sh
check "run all script" test -x scripts/kb079_run_vuln_scans.sh
check "normalize nuclei" test -f scripts/kb079_normalize_nuclei_jsonl.py
check "normalize vuls" test -f scripts/kb079_normalize_vuls_report.py
check "scan-plan API" file_has backend-api/app/api/routes/vuln_sync.py "/scan-plan"
check "scan agent script" test -f scripts/kb079_vuln_scan_agent.py
check "systemd timer unit" test -f deploy/systemd/mssp-vuln-scan-agent.timer
check "admin request-scan route" file_has backend-api/app/api/routes/vulnerability_management.py "request-scan"
check "scheduler migration sql" test -f postgres/init/013_kb079_vuln_scan_scheduler.sql

check "admin list filter param" \
  file_has backend-api/app/api/routes/vulnerability_management.py "source_platform"
check "customer summary route" \
  file_has backend-api/app/api/routes/customer.py "/vulnerabilities/{short_code}/summary"
check "customer API client summary" \
  file_has frontend-customer/src/api/customer.ts "getVulnerabilityServiceSummary"
check "customer page uses summary" \
  file_has frontend-customer/src/pages/VulnerabilitiesPage.tsx "getVulnerabilityServiceSummary"
check "admin source filter" \
  file_has frontend-admin/src/pages/VulnerabilitiesPage.tsx "sourceFilter"
check "admin getVulnerabilities query" \
  file_has frontend-admin/src/api/admin.ts "source_platform"
check "entitlements label nuclei" \
  file_has frontend-admin/src/components/CreateEntitlementsFields.tsx "Nuclei"

check "KB-078 still valid" ./scripts/kb078_validate_nuclei_vuls_free_stack.sh

echo
echo "KB-079 checks: pass=$pass fail=$fail"
test "$fail" -eq 0
echo "======================================================================"
echo "KB-079 NUCLEI + VULS INTEGRATION VALIDATION PASSED"
echo "======================================================================"
