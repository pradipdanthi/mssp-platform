# SOC Analyst Agent — Completion Report

**Date:** 2026-10-26  
**Status:** LIVE (lab)

## Proxmox VM

| Field | Value |
|---|---|
| VMID | **117** |
| Name | `mssp-soc-agent` |
| Node | Labhyp (`192.168.0.191`) |
| IP | **192.168.0.228**/24 |
| Specs | 4 vCPU · **6 GB RAM** · 50 GB disk (local-zfs) |
| Note | Host had ~7.8 GB free; RAM set to 6144 MB so the guest could start. Raise to 8192 when RAM frees. |
| Image | Ubuntu 24.04 cloudimg |
| SSH | `secadmin` · `~/.ssh/id_ed25519_soc_agent` · Host alias `mssp-soc-agent` |

## Agent service

| Field | Value |
|---|---|
| Path | `/opt/soc-agent` on VM 117 |
| Container | `mssp-soc-agent` |
| Health | `http://192.168.0.228:8088/health` |
| Ingest webhook | `http://192.168.0.228:8088/api/v1/ingest` |
| Auth header | `X-Soc-Agent-Token` (token in `soc-agent/data/OPERATOR_TOKEN.txt`) |
| Audit log | container `/var/log/soc-agent/audit.log` |
| Dossiers | container `/var/lib/soc-agent/dossiers/` |
| Firewall | UFW allow 22 + 8088 only |

## E2E verification

| Case | Result |
|---|---|
| A — benign internal SSH brute | `auto_close_benign` / classification `benign` · MITRE T1110 |
| B — critical C2 + payload | `escalate` · MITRE T1071 + T1486 · dossier created |

Control-plane portals (`:3000`/`:3001`/`:8000`) were not modified.
