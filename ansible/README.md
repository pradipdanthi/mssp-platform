# MSSP Platform — Ansible Deployment Automation

Status: KB-039 scaffolding plus KB-041 Wazuh automation preparation. No live
infrastructure execution without separate approval.

## Purpose

Ansible layout for deploying and validating the enterprise SOC stack defined in `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`.

## Directory layout

```text
ansible/
├── ansible.cfg
├── inventory/hosts.yml      # VM 100–111 placeholders
├── group_vars/all.yml       # placeholder vars — no secrets
├── playbooks/
│   ├── bootstrap.yml             # KB-039 stub
│   └── wazuh-stack-install.yml   # KB-041; preflight-safe by default
└── roles/
    └── wazuh_stack/              # KB-041 install/validate role
```

## Prerequisites (future)

- Ansible 2.14+ on operator workstation or CI runner
- SSH access to target VMs (keys via Vault — not in Git)
- Approved KB module before running any playbook against live hosts

## KB-041 safe Wazuh preparation

The Wazuh role pins expected package version `4.14.6` and defaults to:

```yaml
wazuh_execution_mode: preflight
wazuh_live_install_approved: false
```

Do not change both controls or supply an installer digest until the user
separately approves live deployment to VM 101 and confirms a pre-install
snapshot. Static validation does not contact inventory hosts:

```bash
cd /opt/mssp-control
./scripts/kb041_validate_wazuh_stack_installation_validation.sh
```

## Security

- **Never commit secrets** to this tree.
- Use Ansible Vault or runtime env for credentials.
- Customer portal safety rules apply to all ingested data — see KB-036 §9.

## Related KB modules

- KB-037 — Cluster registry planning
- KB-038 — Tenant deployment mode (`cloud` / `on_prem` / `hybrid`)
- KB-040+ — Wazuh, Suricata, and subsequent stack deployment

## Deferred execution

Do **not** run playbooks against live inventory until the target VM exists,
rollback is ready, and that exact execution is explicitly approved.
