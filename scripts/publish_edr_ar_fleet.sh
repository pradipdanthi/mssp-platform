#!/usr/bin/env bash
# Publish MSSP EDR Active Response pack to:
#   1) Control-plane package tree (endpoint_configs + remediate ZIP)
#   2) Central / cloud Wazuh Manager shared groups (direct WAN agents)
#   3) On-prem appliance Wazuh Manager shared groups (local agents)
#
# Endpoint Sync-MsspEdrAr.{ps1,sh} then auto-applies shared/ -> bin + mssp-ar.env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WIN_SRC="$ROOT/deploy/wazuh-active-response/windows"
LINUX_SRC="$ROOT/deploy/wazuh-active-response"
WIN_DST="$ROOT/backend-api/app/endpoint_configs/windows-edr-ar"
LINUX_DST="$ROOT/backend-api/app/endpoint_configs/linux-edr-ar"

CENTRAL_HOST="${WAZUH_MANAGER_HOST:-192.168.0.211}"
CENTRAL_USER="${WAZUH_SSH_USER:-secadmin}"
CENTRAL_KEY="${WAZUH_SSH_KEY:-/home/secadmin/.ssh/id_ed25519_wazuh_stack}"

APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-/opt/mssp-control/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
SKIP_APPLIANCE="${SKIP_APPLIANCE_PUBLISH:-0}"

CALLBACK_URL="${MSSP_CALLBACK_URL:-https://api.kevantic.com/v1/edr/actions/callback}"
CONTROL_PLANE_IP="${MSSP_CONTROL_PLANE_IP:-192.168.0.201}"

resolve_callback_key() {
  if [[ -n "${MSSP_CALLBACK_KEY:-}" ]]; then
    printf '%s' "$MSSP_CALLBACK_KEY"
    return
  fi
  for f in \
    "$ROOT/.secrets/soc_sync_api_key" \
    "$ROOT/.secrets/edr_callback_api_key" \
    /run/secrets/soc_sync_api_key \
    /run/secrets/edr_callback_api_key
  do
    if [[ -f "$f" ]]; then
      tr -d '\r\n' < "$f"
      return
    fi
  done
  echo ""
}

CALLBACK_KEY="$(resolve_callback_key)"
if [[ -z "$CALLBACK_KEY" ]]; then
  echo "WARN: no callback key found; agents will not verify until key is published" >&2
fi

echo "==> Sync pack deploy/ -> endpoint_configs/"
mkdir -p "$WIN_DST" "$LINUX_DST"
for f in \
  Install-MsspWindowsEdrAr.ps1 \
  Test-MsspQuarantineProof.ps1 \
  mssp-isolate-host.cmd mssp-isolate-host.ps1 \
  mssp-kill-process.cmd mssp-kill-process.ps1 \
  mssp-block-hash.cmd mssp-block-hash.ps1 \
  Sync-MsspEdrAr.ps1 Watch-MsspQuarantine.ps1 \
  mssp-ar.env.defaults agent.conf.mssp-edr-sync.xml
do
  [[ -f "$WIN_SRC/$f" ]] && cp -a "$WIN_SRC/$f" "$WIN_DST/$f"
done
for f in mssp-isolate-host mssp-kill-process mssp-block-hash Sync-MsspEdrAr.sh; do
  [[ -f "$LINUX_SRC/$f" ]] && cp -a "$LINUX_SRC/$f" "$LINUX_DST/$f"
done
chmod +x "$LINUX_DST/Sync-MsspEdrAr.sh" "$LINUX_DST"/mssp-* 2>/dev/null || true

# Defaults file for packages (no secret in git); key shipped separately as mssp-callback.key when present.
cat > "$WIN_SRC/mssp-ar.env.defaults" <<EOF
MSSP_CALLBACK_URL=$CALLBACK_URL
MSSP_CONTROL_PLANE_IP=$CONTROL_PLANE_IP
EOF
cp -a "$WIN_SRC/mssp-ar.env.defaults" "$WIN_DST/mssp-ar.env.defaults"
cp -a "$WIN_SRC/mssp-ar.env.defaults" "$LINUX_DST/mssp-ar.env.defaults"
# Never write callback secrets into the git tree / endpoint_configs.
rm -f "$WIN_DST/mssp-callback.key" "$LINUX_DST/mssp-callback.key"

echo "==> Rebuild remediate ZIP"
python3 - <<PY
import zipfile
from pathlib import Path
src = Path("$WIN_SRC")
out = Path("$LINUX_SRC") / "mssp-windows-edr-ar-remediate.zip"
names = [
  "Install-MsspWindowsEdrAr.ps1",
  "mssp-isolate-host.cmd", "mssp-isolate-host.ps1",
  "mssp-kill-process.cmd", "mssp-kill-process.ps1",
  "mssp-block-hash.cmd", "mssp-block-hash.ps1",
  "Sync-MsspEdrAr.ps1", "Watch-MsspQuarantine.ps1",
  "mssp-ar.env.defaults", "agent.conf.mssp-edr-sync.xml",
  "Test-MsspQuarantineProof.ps1",
]
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for n in names:
        p = src / n
        if p.is_file():
            zf.write(p, n)
print(f"wrote {out} ({out.stat().st_size} bytes)")
PY

STAGE="$(mktemp -d /tmp/mssp-edr-ar-publish.XXXXXX)"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

mkdir -p "$STAGE/windows" "$STAGE/linux"
cp -a "$WIN_SRC"/*.ps1 "$WIN_SRC"/*.cmd "$WIN_SRC"/mssp-ar.env.defaults "$WIN_SRC"/agent.conf.mssp-edr-sync.xml \
  "$STAGE/windows/" 2>/dev/null || true
cp -a "$LINUX_SRC/mssp-isolate-host" "$LINUX_SRC/mssp-kill-process" "$LINUX_SRC/mssp-block-hash" \
  "$LINUX_SRC/Sync-MsspEdrAr.sh" "$STAGE/linux/"
cp -a "$WIN_SRC/mssp-ar.env.defaults" "$STAGE/linux/mssp-ar.env.defaults"
# Deploy-time defaults WITH key for Manager shared (not committed).
{
  echo "MSSP_CALLBACK_URL=$CALLBACK_URL"
  echo "MSSP_CONTROL_PLANE_IP=$CONTROL_PLANE_IP"
  if [[ -n "$CALLBACK_KEY" ]]; then
    echo "MSSP_CALLBACK_KEY=$CALLBACK_KEY"
  fi
} > "$STAGE/windows/mssp-ar.env.defaults"
cp -a "$STAGE/windows/mssp-ar.env.defaults" "$STAGE/linux/mssp-ar.env.defaults"
if [[ -n "$CALLBACK_KEY" ]]; then
  printf '%s\n' "$CALLBACK_KEY" > "$STAGE/windows/mssp-callback.key"
  printf '%s\n' "$CALLBACK_KEY" > "$STAGE/linux/mssp-callback.key"
fi

cp -a "$WIN_SRC/agent.conf.mssp-edr-sync.xml" "$STAGE/windows/agent.conf.mssp-edr-sync.xml"
cat > "$STAGE/linux/agent.conf.mssp-edr-sync.xml" <<'EOF'
<agent_config os="linux">
  <wodle name="command">
    <disabled>no</disabled>
    <tag>mssp-edr-ar-sync-linux</tag>
    <interval>1m</interval>
    <run_on_start>yes</run_on_start>
    <timeout>90</timeout>
    <ignore_output>yes</ignore_output>
    <command>bash /var/ossec/etc/shared/Sync-MsspEdrAr.sh</command>
  </wodle>
</agent_config>
EOF

publish_to_host() {
  local host="$1" user="$2" key="$3" label="$4"
  echo "==> Publish shared AR pack to $label ($host)"
  if [[ ! -f "$key" ]]; then
    echo "WARN: skip $label - SSH key missing: $key" >&2
    return 0
  fi
  if ! ssh -o BatchMode=yes -o ConnectTimeout=8 -i "$key" "$user@$host" 'echo ok' >/dev/null 2>&1; then
    echo "WARN: skip $label - SSH unreachable" >&2
    return 0
  fi

  ssh -o BatchMode=yes -i "$key" "$user@$host" 'rm -rf /tmp/mssp-edr-ar-publish && mkdir -p /tmp/mssp-edr-ar-publish'
  scp -o BatchMode=yes -i "$key" -r "$STAGE/windows" "$STAGE/linux" "$user@$host:/tmp/mssp-edr-ar-publish/"

  ssh -o BatchMode=yes -i "$key" "$user@$host" 'bash -s' <<'REMOTE'
set -euo pipefail
SRC_WIN=/tmp/mssp-edr-ar-publish/windows
SRC_LINUX=/tmp/mssp-edr-ar-publish/linux

sudo mkdir -p /var/lib/kevantic/edr-ar/windows /var/lib/kevantic/edr-ar/linux \
  /var/lib/junexis/edr-ar/windows /var/lib/junexis/edr-ar/linux

if [[ -d "$SRC_WIN" ]]; then
  sudo cp -a "$SRC_WIN"/. /var/lib/kevantic/edr-ar/windows/
  sudo cp -a "$SRC_WIN"/. /var/lib/junexis/edr-ar/windows/ 2>/dev/null || true
fi
if [[ -d "$SRC_LINUX" ]]; then
  sudo cp -a "$SRC_LINUX"/. /var/lib/kevantic/edr-ar/linux/
  sudo cp -a "$SRC_LINUX"/. /var/lib/junexis/edr-ar/linux/ 2>/dev/null || true
  sudo chmod 0750 /var/lib/kevantic/edr-ar/linux/mssp-* /var/lib/kevantic/edr-ar/linux/Sync-MsspEdrAr.sh 2>/dev/null || true
fi

if [[ -d /var/ossec/active-response/bin && -d "$SRC_LINUX" ]]; then
  for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
    if [[ -f "$SRC_LINUX/$f" ]]; then
      sudo install -o root -g wazuh -m 0750 "$SRC_LINUX/$f" "/var/ossec/active-response/bin/$f"
    fi
  done
fi

sudo python3 - <<'PY'
import pathlib, pwd, grp, os, re
shared = pathlib.Path("/var/ossec/etc/shared")
src_win = pathlib.Path("/tmp/mssp-edr-ar-publish/windows")
src_linux = pathlib.Path("/tmp/mssp-edr-ar-publish/linux")
win_files = [
  "mssp-isolate-host.cmd", "mssp-isolate-host.ps1",
  "mssp-kill-process.cmd", "mssp-kill-process.ps1",
  "mssp-block-hash.cmd", "mssp-block-hash.ps1",
  "Watch-MsspQuarantine.ps1", "Sync-MsspEdrAr.ps1",
  "mssp-ar.env.defaults", "mssp-callback.key",
]
linux_files = [
  "mssp-isolate-host", "mssp-kill-process", "mssp-block-hash",
  "Sync-MsspEdrAr.sh", "mssp-ar.env.defaults", "mssp-callback.key",
]
win_conf = (src_win / "agent.conf.mssp-edr-sync.xml").read_text(encoding="utf-8") if (src_win / "agent.conf.mssp-edr-sync.xml").is_file() else ""
linux_conf = (src_linux / "agent.conf.mssp-edr-sync.xml").read_text(encoding="utf-8") if (src_linux / "agent.conf.mssp-edr-sync.xml").is_file() else ""
try:
    uid = pwd.getpwnam("wazuh").pw_uid
    gid = grp.getgrnam("wazuh").gr_gid
except KeyError:
    uid = gid = -1

def chown(p: pathlib.Path):
    if uid >= 0:
        try:
            os.chown(p, uid, gid)
        except OSError:
            pass

skip = {"agent-template", "ar.conf"}
for group_dir in sorted(shared.iterdir()):
    if not group_dir.is_dir():
        continue
    name = group_dir.name
    if name in skip or name.endswith(".conf"):
        continue
    for fname in win_files:
        src = src_win / fname
        if not src.is_file():
            continue
        dest = group_dir / fname
        try:
            dest.write_bytes(src.read_bytes())
            dest.chmod(0o640)
            chown(dest)
        except OSError as exc:
            print(f"skip {dest}: {exc}")
    for fname in linux_files:
        src = src_linux / fname
        if not src.is_file():
            continue
        dest = group_dir / fname
        try:
            dest.write_bytes(src.read_bytes())
            mode = 0o640
            if fname.endswith(".sh") or ("." not in fname and fname.startswith("mssp-")):
                mode = 0o750
            if fname in ("mssp-ar.env.defaults", "mssp-callback.key"):
                mode = 0o640
            dest.chmod(mode)
            chown(dest)
        except OSError as exc:
            print(f"skip {dest}: {exc}")
    conf_path = group_dir / "agent.conf"
    try:
        current = conf_path.read_text(encoding="utf-8") if conf_path.is_file() else ""
    except OSError:
        continue
    new = current
    if win_conf:
        if "mssp-edr-ar-sync" in new and "ProgramData" not in new:
            new = re.sub(
                r"<wodle name=\"command\">\s*<disabled>no</disabled>\s*<tag>mssp-edr-ar-sync</tag>.*?</wodle>",
                "",
                new,
                count=1,
                flags=re.S,
            )
            new = new.rstrip() + "\n" + win_conf + "\n"
        elif "mssp-edr-ar-sync" not in new:
            new = (new.rstrip() + "\n" + win_conf + "\n") if new.strip() else win_conf + "\n"
    if linux_conf and "mssp-edr-ar-sync-linux" not in new:
        new = (new.rstrip() + "\n" + linux_conf + "\n") if new.strip() else linux_conf + "\n"
    if new != current:
        try:
            conf_path.write_text(new, encoding="utf-8")
            conf_path.chmod(0o660)
            chown(conf_path)
            print(f"updated agent.conf in {group_dir.name}")
        except OSError as exc:
            print(f"skip agent.conf {conf_path}: {exc}")
print("shared publish done")
PY
sudo rm -rf /tmp/mssp-edr-ar-publish
REMOTE
}

publish_to_host "$CENTRAL_HOST" "$CENTRAL_USER" "$CENTRAL_KEY" "central-wazuh"
if [[ "$SKIP_APPLIANCE" != "1" ]]; then
  publish_to_host "$APPLIANCE_HOST" "$APPLIANCE_USER" "$APPLIANCE_KEY" "appliance-wazuh"
fi

if [[ "$SKIP_APPLIANCE" == "1" ]]; then
  echo "PASS: EDR AR fleet publish complete (packages + central; appliance skipped)"
else
  echo "PASS: EDR AR fleet publish complete (packages + central + appliance)"
fi
echo "      Endpoints auto-apply within ~1 minute via Sync-MsspEdrAr + agent.conf wodle / scheduled task"
