# MSSP Control Plane (Kestrel / MSSP platform)

Multi-tenant **Managed Security Service Provider (MSSP)** control plane: FastAPI backend, PostgreSQL, Redis, Admin SOC dashboard (`:3000`), and Customer portal (`:3001`). Detection engines (Wazuh, Suricata, Zeek, TheHive, Shuffle, Nuclei, Vuls, Greenbone CE) integrate as **backend adapters only**—customers never log into those tools directly.

**Production path on VM 100:** `/opt/mssp-control` (same design intended to migrate to cloud later).

## Repository layout

| Path | Purpose |
|------|---------|
| `backend-api/` | FastAPI application |
| `frontend-admin/` | SOC / Admin UI (nginx build) |
| `frontend-customer/` | Customer portal (nginx build) |
| `postgres/init/` | Schema and additive migrations |
| `ansible/` | Engine VM deployment (Wazuh, Suricata, Zeek, vuln stack, …) |
| `docs/` | KB modules and architecture (`KB036`, `KB082`, …) |
| `scripts/` | Validation and operational scripts per KB |
| `archive/legacy-docker-stack-export-2026-07-06/` | **Archived** pre-control-plane GitHub export (reference only) |

## Start here

1. `AGENTS.md` — rules for humans and AI agents  
2. `CONTEXT.md` — current validated baseline and services  
3. `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` — enterprise stack roadmap  

## Validate (on the control plane host)

```bash
cd /opt/mssp-control
docker compose ps
curl -fsS http://localhost:8000/health
./scripts/kb011_validate_protected_apis.sh
./scripts/kb082_validate_soc_alert_taxonomy.sh
```

## Git baseline

- **Branch:** `kb039-kb060-platform-roadmap-execution` (feature integration) / `main` (foundation through KB-008)  
- **Tag (KB-082):** `kb082-soc-alert-taxonomy-validated`  

Secrets: use `.env` on the server only (never committed). See `.gitignore`.

## Remote

Canonical GitHub: [github.com/pradipdanthi/mssp-platform](https://github.com/pradipdanthi/mssp-platform)
