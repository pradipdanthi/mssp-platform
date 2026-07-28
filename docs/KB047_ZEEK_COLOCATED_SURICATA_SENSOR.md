# KB-047 — Zeek co-located on Suricata sensor (VM 106)

## Target

- **Host:** `suricata-sensor` — `192.168.0.216`
- **Co-located with:** Suricata IDS on management/capture path
- **Control plane:** Does not run Zeek; alerts arrive via Wazuh agent localfile → existing KB-063 ingress

## Deployment options

| Option | When | Steps |
|--------|------|--------|
| Dedicated capture NIC | Production mirror port available | Proxmox: `scripts/kb047_proxmox_add_zeek_capture_nic.sh` → guest: `scripts/kb047_configure_zeek_capture_nic_vm106.sh` → `ZEEK_CAPTURE_IF=enp6s20 ./scripts/kb047_install_zeek_docker_vm106.sh` |
| Shared capture (interim) | Single mirror to `enp6s19` | `ZEEK_CAPTURE_IF=enp6s19 ./scripts/kb047_install_zeek_docker_vm106.sh` |

## Wazuh forwarding

After Zeek logs under `/opt/zeek-logs`, apply Ansible role `zeek_wazuh` via `ansible/playbooks/zeek-on-suricata-sensor.yml` so the Wazuh agent ships Zeek notices to the manager.

## Taxonomy (KB-082)

Ingested Zeek-backed alerts should carry `source_tool=zeek` (or Zeek rule metadata in `raw_event`) so admin taxonomy maps them to **Network IDS / Sensors** (`network_ids_sensors`).

## Validate on sensor

```bash
ssh -i /home/secadmin/.ssh/id_ed25519_suricata secadmin@192.168.0.216 'systemctl is-active mssp-zeek-docker.service; docker ps --filter name=mssp-zeek'
```
