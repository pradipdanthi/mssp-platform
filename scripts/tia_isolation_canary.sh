#!/usr/bin/env bash
# Prove the runner's systemd sandbox hides synthetic canaries. Run as root on an ISOLATED
# test VM (not production). It creates only synthetic files under /tmp/tia-canary-* and a
# transient unit; it never reads real secrets.
#
#   sudo ./scripts/tia_isolation_canary.sh
#
# Evidence status: on the control-plane VM (no root, user manager only) the sandbox
# directives do not apply, so this script exits 3 (PENDING) there instead of passing.
set -uo pipefail
[[ $EUID -eq 0 ]] || { echo "PENDING: must run as root on a disposable VM (user managers do not enforce mount sandboxing)"; exit 3; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$ROOT/soc-agent/deploy/tia-cli-runner.service"
D="$(mktemp -d /tmp/tia-canary-XXXXXX)"
trap 'rm -rf "$D"; systemctl stop tia-canary-probe.service >/dev/null 2>&1' EXIT
chmod 755 "$D"
echo "CANARY_AGENT_SECRET" > "$D/agent.env"; chmod 644 "$D/agent.env"
mkdir -p "$D/app"; echo "CANARY_SOURCE" > "$D/app/source.py"
export CANARY_PARENT_ENV="CANARY_INHERITED_ENV_VALUE"

cat > "$D/probe.py" <<PY
import json, os
res = {}
def can_read(p):
    try: open(p).read(1); return True
    except Exception: return False
def can_write(p):
    try: open(p, "w").write("x"); os.unlink(p); return True
    except Exception: return False
res["read_canary_agent_env"] = can_read("$D/agent.env")
res["read_etc_shadow"] = can_read("/etc/shadow")
res["write_etc"] = can_write("/etc/tia-canary-write")
res["write_opt"] = can_write("/opt/tia-canary-write")
res["write_usr"] = can_write("/usr/tia-canary-write")
res["see_inherited_env"] = "CANARY_PARENT_ENV" in os.environ
res["see_other_procs"] = len([p for p in os.listdir("/proc") if p.isdigit()]) > 3
print(json.dumps(res))
PY
chmod 644 "$D/probe.py"

# Same property set as the unit (kept in sync by reading the shipped file).
props=()
while IFS= read -r line; do
  case "$line" in
    NoNewPrivileges=*|PrivateTmp=*|PrivateDevices=*|ProtectSystem=*|ProtectHome=*|ProtectProc=*|ProcSubset=*|ProtectKernel*=*|ProtectControlGroups=*|ProtectClock=*|ProtectHostname=*|RestrictNamespaces=*|RestrictRealtime=*|RestrictSUIDSGID=*|LockPersonality=*|RestrictAddressFamilies=*|SystemCallArchitectures=*|CapabilityBoundingSet=*|AmbientCapabilities=*)
      props+=("-p" "$line");;
  esac
done < "$UNIT"
props+=("-p" "InaccessiblePaths=$D")   # stand-in for /opt/soc-agent etc.
id nobody >/dev/null 2>&1 && props+=("-p" "User=nobody")

out="$(systemd-run --wait --pipe -q "${props[@]}" python3 "$D/probe.py" 2>&1 | tail -1)"
echo "probe result: $out"
fail=0
check() { python3 -c "import json,sys; r=json.loads(sys.argv[1]); sys.exit(0 if r.get('$1') == $2 else 1)" "$out" 2>/dev/null && echo "PASS: $3" || { echo "FAIL: $3"; fail=1; }; }
check read_canary_agent_env False "canary file in an inaccessible path is not readable"
check read_etc_shadow False "/etc/shadow is not readable"
check write_etc False "/etc is read-only"
check write_opt False "/opt is read-only"
check write_usr False "/usr is read-only"
check see_inherited_env False "the parent environment is not inherited"
[[ $fail -eq 0 ]] && echo "ISOLATION CANARY: PASS" || { echo "ISOLATION CANARY: FAIL"; exit 1; }
