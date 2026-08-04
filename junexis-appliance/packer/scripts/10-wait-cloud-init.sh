#!/usr/bin/env bash
# Wait for cloud-init / first boot settle before Ansible (autoinstall guests).
set -euo pipefail

if command -v cloud-init >/dev/null 2>&1; then
  # status may be "disabled" on autoinstall images; never block forever
  timeout 120 cloud-init status --wait || true
fi

# Wait for active package managers only.
# Do NOT match unattended-upgrade-shutdown (comm truncates to unattended-upgr).
for i in $(seq 1 90); do
  if ! pgrep -x apt-get >/dev/null 2>&1 \
    && ! pgrep -x apt >/dev/null 2>&1 \
    && ! pgrep -x dpkg >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
echo "cloud-init/apt wait done"

command -v python3 >/dev/null
systemctl is-active --quiet ssh || systemctl is-active --quiet sshd || true
