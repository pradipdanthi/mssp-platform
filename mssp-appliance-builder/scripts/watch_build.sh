#!/usr/bin/env bash
# watch_build.sh — Monitor golden build; log progress; flag if SSH wait exceeds threshold.
set -euo pipefail
LOG="${1:-/opt/mssp-control/mssp-appliance-builder/.cache/build_golden.nohup.out}"
PVE_KEY="${HOME}/.ssh/id_ed25519_proxmox"
MAX_SSH_WAIT_SEC="${MAX_SSH_WAIT_SEC:-900}"
BUILD_KEY=/opt/mssp-control/kevantic-appliance/.tools/build-ssh/kevantic_packer

ssh_wait_since=0
last_phase=""

while true; do
  if grep -q 'BUILD_FINISHED\|PROXMOX_PACKER_BUILD_OK\|Build.*finished\|Build.*succeeded' "$LOG" 2>/dev/null; then
    echo "$(date -Is) BUILD_SUCCESS_DETECTED"
    tail -20 "$LOG"
    exit 0
  fi
  if grep -q 'Build.*errored\|Error:' "$LOG" 2>/dev/null; then
    echo "$(date -Is) BUILD_ERROR_DETECTED"
    tail -30 "$LOG"
    exit 1
  fi

  phase=$(tail -3 "$LOG" 2>/dev/null | tr '\n' ' ')
  if [[ "$phase" != "$last_phase" ]]; then
    echo "$(date -Is) $phase"
    last_phase="$phase"
  fi

  if grep -q 'Waiting for SSH' "$LOG" 2>/dev/null; then
    if [[ "$ssh_wait_since" -eq 0 ]]; then
      ssh_wait_since=$(date +%s)
    else
      now=$(date +%s)
      elapsed=$((now - ssh_wait_since))
      if (( elapsed > MAX_SSH_WAIT_SEC )); then
        echo "$(date -Is) SSH_WAIT_EXCEEDED_${MAX_SSH_WAIT_SEC}s — check VM 199 console on Proxmox"
        ssh -i "$PVE_KEY" -o BatchMode=yes root@192.168.0.191 'qm status 199 2>&1; qm config 199 2>/dev/null | egrep boot\|ide\|net0' || true
        exit 2
      fi
    fi
  fi

  if grep -q 'Connected to SSH\|Provisioning with shell\|provision_via_vm112\|ansible-playbook' "$LOG" 2>/dev/null; then
    echo "$(date -Is) SSH_CONNECTED — build progressing"
    ssh_wait_since=0
  fi

  if ! pgrep -f 'packer build.*lab.pkrvars' >/dev/null 2>&1; then
    echo "$(date -Is) PACKER_NOT_RUNNING"
    tail -20 "$LOG"
    exit 3
  fi

  sleep 30
done
