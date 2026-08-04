#!/usr/bin/env bash
# Post-autoinstall bootstrap before Ansible — B2
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Do NOT match unattended-upgrade-shutdown (comm = unattended-upgr).
for i in $(seq 1 60); do
  if ! pgrep -x apt-get >/dev/null 2>&1 \
    && ! pgrep -x apt >/dev/null 2>&1 \
    && ! pgrep -x dpkg >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

for i in 1 2 3 4 5 6; do
  if apt-get update -y; then
    break
  fi
  sleep 10
done
apt-get install -y python3 python3-apt python3-pip sudo ca-certificates curl nftables
true
