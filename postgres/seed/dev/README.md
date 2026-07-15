# Development / lab demo seed (KB-020)

**Status:** Development and lab use only.

## Warning

Files under `postgres/seed/dev/` are **not** production bootstrap material.

- They **must not** be mounted into PostgreSQL's `docker-entrypoint-initdb.d`.
- They **must not** run automatically on container start.
- They **must not** be used on production deployments.
- `docker-compose.yml` mounts only `postgres/init/` for schema/migrations — keep it that way.

## What demo records look like

Historically, lab validation created clearly fake records such as:

| Kind | Examples |
|---|---|
| Tenants | `DEMO`, `DEMO2` ("Demo Tenant Two") |
| Users | `*@example.local`, `*@demo.local`, `*@demo2.local` (e.g. Demo SOC Manager) |
| Appliances / assets | `demo-appliance-01`, `demo-sql-server-01` |
| Alerts / incidents | `demo-wazuh-001`, `INC-DEMO-0001` |
| Tokens / fixtures | Demo activation tokens and related KB-011 fixtures |

Those names are intentional fakes for training and automated validation. They are **not** real customers.

## Current lab database

The running lab database may **still contain** demo rows from KB-007 through KB-019. KB-020 does **not** delete them. Separating demo material in the repository is not the same as wiping a live database.

## Production

Production deployments should:

1. Apply only `postgres/init/*.sql` (schema/migrations).
2. Create the first admin with `scripts/bootstrap_platform_admin.sh`.
3. **Never** apply this `postgres/seed/dev/` path.
4. **Never** run `scripts/seed_demo_data.sh`.

## Demo seed SQL status

A consolidated idempotent `001_demo_seed.sql` for the full DEMO foundation is **deferred**. The original KB-007 "foundation seed" for tenant/appliance baselines is not present as a single reconstructable file in-repo with enough confidence to regenerate safely without risking schema drift.

Until a future module recreates that SQL under this directory:

- Use the existing historical lab scripts (`scripts/kb007_*`, `scripts/kb010_create_auth_rbac.sh` demo sections, `scripts/kb011_seed_rbac_fixtures.sh`) **only** on development/lab environments.
- Or re-seed a disposable lab volume by following documented historical KB steps.

When `001_demo_seed.sql` (or similar) is added here later, `scripts/seed_demo_data.sh` is the only intended applicator — always with `--yes-dev-demo`, never when `APP_ENV=production`.
