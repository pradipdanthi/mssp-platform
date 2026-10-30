#!/usr/bin/env bash
# READ-ONLY host diagnostic for the TIA latency investigation.
# Run it ON the host being measured (VM 117 agent, VM 100 control plane, or the Proxmox node) while a
# voice/chat test is running. It changes nothing, reads no secrets, prints no credentials, and sends
# nothing off the machine. Output is plain text to paste into the latency report.
#
#   ./scripts/tia_host_diagnostics.sh 60        # sample for 60 seconds (default 30)
set -u
DUR="${1:-30}"
echo "== host: $(hostname)  $(date -u +%FT%TZ)  kernel $(uname -r)"
echo "== cpu/mem"; nproc; free -m | sed -n '1,2p'
echo "== load (1/5/15)"; cat /proc/loadavg
echo "== CPU steal and iowait over ${DUR}s (a hypervisor starving this VM shows as steal)"
if command -v vmstat >/dev/null; then vmstat 5 $((DUR / 5 > 0 ? DUR / 5 : 1)); else echo "vmstat not installed"; fi
echo "== pressure stall info (non-zero 'some avg' means tasks waited for the resource)"
for f in cpu memory io; do [ -r /proc/pressure/$f ] && { echo "-- $f"; cat /proc/pressure/$f; }; done
echo "== top processes by CPU"; ps -eo pid,user,pcpu,pmem,etime,comm --sort=-pcpu | head -8
echo "== TIA-related services"
for u in mssp-soc-agent tia-cli-runner; do
  systemctl is-active "$u" 2>/dev/null | sed "s/^/$u: /"
  systemctl show "$u" -p ActiveEnterTimestamp -p NRestarts -p MemoryCurrent 2>/dev/null
done
echo "== network path to the control plane / agent (round-trip timing only)"
for target in "${TIA_DIAG_TARGETS:-}"; do [ -n "$target" ] && ping -c 5 -q "$target" 2>/dev/null | tail -2; done
echo "== time sync (clock offset skews cross-host timings)"
timedatectl show -p NTPSynchronized -p TimeUSec 2>/dev/null
command -v chronyc >/dev/null && chronyc tracking 2>/dev/null | sed -n '1,5p'
if [ -r /etc/pve/.version ] || command -v pveperf >/dev/null; then
  echo "== Proxmox node: per-VM CPU and memory (run on the node; read-only)"
  command -v qm >/dev/null && qm list
  command -v pvesh >/dev/null && pvesh get /nodes/$(hostname)/status --output-format json-pretty 2>/dev/null | head -30
fi
echo "== done. Paste this with the latency probe output; do not paste anything else from this host."
