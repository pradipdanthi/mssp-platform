#!/bin/sh
set -eu
SRC=tap105i0
DST=tap106i1

require_taps() {
    ip link show dev "$SRC" >/dev/null
    ip link show dev "$DST" >/dev/null
}

enable_mirror() {
    require_taps
    tc qdisc del dev "$SRC" clsact 2>/dev/null || true
    tc qdisc add dev "$SRC" clsact
    tc filter add dev "$SRC" ingress protocol all matchall action mirred egress mirror dev "$DST"
    tc filter add dev "$SRC" egress protocol all matchall action mirred egress mirror dev "$DST"
}

disable_mirror() {
    tc qdisc del dev "$SRC" clsact 2>/dev/null || true
}

status_mirror() {
    tc qdisc show dev "$SRC"
    tc filter show dev "$SRC" ingress
    tc filter show dev "$SRC" egress
}

case "${1:-}" in
    enable) enable_mirror ;;
    disable) disable_mirror ;;
    status) status_mirror ;;
    *) echo "Usage: $0 {enable|disable|status}" >&2; exit 2 ;;
esac
