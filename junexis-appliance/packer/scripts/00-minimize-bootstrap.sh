#!/usr/bin/env bash
# Post-autoinstall bootstrap before Ansible — B2
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-apt sudo ca-certificates curl nftables
# Ensure snapd path does not block minimize later
true
