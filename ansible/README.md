# MSSP Platform — Ansible Deployment Automation

Status: **Scaffolding only** (KB-039). No live installs until KB-040+.

## Purpose

Ansible layout for deploying and validating the enterprise SOC stack defined in `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`.

## Directory layout

```text
ansible/
├── ansible.cfg
├── inventory/hosts.yml      # VM 100–111 placeholders
├── group_vars/all.yml       # placeholder vars — no secrets
└── playbooks/
    ├── bootstrap.yml        # KB-039 stub
    └── (future KB playbooks)
```

## Prerequisites (future)

- Ansible 2.14+ on operator workstation or CI runner
- SSH access to target VMs (keys via Vault — not in Git)
- Approved KB module before running any playbook against live hosts

## Security

- **Never commit secrets** to this tree.
- Use Ansible Vault or runtime env for credentials.
- Customer portal safety rules apply to all ingested data — see KB-036 §9.

## Related KB modules

- KB-037 — Cluster registry planning
- KB-038 — Tenant deployment mode (`cloud` / `on_prem` / `hybrid`)
- KB-040+ — Wazuh, Suricata, and subsequent stack deployment

## Deferred execution

Do **not** run playbooks until the matching KB is validated and VMs exist.
