#!/usr/bin/env bash
# Apply NikTiar Sovereign Edge posture on the local appliance.
set -euo pipefail

ACTION="${1:-status}"
shift || true

CONTROL_PLANE_IP="${MSSP_CONTROL_PLANE_IP:-192.168.0.201}"
APPLIANCE_MGMT_IP="${MSSP_APPLIANCE_MGMT_IP:-192.168.0.224}"
BLOCKED=("$CONTROL_PLANE_IP" "$APPLIANCE_MGMT_IP")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --control-plane-ip) CONTROL_PLANE_IP="$2"; shift 2 ;;
    --appliance-mgmt-ip) APPLIANCE_MGMT_IP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

BLOCKED=("$CONTROL_PLANE_IP" "$APPLIANCE_MGMT_IP")
DRY_RUN="${DRY_RUN:-0}"

find_profile_py() {
  for p in \
    /opt/kevantic/appliance-src/appliance/sovereign/profile.py \
    /opt/junexis/appliance-src/appliance/sovereign/profile.py \
    /opt/mssp-control/kevantic-appliance/appliance/sovereign/profile.py
  do
    [[ -f "$p" ]] && { echo "$p"; return 0; }
  done
  return 1
}

PROFILE_PY="$(find_profile_py || true)"
if [[ -z "$PROFILE_PY" ]]; then
  echo "sovereign profile.py not found" >&2
  exit 2
fi

export PYTHONPATH="$(dirname "$(dirname "$(dirname "$PROFILE_PY")")"):${PYTHONPATH:-}"

run_py() {
  if [[ "$DRY_RUN" == "1" ]]; then
    python3 - "$@" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(":")[0])
from appliance.sovereign.profile import (
    enable_sovereign_profile,
    set_cloud_egress,
    show_status,
    apply_sovereign_posture,
    load_profile,
    save_profile,
    default_profile,
)

action = sys.argv[1]
blocked = [x for x in sys.argv[2].split(",") if x]

if action == "enable":
    out = enable_sovereign_profile(
        cloud_egress_enabled=False,
        airgap_enabled=True,
        blocked_ipv4=blocked,
        dry_run=True,
    )
elif action == "egress-on":
    prof = default_profile()
    prof["blocked_ipv4"] = blocked
    save_profile(prof) if False else None
    out = set_cloud_egress(True, dry_run=True)
elif action == "egress-off":
    out = set_cloud_egress(False, dry_run=True)
elif action == "status":
    out = show_status()
else:
  raise SystemExit(f"unknown action {action}")
print(json.dumps(out, indent=2))
PY
    return
  fi

  python3 - "$@" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(":")[0])
from appliance.sovereign.profile import (
    enable_sovereign_profile,
    set_cloud_egress,
    show_status,
)

action = sys.argv[1]
blocked = [x for x in sys.argv[2].split(",") if x]

if action == "enable":
    out = enable_sovereign_profile(
        cloud_egress_enabled=False,
        airgap_enabled=True,
        blocked_ipv4=blocked,
    )
elif action == "egress-on":
    out = set_cloud_egress(True)
elif action == "egress-off":
    out = set_cloud_egress(False)
elif action == "status":
    out = show_status()
else:
    raise SystemExit(f"unknown action {action}")
print(json.dumps(out, indent=2))
PY
}

case "$ACTION" in
  enable) run_py enable "$(IFS=,; echo "${BLOCKED[*]}")" ;;
  egress-on) run_py egress-on "$(IFS=,; echo "${BLOCKED[*]}")" ;;
  egress-off) run_py egress-off "$(IFS=,; echo "${BLOCKED[*]}")" ;;
  status) run_py status "$(IFS=,; echo "${BLOCKED[*]}")" ;;
  *)
    echo "usage: $0 {enable|egress-on|egress-off|status} [--control-plane-ip IP] [--appliance-mgmt-ip IP] [--dry-run]" >&2
    exit 2
    ;;
esac
