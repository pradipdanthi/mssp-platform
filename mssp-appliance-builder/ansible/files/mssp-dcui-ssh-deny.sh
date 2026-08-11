#!/bin/sh
# Stub: network console must never be launched from SSH.
echo "────────────────────────────────────────────" >&2
echo "  Kevantic Console is DISABLED over SSH." >&2
echo "  Use Proxmox → VM → Console (graphical tty1)." >&2
echo "────────────────────────────────────────────" >&2
exit 2
