# VM 105 — Linux endpoint lab (decommissioned)

Status: **2026-07-29** — Proxmox VM **105** (`linux-endpoint-lab`) was **stopped and destroyed** (`qm destroy 105 --purge`) so you can install Ubuntu manually with full control.

## What was cleaned

| Area | Action |
|------|--------|
| Proxmox | VM 105 removed (VMID free for reuse) |
| Ansible inventory | `linux-endpoint-lab` host commented out |
| Greenbone host map | `192.168.0.215` entry removed |
| Vuln scan targets (DEMO) | Linux IP removed |
| Wazuh Manager | Agent `001` / `linux-endpoint-lab` was already absent |
| Control plane DB | No `protected_assets` row for that host |

Architecture docs (KB-036, KB-042) still describe **VM 105** as the Linux lab **slot** — only the live VM and automation hooks were removed.

## When you recreate the VM (manual Ubuntu)

1. In **Proxmox**, create a new VM with **VMID 105** (or another ID — update inventory if you change it).
2. Install **Ubuntu Server**; set **root password** and/or your admin user as you prefer.
3. Give it a static IP (lab convention was **`192.168.0.215`**, hostname **`linux-endpoint-lab`**).
4. Uncomment and adjust **`ansible/inventory/hosts.yml`** under `endpoint_lab` → `linux-endpoint-lab`.
5. Install the Wazuh agent (MSSP one-liner or Ansible `wazuh-agent-linux.yml` after approval).
6. Add scan targets back in **`config/vuln_scan_targets.yml`** and **`config/greenbone_host_tenant_map.yml`** only if you want scanning on that IP.

## Optional: traffic mirror to Suricata (VM 106)

If you use the KB-043 mirror again after VM 105 exists:

```bash
ssh labhyp '/usr/local/sbin/mssp-kb043-mirror-vm105-to-106.sh enable'
```

(Disable with `disable` before stopping the Linux VM.)

No secrets in this file.
