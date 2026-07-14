# KB-016 Appliance Registration and Heartbeat Receiver Foundation — Completion Summary

## 1. Module name and purpose

**KB-016: Appliance Registration and Heartbeat Receiver Foundation.**

Purpose: build the first **appliance-facing** (not admin-facing, not human-JWT-authenticated) API surface, so a customer-site appliance can redeem the one-time activation token an admin creates through KB-015's admin API, obtain its own durable identity and credential, and then periodically report health/status data back to the control plane. This closes the gap KB-015 deliberately left open: KB-015 let a `platform_admin` create activation tokens and view/update appliance metadata, but nothing in the codebase could actually consume a token, create the corresponding `appliances` row, or accept a heartbeat.

- Branch: `kb016-appliance-registration-heartbeat`
- Previous validated commit: `c0e84c2` ("KB-015 add admin appliance management APIs")
- Previous tag: `kb015-admin-appliance-management-validated`
- Previous module: KB-015 Admin Appliance Management API Foundation

## 2. Scope included

- `POST /appliance/register` — redeem a one-time activation token, create the appliance row, issue a durable appliance API key (returned once).
- `POST /appliance/heartbeat` — accept a periodic health/status update from an already-registered appliance, authenticated by that durable API key.
- A new, appliance-specific authentication model — no JWT, no `platform_users` row, no `Depends(get_current_user)`/`Depends(require_roles(...))` anywhere in this module.
- A schema migration adding a durable appliance credential (hash + hint + timestamps) directly to `appliances`.
- A new `db_transaction()` helper so registration (token check → appliance create → token consume) and heartbeat (heartbeat insert → appliance update) can each be a single atomic unit.
- A small, targeted extension of the KB-014 global validation-error redaction list.
- A new validation script that exercises the full registration/heartbeat flow and reruns KB-015's validation script unmodified as a regression gate.

## 3. Scope excluded/deferred

Explicitly **not** built in KB-016 (see also the KB-017 recommendation in section 19):

- **Admin-facing visibility into appliance credential state.** `GET /admin/appliances/{appliance_id}` (KB-015, unmodified) still shows no `has_appliance_api_key`, `appliance_api_key_hint`, or `appliance_key_last_used_at` field — an admin currently has no safe, API-based way to see whether an appliance has ever been issued a credential, or when it was last used.
- **Appliance credential rotation/reissue.** There is no way to reissue a new durable API key for an already-registered appliance without a fresh activation token; if a key is compromised or lost, the only recovery path today is a brand-new admin-issued activation token and a brand-new appliance row.
- **Alert/event ingestion from appliances** (Wazuh/Suricata data flowing through an appliance) — heartbeat carries only health/status fields, never security alert data.
- **Frontend, customer dashboard UI, admin UI** — none were touched or scaffolded.
- **Mutual TLS or any transport-layer authentication** — authentication here is entirely application-layer (token/API-key), consistent with every other endpoint in this codebase; TLS-level appliance authentication is a possible future hardening step, not attempted here.
- **Protected-asset/device-inventory sync from the appliance** — heartbeat does not touch `protected_assets` at all.
- **Automatic activation-token expiry** — expiry continues to be checked lazily at redemption time (`expires_at` compared to `now()`), exactly as KB-015 documented; no scheduled worker flips `pending` → `expired`.

## 4. Database migration details

**New file:** `postgres/init/003_kb016_appliance_registration_heartbeat.sql` — idempotent, follows the exact pattern KB-010's `002_kb010_auth_rbac.sql` established (this file only runs automatically for a brand-new, empty Postgres data volume; it does **not** retroactively apply to the already-running database).

Four new, nullable columns on `appliances`:

| Column | Type | Purpose |
|---|---|---|
| `appliance_api_key_hash` | `TEXT` | SHA-256 hex digest of the durable appliance API key. `UNIQUE`. |
| `appliance_api_key_hint` | `TEXT` | Last 6 characters of the raw key — display-only, not reversible. |
| `appliance_key_created_at` | `TIMESTAMPTZ` | Set once, at registration. |
| `appliance_key_last_used_at` | `TIMESTAMPTZ` | Updated on every successful heartbeat authentication. |

New constraint: `appliances_appliance_api_key_hash_key` — `UNIQUE (appliance_api_key_hash)`, added only if not already present (`pg_constraint` existence check).

**Live-database migration:** `scripts/kb016_create_appliance_registration_heartbeat.sh` — runs the same `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / guarded `ADD CONSTRAINT` statements directly against the running `mssp-postgres` container via `docker compose exec -T postgres psql -v ON_ERROR_STOP=1`, then verifies the 4 columns and the constraint exist via `information_schema.columns`/`pg_constraint`. Safe to run more than once. This was run against the live database before validation, and validation's own section 2 independently re-verifies the same 4 columns and constraint before doing anything else.

No existing schema file (`001_mssp_core_schema.sql`, `002_kb010_auth_rbac.sql`) was modified. All 4 new columns are nullable, so no existing `appliances` row (including any created directly via SQL, e.g. KB-015's own validation fixtures) was broken by this change.

## 5. Files created/modified

**Created:**

- `postgres/init/003_kb016_appliance_registration_heartbeat.sql`
- `scripts/kb016_create_appliance_registration_heartbeat.sh`
- `backend-api/app/schemas/appliance_agent.py` — `ApplianceRegisterRequest`/`ApplianceRegisterResponse`, `ApplianceHeartbeatRequest`/`ApplianceHeartbeatResponse`.
- `backend-api/app/services/appliance_auth_service.py` — `generate_appliance_api_key()`, `hash_secret_sha256()`, `verify_appliance_credentials()`, `InvalidApplianceCredentialsError`, `ApplianceRetiredError`.
- `backend-api/app/api/routes/appliance_agent.py` — the two new endpoints.
- `scripts/kb016_validate_appliance_registration_heartbeat.sh`
- `docs/KB016_APPLIANCE_REGISTRATION_HEARTBEAT_COMPLETION.md` — this file.

**Modified:**

- `backend-api/app/main.py` — one new import (`appliance_agent_router`) and one new `app.include_router(appliance_agent_router)` line. No other line touched.
- `backend-api/app/db/session.py` — added `db_transaction()` only. `fetch_all()`, `fetch_one()`, `execute()`, `fetch_one_write()`, `redis_client()` are all unchanged.
- `backend-api/app/core/error_handlers.py` — added `"activation_token"`, `"appliance_api_key"`, `"api_key"` to `SENSITIVE_KEYS`. The redaction logic itself (`_contains_sensitive_key`, `_redact_if_sensitive`, `_loc_is_sensitive`, `_sanitize_errors`, `validation_exception_handler`) was not rewritten.
- `docs/AI_PROMPT_LEDGER.md` — new KB-016 row (see the ledger update in this same documentation pass).

**Not touched:** `docker-compose.yml`, `.env`, `backend-api/requirements.txt` (no new dependency was needed — `secrets`/`hashlib`/`hmac`/`uuid` are standard library, and `IPvAnyAddress`/`psycopg.types.json.Jsonb` are already provided by the pinned `pydantic`/`psycopg[binary]` versions), `backend-api/app/api/routes/admin.py`/`tenant_management.py`/`user_management.py`/`appliance_management.py`/`auth.py`/`customer.py`/`health.py`, `backend-api/app/api/dependencies.py`, `backend-api/app/core/security.py`/`config.py`, `backend-api/app/services/auth_service.py`, `backend-api/app/schemas/auth.py`/`tenants.py`/`users.py`/`appliances.py`, `postgres/init/001_mssp_core_schema.sql`/`002_kb010_auth_rbac.sql`, and every existing validation script (`kb008` through `kb015`).

## 6. New endpoints

| Endpoint | Auth | Success | Errors |
|---|---|---|---|
| `POST /appliance/register` | Possession of a valid, `pending`, unexpired activation token (request body) | `201` | `401`/`409`/`422`/`500` |
| `POST /appliance/heartbeat` | Possession of a durable appliance API key (`X-Appliance-ID`/`X-Appliance-API-Key` headers) | `200` | `401`/`403`/`422`/`500` |

Neither endpoint uses `Depends(get_current_user)` or `Depends(require_roles(...))`, and neither appears under `/admin/*` or `/customer/*` — they are appliance-facing only, and no existing `/admin/*`/`/customer/*` endpoint's behavior changed.

## 7. Registration flow

1. Appliance sends `POST /appliance/register` with `activation_token` (required) and `appliance_name` (required); optionally `appliance_uuid`, `agent_version`, `config_version`, `local_ip`, `health_snapshot`. The request model rejects (`422`) any attempt to also send `tenant_id`, `site_name`, `appliance_api_key`, `token_hash`, or `appliance_api_key_hash` — `ApplianceRegisterRequest` uses Pydantic `extra="forbid"`, so these are not silently ignored, they are structurally impossible to submit.
2. The raw `activation_token` is hashed with SHA-256 and looked up against `appliance_activation_tokens.token_hash`, inside one `db_transaction()`, using `SELECT ... FOR UPDATE` — this row lock serializes any concurrent redemption attempt against the same token.
3. The token must exist, have `status = 'pending'`, and (if `expires_at` is set) not be in the past. Any failure here — not found, wrong status, or expired — raises the same internal error and is reported identically as a generic `401`.
4. `tenant_id` and `site_name` for the new appliance come **only** from the token row, never from the request body — the client cannot choose or override them.
5. `appliance_uuid` is the client-supplied value if present, otherwise the server generates one with `uuid4()` — the column is always populated after a successful registration.
6. The appliance row is **inserted before** the token is marked used. A `UniqueViolation` on `appliance_uuid` or on the existing `UNIQUE (tenant_id, appliance_name)` constraint is caught and reported as a clean `409` — and because the token hasn't been consumed yet at that point, the caller can retry with the same still-`pending` token.
7. Only after the `INSERT` succeeds does the same transaction run `UPDATE appliance_activation_tokens SET status = 'used', used_at = now() WHERE id = %s AND status = 'pending' RETURNING id` — a belt-and-suspenders compare-and-swap on top of the earlier row lock. If this affects zero rows, the whole transaction (including the just-inserted appliance row) is rolled back and the caller gets a clean `409`.
8. On success (`201`), the response returns `appliance_id`, `appliance_uuid`, `tenant_id`, `tenant_short_code`, `appliance_name`, `site_name`, `status` (`"registered"`), the one-time `appliance_api_key`, `api_key_hint`, and a `message`. `token_hash` and `appliance_api_key_hash` are structurally absent from the response model.

## 8. Heartbeat flow

1. Appliance sends `POST /appliance/heartbeat` with `X-Appliance-ID` and `X-Appliance-API-Key` headers (both `Header(default=None, ...)` so a missing header is checked manually and reported as `401`, not FastAPI's default `422`).
2. `X-Appliance-ID` is validated as a well-formed UUID; a malformed value is reported as the same generic `401` used for any other credential failure (never `422` — this is a credential, not a request-body field).
3. `appliance_auth_service.verify_appliance_credentials()` looks up the appliance by id, hashes the presented `X-Appliance-API-Key` with SHA-256, and compares it to the stored `appliance_api_key_hash` using `hmac.compare_digest` (constant-time). Appliance not found, no credential hash on file, or a hash mismatch all raise the same generic `401`.
4. If the credentials are valid but the appliance's `status` is `retired`, `verify_appliance_credentials()` raises a separate error the route turns into `403` — a known, correctly-authenticated identity that is nonetheless not permitted to send heartbeats.
5. One `db_transaction()` then performs two writes: an `INSERT` into `appliance_heartbeats` (`source_ip` taken from `request.client.host`, never from the request body) and an `UPDATE` of `appliances` — `last_seen_at`, `last_source_ip`, `appliance_key_last_used_at` are always refreshed; `local_ip`, `agent_version`, `config_version`, `git_commit`, `update_status`, `health_snapshot` are updated only when the caller actually provided them (`COALESCE`, keeping the old value otherwise); `status` becomes `'online'` unless it is currently `'maintenance'`, which is preserved.
6. On success (`200`), the response returns `appliance_id`, `status`, `heartbeat_at`, and a `message`. No field in the response model can carry a raw key, a hash, or a raw activation token.

## 9. Appliance authentication model

This module introduces a caller type that does not exist anywhere else in the codebase: a piece of customer-site hardware/software, not a `platform_users` row. Deliberately:

- No JWT is issued to, checked from, or expected from an appliance.
- `POST /appliance/register` authenticates by **possession of a one-time secret** (the activation token) presented in the request body — there is no appliance identity yet at that point, so there is nothing to put in a header.
- `POST /appliance/heartbeat` authenticates by **possession of a durable secret** (the appliance API key) presented via `X-Appliance-ID`/`X-Appliance-API-Key` headers — chosen over a body field because it is a long-lived credential attached to every call, closer in spirit to how an API key is conventionally transmitted.
- Every authentication failure path in this module returns a **generic** `401` or `403` — never a `404` (which would let a caller distinguish "wrong id" from "wrong key") and never a message that reveals *why* a token or key failed. This is a deliberate anti-enumeration choice, consistent with how `require_tenant_match()` already returns `404` (not `403`) for a tenant mismatch elsewhere in this codebase — different mechanism, same underlying principle of not giving an unauthenticated caller information to probe with.

## 10. Token/API-key hashing model

- **Generation:** `secrets.token_urlsafe(32)` for the durable appliance API key — 256 bits of cryptographically secure randomness, the same approach KB-015 already used for activation tokens.
- **Storage:** only `hashlib.sha256(raw_value).hexdigest()` is ever written to the database (`appliance_api_key_hash`). The raw key is never stored, in this table or anywhere else.
- **Hint:** `appliance_api_key_hint` stores only the last 6 characters of the raw key — for display/troubleshooting only, not reversible to the full key.
- **Comparison:** heartbeat verification hashes the presented key and compares it to the stored hash with `hmac.compare_digest()` — a constant-time comparison, reducing the risk of a timing side-channel, rather than Python's built-in `==`.
- **Why not bcrypt:** bcrypt is designed to slow down brute-forcing a low-entropy, human-chosen secret (a password). A `secrets.token_urlsafe(32)` value is already a uniformly random 256-bit value — a fast, deterministic hash is the correct, standard tool for verifying it, and is what this codebase already uses for activation tokens (KB-015) and this module's appliance API keys alike.
- **One-time exposure:** the raw appliance API key is returned **exactly once**, in the `appliance_api_key` field of the `POST /appliance/register` `201` response. No other endpoint — including `POST /appliance/heartbeat` and every existing `/admin/*` endpoint — ever returns it, and `appliance_api_key_hash` is absent from every response model in the codebase.

## 11. Transaction/race-condition protection

- `backend-api/app/db/session.py` gained one new helper, `db_transaction()` — a context manager yielding a cursor for multiple statements against a single connection/transaction, committing once on clean exit and rolling back the entire transaction if any exception propagates (including an application-level exception the route raises itself to signal "abort this attempt"). `fetch_all()`, `fetch_one()`, `execute()`, and `fetch_one_write()` are unchanged.
- **Registration** uses one `db_transaction()` for: locking the token row (`SELECT ... FOR UPDATE`), validating it, inserting the appliance row, and consuming the token (`UPDATE ... WHERE status = 'pending'`). The `FOR UPDATE` lock serializes concurrent redemption attempts against the *same* token — a second concurrent request blocks until the first transaction commits or rolls back, then sees the now-`used` status and is rejected at the very first check, before ever attempting an `INSERT`. The appliance `INSERT` happens **before** the token is marked used specifically so that a duplicate-`appliance_name`/duplicate-`appliance_uuid` conflict never wastes the caller's token.
- **Heartbeat** uses one `db_transaction()` for the `appliance_heartbeats` insert and the `appliances` update together, so a heartbeat is recorded as a single atomic unit rather than two independent writes that could partially succeed.

## 12. Error behavior

| Scenario | Response |
|---|---|
| Missing `activation_token` field entirely | `422` (Pydantic-native — required field) |
| Invalid / nonexistent / expired / revoked / already-used activation token | `401`, identical generic message in every case |
| Duplicate `appliance_uuid` | `409` |
| Duplicate `appliance_name` within the same tenant | `409` |
| Belt-and-suspenders token-consume race lost | `409` (whole transaction rolled back) |
| Missing `X-Appliance-ID`/`X-Appliance-API-Key` header(s) | `401` (checked manually, not FastAPI's default `422`) |
| Malformed `X-Appliance-ID` (not a UUID) | `401` |
| Unknown appliance id, no credential on file, or wrong API key | `401`, identical generic message in every case |
| Heartbeat from a `retired` appliance (valid credentials) | `403` |
| Malformed heartbeat payload (bad enum value, out-of-range percent, etc.) | `422` (Pydantic-native) |
| Any unexpected internal failure | `500`, generic message, full detail logged server-side only |

No raw database error or stack trace is ever returned to a caller in either endpoint.

## 13. Sensitive-data redaction

- `backend-api/app/core/error_handlers.py`'s `SENSITIVE_KEYS` set gained exactly three entries: `"activation_token"`, `"appliance_api_key"`, `"api_key"`. None of KB-016's new field names matched any pre-existing entry by exact string (`"activation_token" != "token"`), so before this change a `422` on, say, a too-short `activation_token` would have echoed the caller's submitted value back in the error's `input` field, unredacted. The redaction logic itself was not touched — only the set of key names it checks against.
- The raw activation token and raw appliance API key are never logged anywhere in `backend-api/app/api/routes/appliance_agent.py` or `backend-api/app/services/appliance_auth_service.py` — only their SHA-256 hashes and hints ever reach storage, and the only place either raw secret reaches a log call is nowhere at all.
- `appliance_api_key_hash` and `token_hash` are absent from every response model in `backend-api/app/schemas/appliance_agent.py` — structurally impossible to leak, not just "not currently selected."
- Validation directly exercised this: a `422` triggered by a too-short `activation_token` was confirmed to have its `input` redacted rather than echoing the caller's raw value.

## 14. Validation steps performed

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
./scripts/kb016_create_appliance_registration_heartbeat.sh
docker compose build backend-api
docker compose up -d backend-api
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb016_validate_appliance_registration_heartbeat.sh
```

`scripts/kb016_validate_appliance_registration_heartbeat.sh` internally reruns `./scripts/kb015_validate_admin_appliance_management.sh` unmodified as its behavior-regression gate (which itself reruns KB-014 → KB-013 → KB-012 → KB-011 unmodified).

Confirmed by the passing run:

- Public endpoints remain public: `/health`, `/auth/roles`, `/docs`.
- `POST /appliance/register` and `POST /appliance/heartbeat` exist and are reachable.
- Missing `activation_token` returns a clean `422`; a garbage `activation_token` returns a generic `401`.
- `platform_admin` created a fake activation token for the `DEMO` tenant using the existing, unmodified KB-015 admin API.
- Registration with that raw fake token succeeded with `201`; `tenant_id` and `site_name` in the response came from the token, not the request body; `appliance_uuid` was server-generated (the request omitted it).
- `appliance_api_key` appeared exactly once, in the registration response; the response never contained `token_hash` or `appliance_api_key_hash`.
- The same activation token could not be redeemed a second time (`401`); its `status` became `used` with `used_at` set, confirmed via the existing, unmodified KB-015 admin token-list endpoint.
- Heartbeat with no headers returned `401`; heartbeat with a correct `X-Appliance-ID` but wrong `X-Appliance-API-Key` returned `401`; heartbeat with valid credentials returned `200`.
- The heartbeat created a new `appliance_heartbeats` row and updated `appliances.last_seen_at` and `appliances.appliance_key_last_used_at` — confirmed with direct SQL.
- After the heartbeat, `appliances.status` became `online`; the existing, unmodified `GET /admin/appliances/{appliance_id}` (KB-015) showed the expected `appliance_name`, `status`, and `latest_heartbeat_at`.
- The existing, unmodified `GET /admin/appliances` list endpoint still returned `200`.
- After setting the fake appliance's `status` to `retired` (via the existing, unmodified KB-015 admin `PATCH` endpoint), a heartbeat with otherwise-valid credentials returned `403`.
- No response at any point exposed `token_hash`, `appliance_api_key_hash`, the raw activation token outside its one creation response, the raw appliance API key outside its one registration response, `password_hash`, or a password value.
- All fake KB-016 validation appliance/heartbeat/activation-token fixtures were cleaned up — 0 rows remaining afterward.
- `./scripts/kb015_validate_admin_appliance_management.sh` passed unmodified inside the KB-016 run — no observable regression to admin appliance management, and (through its own regression chain) no observable regression to user management, tenant management, route structure, auth, RBAC, tenant isolation, or validation-error redaction (KB-014 → KB-013 → KB-012 → KB-011).

## 15. Final validation result

```
KB-016 APPLIANCE REGISTRATION AND HEARTBEAT VALIDATION PASSED
```

Reported by the user after running `./scripts/kb016_create_appliance_registration_heartbeat.sh`, rebuilding/restarting `backend-api`, and running `./scripts/kb016_validate_appliance_registration_heartbeat.sh` to completion.

## 16. Post-validation safety result

- Docker services (`mssp-postgres`, `mssp-redis`, `mssp-backend-api`) all running/healthy.
- `GET /health` returned OK.
- `/openapi.json` includes both new KB-016 paths: `/appliance/register`, `/appliance/heartbeat`.
- `information_schema.columns` confirmed all 4 new columns exist on `appliances`: `appliance_api_key_hash`, `appliance_api_key_hint`, `appliance_key_created_at`, `appliance_key_last_used_at`.
- `pg_constraint` confirmed the `appliances_appliance_api_key_hash_key` unique constraint exists.
- A follow-up query for fake KB-016 validation appliances returned **0 rows**.
- A follow-up query for fake KB-016 validation activation tokens returned **0 rows**.
- Python syntax check (`py_compile`) passed for all new/changed Python files.
- Bash syntax check (`bash -n`) passed for both new shell scripts.

## 17. Operational notes for future modules

- **Admins currently have no safe visibility into appliance credential state.** `GET /admin/appliances/{appliance_id}` (KB-015, unmodified by design — Decision H was deferred) shows nothing about whether an appliance has ever been issued a durable API key, its hint, or when it was last used. Operationally, once a real appliance is in the field, an admin/SOC user has no way to answer "does this appliance have a working credential?" without querying the database directly.
- **There is no credential rotation or reissue path.** If a durable appliance API key is lost, compromised, or an appliance needs to be re-provisioned, the only way forward today is issuing a brand-new activation token (KB-015) and running `POST /appliance/register` again — which will fail with a clean `409` if the same `appliance_name`/`appliance_uuid` is reused, since those columns are still `UNIQUE`. There is currently no "reissue a key for an existing appliance" operation.
- **`appliance_key_last_used_at` is a good, cheap signal for future health/staleness logic** (e.g. "no heartbeat and no key usage in N days") but nothing currently reads or alerts on it — it is only written, never consumed elsewhere yet.
- **The regression-gate chain is now five scripts deep** (KB-016 → KB-015 → KB-014 → KB-013 → KB-012 → KB-011). Each new module's validation script continues to rerun the previous module's script unmodified — this pattern is working well as a lightweight regression suite and should continue for KB-017 and beyond.
- **`db_transaction()` is now a shared primitive** (`backend-api/app/db/session.py`) — any future module needing more than one write to succeed or fail together as a unit should reuse it rather than inventing a second transaction pattern.
- **Expiry remains lazy**, exactly as KB-015 documented — `POST /appliance/register` checks `expires_at` itself at redemption time; no scheduled worker flips `pending` → `expired`.

## 18. Rollback notes

- **Application rollback:** delete the 5 new backend files (`appliance_agent.py` router, `appliance_agent.py` schemas, `appliance_auth_service.py`, and the 2 new scripts), revert the two lines added to `main.py`, revert the `db_transaction()` addition to `session.py`, and revert the 3-string `SENSITIVE_KEYS` addition to `error_handlers.py`. Rebuild `backend-api`. This restores the exact KB-015 validated behavior (tag `kb015-admin-appliance-management-validated`, commit `c0e84c2`).
- **Migration rollback:** the 4 new `appliances` columns are additive and nullable — leaving them in place unused is always safe. If an explicit rollback is ever needed: `ALTER TABLE appliances DROP COLUMN IF EXISTS appliance_api_key_hash, DROP COLUMN IF EXISTS appliance_api_key_hint, DROP COLUMN IF EXISTS appliance_key_created_at, DROP COLUMN IF EXISTS appliance_key_last_used_at;` — safe, since no other table has a foreign key into any of these columns.
- **Test data cleanup:** `scripts/kb016_validate_appliance_registration_heartbeat.sh` removes its own fake appliance (`kb016-validation-appliance`), its heartbeats (via `ON DELETE CASCADE`), and its fake activation token (`KB016 Validation Site (fake, safe to delete)`) both at the end of a successful run and in its failure trap — confirmed to leave 0 rows behind in the passing run.

## 19. Next recommended module

**Recommended: KB-017: Appliance Credential Rotation and Admin Credential Visibility Foundation.**

Purpose:
- Add safe admin visibility into appliance credential *metadata* only — e.g. whether a credential exists, its hint, when it was created, when it was last used — never the raw key or its hash.
- Add a credential rotation/reissue capability for an already-registered appliance, if needed, so a lost/compromised key does not require creating a whole new appliance row.
- Keep the appliance heartbeat authentication model (this module) stable — rotation should not change how `POST /appliance/heartbeat` verifies a key, only how a new key gets issued.

This is recommended over the alternative — **KB-017: Appliance Alert Ingestion Foundation** — because KB-016 just introduced durable, long-lived appliance credentials, and there is currently no safe operational path for an admin to see that a credential exists or to recover from a lost one. Closing that gap before building alert ingestion (which will lean on appliances actually being reliably registered and monitorable) keeps the credential lifecycle from becoming a bigger, harder-to-unwind gap later. This is a recommendation only — the next module should be explicitly defined and approved by the user before any planning or implementation begins.
