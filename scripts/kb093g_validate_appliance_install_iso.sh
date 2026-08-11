#!/usr/bin/env bash
# KB-093G validation — install ISO pipeline + license mint/verify + idle roles
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/kevantic-appliance"
PASS=0
fail() { echo "FAIL: $*"; exit 1; }
ok() { echo "PASS: $*"; PASS=$((PASS + 1)); }

[[ -f "$APP/iso/build_install_iso.sh" ]] || fail "missing iso/build_install_iso.sh"
[[ -f "$APP/iso/docker_remaster.sh" ]] || fail "missing iso/docker_remaster.sh"
[[ -f "$APP/iso/autoinstall/user-data" ]] || fail "missing autoinstall user-data"
[[ -f "$APP/iso/firstboot/kevantic-firstboot.sh" ]] || fail "missing firstboot script"
grep -q 'ANSIBLE_ROLES_PATH' "$APP/iso/firstboot/kevantic-firstboot.sh" \
  || fail "firstboot must set ANSIBLE_ROLES_PATH (customer installs must find roles)"
grep -q 'ANSIBLE_CONFIG' "$APP/iso/firstboot/kevantic-firstboot.sh" \
  || fail "firstboot must set ANSIBLE_CONFIG to payload ansible.cfg"
grep -q 'group_vars/all.yml' "$APP/iso/firstboot/kevantic-firstboot.sh" \
  || fail "firstboot must load group_vars/all.yml (control plane URL)"
# Bash ${#arr[@]} becomes a Jinja comment ({#) and breaks customer firstboot.
# Also ban '{#' inside shell/task YAML (including comments inside | blocks).
if rg -n '\$\{#|\{#' "$APP/ansible/roles" --glob '*.yml' >/tmp/kb093g-jinja-hash.txt 2>/dev/null; then
  fail "Ansible roles contain {# Jinja trap (use a counter loop, never \${#arr[@]}) — see $(head -8 /tmp/kb093g-jinja-hash.txt)"
fi
# meta: end_role fails on some ansible packaging paths ("invalid meta action"); use when/block.
if rg -n 'end_role' "$APP/ansible/roles" --glob '*.yml' >/tmp/kb093g-end-role.txt 2>/dev/null; then
  fail "ansible roles must not use meta:end_role — see $(head -5 /tmp/kb093g-end-role.txt)"
fi
ok "no meta:end_role in ansible roles"
grep -q 'autoinstall' "$APP/iso/autoinstall/user-data" || fail "user-data missing autoinstall"
grep -q 'ubuntu-server-minimal' "$APP/iso/autoinstall/user-data" || fail "user-data must force ubuntu-server-minimal"
grep -q 'interactive-sections: \[\]' "$APP/iso/autoinstall/user-data" || fail "user-data must set interactive-sections: []"
grep -q 'Install Kevantic Appliance' "$APP/iso/docker_remaster.sh" || fail "remaster must brand GRUB as Kevantic automatic install"
[[ -f "$APP/iso/boot-splash/kevantic-boot.png" ]] || fail "missing boot splash PNG"
[[ -f "$APP/ansible/roles/boot_splash/tasks/main.yml" ]] || fail "missing boot_splash role"
grep -q 'boot_splash' "$APP/ansible/playbooks/install-provision.yml" || fail "boot_splash not in install-provision"
grep -q 'minimize_engine_protect_packages' "$APP/ansible/roles/minimize/defaults/main.yml" || fail "minimize missing engine protect list"
# plymouth must stay installable for splash — must not appear under minimize_purge_packages
python3 - <<'PY' "$APP/ansible/roles/minimize/defaults/main.yml" || fail "minimize must NOT purge plymouth (needed for Kevantic splash)"
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text().splitlines()
in_purge = False
for line in text:
    if line.startswith("minimize_purge_packages:"):
        in_purge = True
        continue
    if in_purge and line and not line.startswith(" ") and not line.startswith("\t") and not line.startswith("#"):
        in_purge = False
    if in_purge and line.strip() == "- plymouth":
        raise SystemExit(1)
raise SystemExit(0)
PY
grep -q 'catalogue_engines' "$APP/ansible/playbooks/install-provision.yml" || fail "catalogue_engines not in install-provision"
grep -qi 'fluent' "$ROOT/docs/KB093G_APPLIANCE_ISO_ENTITLEMENT_PLAN.md" || fail "KB093G Fluent Bit section"
ok "install ISO scaffolding present (unattended minimized + splash + idle engines)"

# Ansible roles no longer placeholders
for role in license_enforcer service_manager wazuh_local harden_cis auditd container_runtime apparmor_profiles channel_agent ota_staging boot_splash; do
  if grep -q 'scaffold-only' "$APP/ansible/roles/$role/tasks/main.yml" 2>/dev/null; then
    fail "role $role still scaffold-only"
  fi
  [[ -f "$APP/ansible/roles/$role/tasks/main.yml" ]] || fail "missing role $role"
  ok "role $role implemented"
done
grep -q 'fluent-bit' "$APP/ansible/roles/wazuh_local/tasks/main.yml" || fail "Fluent Bit not in wazuh_local"
grep -q 'thehive' "$APP/ansible/roles/wazuh_local/tasks/main.yml" || fail "TheHive forbid check missing"
grep -q 'offline' "$APP/ansible/roles/wazuh_local/tasks/main.yml" || fail "offline package pool not wired in wazuh_local"
[[ -x "$APP/scripts/b2_fetch_offline_packages.sh" ]] || fail "missing b2_fetch_offline_packages.sh"
grep -q 'offline-packages' "$APP/iso/build_install_iso.sh" || fail "build_install_iso does not stage offline-packages"
grep -qE '(^|[[:space:]])channel([[:space:]]|$)' "$APP/iso/build_install_iso.sh" || fail "build_install_iso does not stage channel/"
grep -qE '(^|[[:space:]])ota([[:space:]]|$)' "$APP/iso/build_install_iso.sh" || fail "build_install_iso does not stage ota/"
grep -q '192.168.0.224:8000' "$APP/ansible/group_vars/all.yml" || fail "group_vars missing Appliance Mgmt VM114 URL"
grep -q 'default_control_plane' "$APP/cli/kevantic-cli/kevantic_cli/state.py" || fail "CLI missing default_control_plane"
ok "Fluent Bit on appliance; TheHive forbidden; offline pool + channel/ota + VM114 defaults"

if compgen -G "$APP/iso/offline-packages/wazuh-manager"*.deb >/dev/null \
  && compgen -G "$APP/iso/offline-packages/fluent-bit"*.deb >/dev/null \
  && compgen -G "$APP/iso/offline-packages/suricata"*.deb >/dev/null \
  && [[ -x "$APP/iso/offline-packages/bin/nuclei" ]] \
  && [[ -x "$APP/iso/offline-packages/bin/vuls" ]] \
  && compgen -G "$APP/iso/offline-packages/zeek"*.deb >/dev/null; then
  ok "offline-packages: wazuh, fluent-bit, suricata, zeek, nuclei, vuls"
else
  echo "WARN: offline-packages incomplete — run kevantic-appliance/scripts/b2_fetch_offline_packages.sh"
fi
[[ -f "$APP/engines/kevantic_engine_worker.py" ]] || fail "missing engines/kevantic_engine_worker.py"
[[ -f "$APP/ansible/roles/catalogue_engines/tasks/main.yml" ]] || fail "missing catalogue_engines role"
grep -q 'catalogue_engines' "$APP/ansible/playbooks/install-provision.yml" || fail "catalogue_engines not in install-provision"
ok "catalogue engine worker + role wired"

# CLI license commands
grep -q 'license' "$APP/cli/kevantic-cli/kevantic_cli/cli.py" || fail "CLI license subcommand missing"
ok "kevantic-cli license commands present"

# Backend license service + admin route
[[ -f "$ROOT/backend-api/app/services/kevantic_license.py" ]] || fail "missing kevantic_license.py"
grep -q 'appliance-licenses' "$ROOT/backend-api/app/api/routes/entitlements.py" || fail "mint route missing"
grep -q 'cryptography==' "$ROOT/backend-api/requirements.txt" || fail "cryptography not pinned"
ok "control-plane license mint path present"

# Ansible syntax (if ansible-playbook available)
if command -v ansible-playbook >/dev/null 2>&1; then
  ansible-playbook --syntax-check "$APP/ansible/playbooks/site.yml" >/dev/null
  ok "site.yml syntax-check"
else
  ok "ansible-playbook not on host — syntax-check skipped"
fi

# License round-trip (ephemeral keys)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 - <<'PY' "$TMP" "$ROOT"
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[2]) / "backend-api"))
from app.services.kevantic_license import generate_keypair, mint_license, verify_license

tmp = Path(sys.argv[1])
priv_pem, pub_pem = generate_keypair()
(tmp / "priv.pem").write_bytes(priv_pem)
(tmp / "pub.pem").write_bytes(pub_pem)
from cryptography.hazmat.primitives.serialization import load_pem_private_key
key = load_pem_private_key(priv_pem, password=None)
minted = mint_license(
    tenant_id="11111111-1111-1111-1111-111111111111",
    service_ids=["svc-01", "svc-06"],
    appliance_id="22222222-2222-2222-2222-222222222222",
    fingerprint="lab-fp-1",
    contract_id="C-LAB-1",
    core=True,
    private_key=key,
)
claims = verify_license(minted["license_jws"], public_key_pem=pub_pem, fingerprint="lab-fp-1")
assert "svc-01" in claims["svc"] and "svc-06" in claims["svc"]
(tmp / "license.jws").write_text(minted["license_jws"] + "\n", encoding="utf-8")
print("LICENSE_ROUNDTRIP_OK", claims["jti"])
PY
ok "license mint/verify round-trip"

# CLI apply against temp state
export KEVANTIC_STATE_DIR="$TMP/state"
export KEVANTIC_LICENSE_PUBKEY="$TMP/pub.pem"
mkdir -p "$TMP/state" "$APP/licensing/keys"
# point CLI pubkey candidate via env
PYTHONPATH="$APP/cli/kevantic-cli${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m kevantic_cli license apply --file "$TMP/license.jws" --fingerprint lab-fp-1 --json \
  | grep -q '"ok": true' || fail "CLI license apply failed"
PYTHONPATH="$APP/cli/kevantic-cli${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m kevantic_cli license show --json | grep -q 'svc-01' || fail "CLI license show missing svc-01"
ok "CLI license apply/show"

# ISO cache presence (build is separate / long)
if [[ -f "$APP/.cache/ubuntu-24.04.4-live-server-amd64.iso" ]]; then
  ok "Ubuntu live ISO cached for remaster"
else
  echo "WARN: Ubuntu ISO not cached — run kevantic-appliance/scripts/b2_fetch_ubuntu_iso.sh before build"
fi

echo ""
echo "KB093G_VALIDATE_OK checks_passed=$PASS"
echo "Next: $APP/iso/build_install_iso.sh  # produces .cache/dist-install/Kevantic-Appliance-Install-*.iso"
