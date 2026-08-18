# MSSP Platform — Ansible Deployment Automation

Status: Live controller on **VM 112**. Source of truth for playbooks/roles is
`/opt/mssp-control/ansible` on VM 100; sync to the controller before runs.

## Purpose

Ansible layout for deploying and validating the enterprise SOC stack defined in
`docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`.

**Kevantic edge appliance image builds** use a separate tree (`kevantic-appliance/`)
and Proxmox factory VM 113 — see `docs/KB093F_PROXMOX_APPLIANCE_BUILD_VM.md`.
Those roles are **not** mixed into SOC stack install playbooks.

## Controller (VM 112)

| Item | Value |
|------|--------|
| Host | `automation` / `192.168.0.222` |
| Ansible | Core **2.16.3** |
| Working copy | `/home/secadmin/mssp-automation/ansible` |
| Sync from VM 100 | `./scripts/sync_ansible_controller.sh` |

### Keep the controller current

```bash
cd /opt/mssp-control
./scripts/sync_ansible_controller.sh
```

This rsyncs playbooks/roles/inventory, aligns SSH key names on the controller,
syntax-checks playbooks, and pings known-live hosts. It does **not** install or
upgrade any SOC component.

## Can this redeploy the whole stack?

**Partially — by component, with approval — not one blind “redeploy all” button.**

| Area | Playbook | Notes |
|------|----------|--------|
| Wazuh | `playbooks/wazuh-stack-install.yml` | Defaults to preflight; live install needs explicit flags + snapshot. Asserts `vm_id==101`. |
| Linux mid-layer EDR | `playbooks/mssp-linux-midlayer-manager.yml` | After Manager exists. Rules 110001–110005 + Linux shared helper. Cloud-portable (no VM 101 identity assert). |
| TheHive/Shuffle | `playbooks/case-soar.yml` | Co-located VM 102 |
| Suricata | `playbooks/suricata-sensor.yml` (+ wazuh forward) | VM 106 |
| Greenbone | `playbooks/greenbone.yml` | VM 109 |
| Nuclei/Vuls | `playbooks/vuln-free-stack.yml` | VM 109 |
| Velociraptor / MISP / Zeek / EASM | respective playbooks | Only when that KB is approved |

There is **no** single playbook that tears down and rebuilds every VM safely.
Treat “full stack redeploy” as: sync controller → snapshot targets → run each
approved playbook in dependency order.

**KB-094:** Normal control-plane deploy uses `./scripts/production_deploy_control_plane.sh`.
Engine orchestration (dry-run by default): `./scripts/production_deploy_engines.sh`.
Production inventory template: `inventory/production.example.yml`.

## Directory layout (VM 100 source)

```text
ansible/
├── ansible.cfg
├── inventory/hosts.yml
├── group_vars/all.yml
├── playbooks/          # one playbook per component
└── roles/
```

## Security

- Never commit secrets.
- Controller SSH keys live under `secadmin` on VM 112.
- Do not run install playbooks against live inventory without explicit approval.

## Related

- KB-039 / KB-041 — automation foundation / Wazuh
- KB-093F — Kevantic Proxmox build VM (factory, separate from SOC stack)
