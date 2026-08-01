# MSSP Network & Proxmox Identity Map (DR reference)

Updated: 2026-08-01
Keep this file with your MSSP_Full_Backup copy.
Prefer restoring with the same guest IPs so Cursor can use ansible inventory + .env without rewriting.

## Core production VMs (must recreate for Path A/B)

| Proxmox VMID | Proxmox / inventory name | Linux hostname | IP | Role / tools installed today |
|---:|---|---|---|---|
| 100 | mssp-control | mssp-control | 192.168.0.201 | Control plane: Postgres, Redis, FastAPI, Admin :3000, Customer :3001 |
| 101 | wazuh-stack | wazuh-stack | 192.168.0.211 | Wazuh Manager + Indexer + Dashboard |
| 102 | thehive-shuffle / thehive_shuffle | thehiveshuffle | 192.168.0.212 | TheHive 4 + Shuffle (+ Tenzir observed on this host) |
| 106 | suricata-sensor | suricata-sensor | 192.168.0.216 | Suricata IDS + Wazuh agent; Zeek co-located (KB-047) |
| 109 | greenbone | greenbone | 192.168.0.219 | Greenbone CE + Nuclei + Vuls (`/opt/mssp-vuln-free`) + **Amass EASM agent** (`/opt/mssp-easm-agent`) |
| 110 | velociraptor | velociraptor | 192.168.0.220 | **Velociraptor DFIR + MSSP bridge :8001** |
| 112 | automation | automation | 192.168.0.222 | **Required** Ansible automation controller (included in DR backup) |

## Endpoint / lab VMs

| Proxmox VMID | Name | IP | Status |
|---:|---|---|---|
| 104 | windows-endpoint-lab | 192.168.0.214 | Windows test endpoint (Wazuh agent) |
| 105 | linux-endpoint-lab | 192.168.0.215 | Removed — reinstall later if needed |

## Planned placeholders (not live dedicated VMs)

| VMID | Name | IP | Notes |
|---:|---|---|---|
| 103 | shuffle standalone | — | Not used — Shuffle on VM 102 |
| 107 | zeek standalone | — | Not used — Zeek on VM 106 |
| 108 | misp | 192.168.0.218 | Planned — MISP not deployed yet |
| 111 | monitoring | 192.168.0.221 | Planned — Prometheus/Grafana |

## Control-plane service engines (NOT separate Proxmox VMs)

These run inside MSSP on VM 100 and are restored from the DB archive:
Phase1 Compliance/SCA, Phase2 EASM, Phase3 ITDR, Phase4 VMaaS, Phase5 NDR, Phase6 Threat Intel.

## Hypervisor

| Item | Value |
|---|---|
| Proxmox (lab docs) | Labhyp |
| Proxmox management IP | Any IP you choose when rebuilding Proxmox — does NOT need to match old Proxmox IP |
| Guest LAN | 192.168.0.0/24 on vmbr0 — KEEP guest IPs in first table the same |

## DR rule

1. Rebuild Proxmox (any mgmt IP).
2. Recreate guests with SAME guest IPs + hostnames from first table.
3. Path A restore from MSSP_Full_Backup — Cursor maps names/IPs from this file + ansible inventory + encrypted archive.
