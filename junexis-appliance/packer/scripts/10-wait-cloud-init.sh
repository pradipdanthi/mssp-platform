#!/usr/bin/env bash
# Wait for cloud-init / first boot settle before Ansible (autoinstall guests).
set -euo pipefail
if command -v cloud-init >/dev/null 2>&1; then
  cloud-init status --wait || true
fi
# Ensure SSH is up and python3 exists for Ansible
command -v python3 >/dev/null
systemctl is-active --quiet ssh || systemctl is-active --quiet sshd || true
