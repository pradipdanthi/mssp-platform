#!/usr/bin/env bash
# KB-036: Validate MSSP Platform Architecture and Deployment Model Roadmap (docs only).
# Enterprise MSSP/SOC/MDR/XDR platform — confirms roadmap docs exist, required
# architecture mentions are present, and runtime/protected paths were not modified.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-036: Validate MSSP Platform Architecture Roadmap"
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

file_mentions() {
  local file="$1"
  shift
  local needle
  for needle in "$@"; do
    grep -qi "$needle" "$file" || fail "$file missing required mention: $needle"
  done
}

section "1. Required documentation files exist"

REQUIRED=(
  "AGENTS.md"
  "CLAUDE.md"
  ".cursor/rules/mssp-control-plane.mdc"
  "CONTEXT.md"
  "docs/AI_PROMPT_LEDGER.md"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
  "scripts/kb036_validate_mssp_platform_architecture_roadmap.sh"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-036 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-036 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. CONTEXT.md required enterprise architecture mentions"

file_mentions CONTEXT.md \
  "MSSP" \
  "MDR" \
  "XDR" \
  "cloud-hosted" \
  "on-prem" \
  "hybrid" \
  "Wazuh" \
  "Wazuh Indexer" \
  "OpenSearch" \
  "Wazuh Dashboard" \
  "Wazuh Agents" \
  "Suricata" \
  "Zeek" \
  "TheHive" \
  "Shuffle" \
  "MISP" \
  "Greenbone" \
  "OpenVAS" \
  "Velociraptor" \
  "Ansible" \
  "deployment automation" \
  "cluster registry" \
  "appliance registry" \
  "source_platform" \
  "vulnerability" \
  "sync_health" \
  "VM 100" \
  "VM 101" \
  "VM 105" \
  "VM 106" \
  "not deployed yet" \
  "KB-037" \
  "KB-060" \
  "Phase 1" \
  "Phase 12" \
  "KB-035" \
  "1ac1df3" \
  "raw logs"
echo "OK: CONTEXT.md mentions enterprise stack, deployment models, VMs, and roadmap."

section "4. KB036 roadmap doc required mentions"

file_mentions docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md \
  "enterprise" \
  "MDR" \
  "XDR" \
  "cloud-hosted MSSP" \
  "on-prem appliance" \
  "Hybrid model" \
  "Wazuh Manager" \
  "Wazuh Indexer" \
  "OpenSearch" \
  "Wazuh Dashboard" \
  "Wazuh Agents" \
  "Suricata" \
  "Zeek" \
  "TheHive" \
  "Shuffle" \
  "MISP" \
  "Greenbone" \
  "OpenVAS" \
  "Velociraptor" \
  "Ansible" \
  "deployment automation" \
  "cluster registry" \
  "appliance registry" \
  "source_platform" \
  "vulnerability" \
  "sync_health_status" \
  "VM 100" \
  "VM 111" \
  "NOT been deployed yet" \
  "KB-037" \
  "KB-060" \
  "Phase 1" \
  "Phase 12" \
  "raw Suricata"
echo "OK: KB036 doc mentions full enterprise stack, models, VMs, and KB roadmap."

section "5. AGENTS.md / CLAUDE.md / Cursor rule synced to KB-035+ and KB-036"

for f in AGENTS.md CLAUDE.md .cursor/rules/mssp-control-plane.mdc; do
  file_mentions "$f" \
    "KB-035" \
    "KB-036" \
    "Suricata" \
    "MISP" \
    "hybrid" \
    "planning before implementation" \
    "no .env" \
    "no /admin" \
    "validation before commit"
  echo "OK: $f mentions KB-035/KB-036, enterprise stack, and workflow/safety rules."
done

section "6. AI_PROMPT_LEDGER.md required mentions"

file_mentions docs/AI_PROMPT_LEDGER.md \
  "KB-035" \
  "KB-036" \
  "kb035-customer-appliance-detail-validated" \
  "enterprise"
echo "OK: ledger mentions KB-035, KB-036, and enterprise scope."

section "7. No obvious secrets in updated docs"

DOC_SCAN_FILES=(
  AGENTS.md
  CLAUDE.md
  CONTEXT.md
  docs/AI_PROMPT_LEDGER.md
  docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md
  .cursor/rules/mssp-control-plane.mdc
)

SECRET_HIT="$(grep -REn \
  -e 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'api_key[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'token[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{8,}' \
  -e 'JWT_SECRET[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]+' \
  -e 'Bearer[[:space:]]+[A-Za-z0-9_-]{20,}' \
  "${DOC_SCAN_FILES[@]}" 2>/dev/null || true)"

if [ -n "$SECRET_HIT" ]; then
  echo "$SECRET_HIT" >&2
  fail "Possible secret material found in documentation files"
fi
echo "OK: no obvious password/token/api_key secret assignments in updated docs."

section "8. Final verdict"

echo "======================================================================"
echo "KB-036 MSSP PLATFORM ARCHITECTURE ROADMAP VALIDATION PASSED"
echo "======================================================================"
