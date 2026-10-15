#!/usr/bin/env bash
# Proxmox host (192.168.0.191): 8 GiB zstd zram swap as an OOM safety net.
# The lab overcommits RAM (~77 GiB configured on 60 GiB, KSM-backed) and the
# host has no disk swap (rpool is ZFS; swap on a zvol can deadlock).
# swappiness=10 keeps zram idle until the host is genuinely under pressure.
# Run on the Proxmox host as root. Idempotent.
set -euo pipefail

DEBIAN_FRONTEND=noninteractive apt-get install -y -q systemd-zram-generator

cat > /etc/systemd/zram-generator.conf <<'EOF'
[zram0]
zram-size = 8192
compression-algorithm = zstd
swap-priority = 100
EOF

cat > /etc/sysctl.d/90-mssp-zram.conf <<'EOF'
# Hypervisor: zram swap is an OOM safety net, not working memory.
vm.swappiness = 10
EOF
sysctl -q -p /etc/sysctl.d/90-mssp-zram.conf

systemctl daemon-reload
systemctl start systemd-zram-setup@zram0.service
systemctl start dev-zram0.swap
swapon --show
