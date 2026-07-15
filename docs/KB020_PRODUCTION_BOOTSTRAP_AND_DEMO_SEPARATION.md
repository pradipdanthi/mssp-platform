# KB-020 — Production Bootstrap and Demo Data Separation

**Status:** Implemented (repository layout + scripts). Non-destructive.  
**Branch:** `kb020-production-bootstrap-demo-separation`

## Problem

The Kestrel Cyber Control Plane lab UI still shows **demo** records (Demo SOC Manager, Demo Customer tenants, DEMO/DEMO2, example.local users, demo alerts/incidents/tokens). Those records are useful for development and KB validation, but they must not be part of a **production** deployment path.

Historically, demo rows were applied by **optional scripts** (KB-007 / KB-010 / KB-011), not by `postgres/init/*.sql`. Schema init was already clean; the risk was process and documentation, not automatic demo inserts on fresh volumes.

## Three distinct layers

| Layer | Location | Purpose |
|---|---|---|
| **Schema / migrations** | `postgres/init/` (mounted as `docker-entrypoint-initdb.d`) | Empty product tables + additive migrations only |
| **Demo seed (dev/lab)** | `postgres/seed/dev/` + `scripts/seed_demo_data.sh` | Optional fake DEMO data — never auto-run in production |
| **Production bootstrap** | `scripts/bootstrap_platform_admin.sh` | First `platform_admin` only; no demo tenants/users |

## Fresh development flow

1. Start Compose so Postgres applies `postgres/init/*.sql` only.
2. Start `backend-api`.
3. Optionally load lab fixtures:
   - Prefer future `postgres/seed/dev/001_demo_seed.sql` via  
     `./scripts/seed_demo_data.sh --yes-dev-demo`  
     (today that SQL is **deferred**; the script exits with a clear message).
   - Or use historical lab scripts (`kb007_*`, demo sections of `kb010_create_auth_rbac.sh`, `kb011_seed_rbac_fixtures.sh`) **only** on disposable lab/dev systems.
4. Run KB validation scripts as needed against the lab database.

**Never** set `APP_ENV=production` when seeding demo data.

## Fresh production flow

1. Start Compose on an empty volume — schema/migrations from `postgres/init/` only.
2. Start `backend-api`.
3. Create the first administrator:

```bash
cd /opt/mssp-control
./scripts/bootstrap_platform_admin.sh
```

Interactive prompts collect email, full name, and password (entered twice, hidden).  
Or automate with:

```bash
export BOOTSTRAP_ADMIN_EMAIL='admin@your-domain.example'
export BOOTSTRAP_ADMIN_FULL_NAME='Platform Administrator'
export BOOTSTRAP_ADMIN_PASSWORD='...'   # never commit this; unset after use
./scripts/bootstrap_platform_admin.sh
```

4. Sign in to the admin portal; create real tenants and users via the APIs/UI.
5. **Do not** run `scripts/seed_demo_data.sh`.  
6. **Do not** mount `postgres/seed/dev/` into `docker-entrypoint-initdb.d`.

### bootstrap_platform_admin.sh behavior

- Inserts one `platform_admin` with `tenant_id NULL`.
- Hashes the password with `app.core.security.hash_password` (bcrypt) inside the `backend-api` container.
- Never prints the plaintext password or the hash.
- Refuses if a `platform_admin` already exists unless `--force` is passed.
- Creates **no** DEMO tenants, demo incidents, or `@example.local` users.

## Why demo data remains in the current lab DB

KB-020 **does not delete** live rows. The current lab may still contain DEMO/DEMO2 and related users from earlier modules so KB-011–KB-019 validation and operator training keep working without a destructive cutover.

Repository separation means: **new** production installs do not inherit demo seed through init mounts or automatic scripts. Cleaning an existing lab/production-like volume is a **future, explicitly approved** module.

## Password and secret rules

- No production passwords in SQL or git.
- No default passwords in bootstrap scripts.
- Interactive `read -rs` or env vars that are never committed.
- Hash with the existing backend bcrypt helper; store hash only.
- Never print `.env` values, passwords, or hashes.

## Demo seed SQL deferred

A consolidated idempotent `postgres/seed/dev/001_demo_seed.sql` was **not** invented in KB-020 because the original KB-007 foundation seed for the DEMO tenant/appliance baseline is not present as one reconstructable in-repo artifact with enough confidence to regenerate safely. See `postgres/seed/dev/README.md`.

## Future module (deferred)

- Production reset / clean deployment that optionally wipes demo rows from an existing volume (explicit approval required).
- Reconstructed idempotent `001_demo_seed.sql` under `postgres/seed/dev/` for greenfield labs.
- Optional `.env.example` documenting `APP_ENV=development` vs `production` (no secrets).

## Validation

```bash
cd /opt/mssp-control
./scripts/kb020_validate_production_bootstrap_demo_separation.sh
```

Expected final line:

```text
KB-020 PRODUCTION BOOTSTRAP AND DEMO SEPARATION VALIDATION PASSED
```

The validator checks repository layout and safety guards. It honestly does **not** claim the current lab database is free of demo rows.
