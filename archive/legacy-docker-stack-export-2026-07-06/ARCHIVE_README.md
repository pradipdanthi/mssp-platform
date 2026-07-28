# Legacy export (archived 2026-07-28)

This tree is a **point-in-time export** that previously lived at the root of `pradipdanthi/mssp-platform` (single commit `5e6a194`, dated **2026-07-06**).

## What it is

- Docker Compose and configs for an **older lab stack** (Wazuh, OpenSearch, Filebeat, Nginx, deployment manifests).
- Inventory snapshots under `exports/inventory/`.
- **Not** the production MSSP control plane (FastAPI, PostgreSQL, Admin/Customer portals, KB modules).

## Why it was moved

The active product is developed in the **repository root** (`/opt/mssp-control` on VM 100). This export is kept for reference only and is not deployed from this path.

## Do not use for production

Use the root `AGENTS.md`, `CONTEXT.md`, and `docker-compose.yml` for the current platform.
