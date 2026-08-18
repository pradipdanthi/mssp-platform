#!/usr/bin/env bash
# KB-041: Validate prepared Wazuh automation without contacting live hosts.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-041: Validate Wazuh Stack Installation and Validation"
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

section "1. Required files exist"

REQUIRED=(
  "docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md"
  "scripts/kb041_validate_wazuh_stack_installation_validation.sh"
  "ansible/playbooks/wazuh-stack-install.yml"
  "ansible/group_vars/all.yml"
  "ansible/roles/wazuh_stack/defaults/main.yml"
  "ansible/roles/wazuh_stack/tasks/main.yml"
  "ansible/roles/wazuh_stack/handlers/main.yml"
  "docs/KB040_WAZUH_STACK_VM_DEPLOYMENT_PLAN.md"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-041 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-041 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB041 execution plan required mentions"

file_mentions docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md \
  "Purpose" \
  "VM 101" \
  "wazuh-stack-install" \
  "4.14.6" \
  "preflight" \
  "SHA-256" \
  "separate approval" \
  "snapshot" \
  "rollback" \
  "KB-036" \
  "KB-037" \
  "KB-038" \
  "no secrets" \
  "customer portal" \
  "raw" \
  "never" \
  "NOT" \
  "live" \
  "Deferred" \
  "deferred"
echo "OK: KB041 doc records automation controls, rollback, and approval gate."

section "4. Parse all KB-041 YAML"

python3 - <<'PY'
from pathlib import Path
import yaml

paths = [
    Path("ansible/group_vars/all.yml"),
    Path("ansible/playbooks/wazuh-stack-install.yml"),
    Path("ansible/roles/wazuh_stack/defaults/main.yml"),
    Path("ansible/roles/wazuh_stack/tasks/main.yml"),
    Path("ansible/roles/wazuh_stack/handlers/main.yml"),
]
for path in paths:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        raise SystemExit(f"{path} parsed as empty YAML")
    print(f"parsed: {path}")
PY
echo "OK: KB-041 YAML parses successfully."

section "5. Verify safe defaults and installation interlocks"

python3 - <<'PY'
from pathlib import Path
import yaml

group_vars = yaml.safe_load(Path("ansible/group_vars/all.yml").read_text())
defaults = yaml.safe_load(
    Path("ansible/roles/wazuh_stack/defaults/main.yml").read_text()
)

for source in (group_vars, defaults):
    assert source["wazuh_version"] == "4.14.6"
    assert source["wazuh_repository_major_minor"] == "4.14"
    assert source["wazuh_execution_mode"] == "preflight"
    assert source["wazuh_live_install_approved"] is False
    assert source["wazuh_install_assistant_sha256"] == (
        "cb7f4ca737a798e4ed98c73579a6105b4dab45aa967bc1c0154f85ab2951b209"
    )

playbook = Path("ansible/playbooks/wazuh-stack-install.yml").read_text()
tasks = Path("ansible/roles/wazuh_stack/tasks/main.yml").read_text()

required_playbook = ["hosts: wazuh_stack", "role: wazuh_stack", "gather_facts: true"]
required_tasks = [
    'wazuh_execution_mode == "install"',
    "wazuh_live_install_approved | bool",
    "wazuh_install_assistant_sha256",
    'checksum: "sha256:',
    "no_log: true",
    "ansible_host is defined",
    'deployment_role == "wazuh_cluster"',
    "package_facts:",
    "service_facts:",
    "wait_for:",
    "wazuh_install_marker",
    "check_mode: false",
    "Verify Wazuh TCP ports are available",
    "443|1514|1515|55000|9200",
    "wazuh_install_credentials_archive",
    'mode: "0600"',
    "ansible_processor_vcpus",
    "wazuh_root_available_bytes",
    "/var/run/reboot-required",
    "validate_certs: true",
    'hash("sha256")',
]

for needle in required_playbook:
    assert needle in playbook, f"playbook missing: {needle}"
for needle in required_tasks:
    assert needle in tasks, f"role tasks missing: {needle}"
PY
echo "OK: safe defaults, target guard, integrity gate, and validation checks exist."

section "6. Optional Ansible syntax check (never contacts inventory hosts)"

if command -v ansible-playbook >/dev/null 2>&1; then
  ANSIBLE_CONFIG="$PROJECT_DIR/ansible/ansible.cfg" \
    ansible-playbook --syntax-check ansible/playbooks/wazuh-stack-install.yml \
    || fail "ansible-playbook syntax check failed"
  echo "OK: ansible-playbook syntax check passed."
else
  echo "SKIP: ansible-playbook is not installed; strict PyYAML parsing passed."
fi

section "7. No obvious secrets in KB-041 files"

SCAN_FILES=(
  docs/KB041_WAZUH_STACK_INSTALLATION_VALIDATION.md
  ansible/README.md
  ansible/group_vars/all.yml
  ansible/playbooks/wazuh-stack-install.yml
  ansible/roles/wazuh_stack/defaults/main.yml
  ansible/roles/wazuh_stack/tasks/main.yml
  ansible/roles/wazuh_stack/handlers/main.yml
)

SECRET_HIT="$(grep -REn \
  -e 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'api_key[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'token[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{8,}' \
  -e 'JWT_SECRET[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]+' \
  -e 'Bearer[[:space:]]+[A-Za-z0-9_-]{20,}' \
  "${SCAN_FILES[@]}" 2>/dev/null || true)"

if [ -n "$SECRET_HIT" ]; then
  echo "$SECRET_HIT" >&2
  fail "Possible secret material found in KB-041 files"
fi
echo "OK: no obvious secret assignments in KB-041 files."

section "8. Confirm validation made no infrastructure connection"

echo "OK: validator performed local source checks only; no Ansible playbook was executed."

section "9. Final verdict"

echo "======================================================================"
echo "KB-041 WAZUH STACK INSTALLATION VALIDATION PASSED"
echo "======================================================================"
