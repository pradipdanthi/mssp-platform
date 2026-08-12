# MSSP environment configuration (KB-094)

**Never commit real secrets.** Copy an example file to a private location, fill in values, then link or copy to `/opt/mssp-control/.env` on the control-plane host.

## Files

| File | Use when |
|------|----------|
| `control-plane.lab.example.env` | Lab / Proxmox VM 100 (`192.168.0.201`) |
| `control-plane.production.example.env` | Production or cloud control plane (hostnames + TLS) |
| `engines.lab.example.env` | Reference for engine adapter URLs (lab IPs) — merge into `.env` |
| `engines.production.example.env` | Reference for production engine hostnames |
| `validation.lab.example.env` | Template for **validator passwords** → copy to `.secrets/validation.env` |

## Validation passwords (so the agent never skips kb011)

Validators need the five **lab demo user** passwords. Store them once (never in git):

```bash
cp deploy/environments/validation.lab.example.env .secrets/validation.env
chmod 600 .secrets/validation.env
# Edit — fill PLATFORM_ADMIN_PASSWORD, SOC_MANAGER_PASSWORD, etc.
```

After that, `./scripts/run_post_change_checks.sh` and `kb011_validate_protected_apis.sh` run **without prompts** and the agent does not skip auth regression checks.

## Quick start (lab)

```bash
cd /opt/mssp-control
cp deploy/environments/control-plane.lab.example.env .env
# Edit .env — set POSTGRES_PASSWORD, REDIS_PASSWORD, JWT_SECRET (never commit)
mkdir -p .secrets   # engine bridge files — see DOCS/CURSOR_REDEPLOYMENT_PLAYBOOK.md
./scripts/production_deploy_control_plane.sh
```

## Quick start (production / cloud — first install)

1. Provision Linux host (Ubuntu 24.04 LTS recommended), Docker Engine + Compose plugin.
2. Clone this repo to `/opt/mssp-control` at a **git tag** (see `deploy/RELEASE_CHECKLIST.md`).
3. Copy `control-plane.production.example.env` → `.env`; set all `<REQUIRED>` values.
4. Copy engine URL section from `engines.production.example.env` into `.env`.
5. Populate `.secrets/` from your vault (Wazuh, TheHive, MISP, etc.).
6. Run `./scripts/production_deploy_control_plane.sh`.
7. Run `./scripts/bootstrap_platform_admin.sh` (KB-020) — **do not** run demo seed.
8. Deploy engines with `./scripts/production_deploy_engines.sh` (after inventory is filled).

## Cloud provider note

AWS, Azure, and GCP differ only in **Layer 2** (VMs, DNS, TLS, managed Postgres optional). The **recipe** (git) and **scripts** are the same. Fill `ansible/inventory/production.example.yml` with your hostnames when engines are ready.
