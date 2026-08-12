#!/usr/bin/env bash
# Push KB-093P critical-alert forwarder onto an already-deployed appliance.
# For FUTURE appliances: rebuild golden image (install-provision.yml) instead.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER_NAME="${2:-junexis}"

if [[ -z "$HOST" ]]; then
  echo "Usage: $0 <appliance-ip> [ssh-user]" >&2
  echo "Example: $0 192.168.0.226 junexis" >&2
  echo
  echo "This is a ONE-TIME field upgrade for boxes built before KB-093P."
  echo "New appliances must get this from the golden image rebuild — not this script."
  exit 1
fi

export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook \
  -i "${HOST}," \
  -e "ansible_user=${USER_NAME}" \
  -e "ansible_become=true" \
  -e "ansible_python_interpreter=/usr/bin/python3" \
  "$ROOT/ansible/playbooks/upgrade-critical-alert-forwarder.yml"
