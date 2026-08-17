#!/usr/bin/env bash
# soc_demo_fire_detection.sh — controlled lab detections for SOC demo rehearsal.
# Does NOT print secrets. Lab VMs only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API="${MSSP_API_URL:-http://127.0.0.1:8000}"
ALPHA="${MSSP_ALPHA_CODE:-ALPHAWINCORP-6VS2}"
TS="$(date +%s)"

log() { printf '[soc_demo] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

load_creds() {
  # shellcheck disable=SC1091
  source "$ROOT/scripts/load_validation_credentials.sh"
}

admin_token() {
  load_creds
  python3 - <<'PY'
import json, os, urllib.request
api = os.environ.get("MSSP_API_URL", "http://127.0.0.1:8000")
body = json.dumps({
    "email": os.environ["PLATFORM_ADMIN_EMAIL"],
    "password": os.environ["PLATFORM_ADMIN_PASSWORD"],
}).encode()
req = urllib.request.Request(f"{api}/auth/login", data=body, method="POST",
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=20) as r:
    print(json.loads(r.read())["access_token"])
PY
}

ingress_token() {
  if [[ -f "$ROOT/.secrets/wazuh_ingress_token" ]]; then
    tr -d '\r\n' < "$ROOT/.secrets/wazuh_ingress_token"
  elif [[ -n "${WAZUH_INGRESS_TOKEN:-}" ]]; then
    printf '%s' "$WAZUH_INGRESS_TOKEN"
  else
    die "Missing .secrets/wazuh_ingress_token"
  fi
}

fire_wazuh_alert() {
  local unique="$1"
  local level="$2"
  local rule_id="$3"
  local title="$4"
  local extra_json="${5:-}"

  local token
  token="$(ingress_token)"
  local hook="${API}/integrations/soc/hooks/wazuh/${token}"

  python3 - <<PY
import json, urllib.request, sys
hook = "$hook"
unique = "$unique"
level = int("$level")
rule_id = "$rule_id"
title = """$title"""
extra = json.loads("""${extra_json:-{}}""") if """$extra_json""" else {}
payload = {
    "timestamp": "2026-08-12T18:00:00.000+0530",
    "rule": {
        "level": level,
        "description": title,
        "id": rule_id,
        "groups": ["windows", "sysmon", "attack"],
        "mitre": {"id": ["T1059.001"], "tactic": ["Execution"], "technique": ["PowerShell"]},
    },
    "agent": {
        "id": "006",
        "name": "WIN-BL72S84GDTF",
        "ip": "192.168.0.214",
        "groups": ["tenant_ALPHAWINCORP_6VS2"],
    },
    "id": unique,
    "manager": {"name": "wazuh-stack"},
    "decoder": {"name": "windows_eventchannel"},
}
payload.update(extra)
data = json.dumps(payload).encode()
req = urllib.request.Request(hook, data=data, method="POST", headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
    body = json.loads(r.read().decode())
print(json.dumps(body, indent=2))
PY
}

admin_post() {
  local path="$1"
  local tok
  tok="$(admin_token)"
  curl -fsS -X POST "${API}${path}" \
    -H "Authorization: Bearer ${tok}" \
    -H "Content-Type: application/json" \
    -d "${2:-{}}" | python3 -m json.tool 2>/dev/null || true
}

usage() {
  cat <<'EOF'
Usage: ./scripts/soc_demo_fire_detection.sh <scenario>

Scenarios (controlled lab only):
  s01-powershell     High-severity encoded PowerShell (Log monitoring + IR)
  s01-netsh          Netsh firewall rule alert (Log monitoring)
  s02-incident       Same as powershell — auto-opens incident if level >= 10
  s04-vmaas-sync     Refresh vulnerability findings for Alpha (VMaaS)
  s05-compliance-sync  Refresh Wazuh SCA compliance data (CaaS)
  s06-ndr-sync       Refresh NDR adapter data
  s07-ti-sync        Refresh threat intel IOCs from MISP bridge
  s08-forensics-sync Refresh forensics/deception adapter data
  s09-easm-scan      Queue external attack surface scan (Alpha)
  s10-itdr-sync      Refresh cloud identity adapter events

Examples:
  ./scripts/soc_demo_fire_detection.sh s01-powershell
  ./scripts/soc_demo_fire_detection.sh s04-vmaas-sync

After firing, open Admin :3000 Alerts/Incidents or the relevant service page.
See: exports/SOC-DEMO-CONTROLLED-TEST-PLAYBOOK.md
EOF
}

case "${1:-}" in
  s01-powershell|s02-incident)
    log "Firing controlled PowerShell detection for Alpha..."
    fire_wazuh_alert "soc-demo-powershell-${TS}" 12 92213 \
      "SOC demo: suspicious encoded PowerShell on Windows workstation" \
      '{"data":{"win":{"eventdata":{"User":"ALPHAWIN\\\\itadmin","Image":"C:\\\\Windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe","CommandLine":"powershell.exe -NoProfile -EncodedCommand <demo>"}}}}'
    log "Next: Admin :3000/alerts — newest row — triage + customer visible"
    log "Next: Admin :3000/incidents — new INC-*-TH-* if level >= 10"
    ;;
  s01-netsh)
    log "Firing controlled Netsh firewall rule detection..."
    fire_wazuh_alert "soc-demo-netsh-${TS}" 12 67004 \
      "Netsh used to add firewall rule" \
      '{"data":{"win":{"eventdata":{"User":"ALPHAWIN\\\\itadmin","Image":"C:\\\\Windows\\\\System32\\\\netsh.exe"}}}}'
    log "Next: Admin :3000/alerts — triage (may correlate to open incident if same title within window)"
    ;;
  s04-vmaas-sync)
    log "Syncing VMaaS for ${ALPHA}..."
    admin_post "/admin/vmaas/${ALPHA}/sync"
    log "Next: Admin :3000/vulnerabilities — pick open HIGH finding — Promote to recommendation"
    log "Next: Customer :3001/vulnerabilities"
    ;;
  s05-compliance-sync)
    log "Syncing compliance (SCA) for ${ALPHA}..."
    admin_post "/admin/compliance/${ALPHA}/sync"
    log "Next: Customer :3001/compliance — score + failed checks"
    log "Next: Admin :3000/recommendations — create IT patch/hardening recommendation"
    ;;
  s06-ndr-sync)
    log "Syncing NDR for ${ALPHA}..."
    admin_post "/admin/ndr/${ALPHA}/sync"
    log "Next: Customer :3001/ndr — events + sensors"
    log "Honesty: sample rows until real Suricata event ingested"
    ;;
  s07-ti-sync)
    log "Syncing threat intel for ${ALPHA}..."
    admin_post "/admin/threat-intel/${ALPHA}/sync"
    log "Next: Admin :3000/threat-intel?tenant=${ALPHA}"
    log "Next: Customer :3001/threat-intel"
    ;;
  s08-forensics-sync)
    log "Syncing forensics for ${ALPHA}..."
    admin_post "/admin/forensics/${ALPHA}/sync"
    log "Next: Customer :3001/forensics — tripwires / collections"
    log "Optional: Admin incident detail — EDR Collect (lab only)"
    ;;
  s09-easm-scan)
    log "Queueing EASM scan for ${ALPHA} (uses registered domain if any)..."
    admin_post "/admin/easm/${ALPHA}/scan" '{"async_mode": true}'
    log "Next: Customer :3001/easm — assets/findings after agent cycle"
    ;;
  s10-itdr-sync)
    log "Syncing ITDR for ${ALPHA}..."
    admin_post "/admin/itdr/${ALPHA}/sync"
    log "Next: Customer :3001/itdr"
    log "Honesty: adapter events until Microsoft Graph connected"
    ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  *)
    die "Unknown scenario: $1 (run with --help)"
    ;;
esac

log "Done."
