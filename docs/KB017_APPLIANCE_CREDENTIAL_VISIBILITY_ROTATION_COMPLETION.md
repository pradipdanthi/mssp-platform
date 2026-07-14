# KB-017 Appliance Credential Rotation and Admin Credential Visibility Foundation — Completion Summary

## 1. Module name and purpose

**KB-017: Appliance Credential Rotation and Admin Credential Visibility Foundation.**

Purpose: KB-016 introduced durable, long-lived appliance API credentials (a SHA-256 hash stored on `appliances.appliance_api_key_hash`, used to authenticate `POST /appliance/heartbeat`), but left admins with no safe, API-based way to see whether an appliance had ever been issued a credential, when it was created, or when it was last used — and no way to reissue a credential if it was lost or suspected compromised without creating an entirely new appliance row. KB-017 closes that gap with two small, focused admin-side endpoints: one read-only credential-metadata view, and one `platform_admin`-only rotation/reissue action.

- Branch: `kb017-appliance-credential-visibility-rotation`
- Previous validated commit: `f699b74` ("KB-016 add appliance registration and heartbeat APIs")
- Previous tag: `kb016-appliance-registration-heartbeat-validated`
- Previous module: KB-016 Appliance Registration and Heartbeat Receiver Foundation

## 2. Scope included

- `GET /admin/appliances/{appliance_id}/credential` — safe, read-only credential metadata (existence, hint, created/last-used timestamps, current appliance status, last-seen time). Never the raw key, never the hash.
- `POST /admin/appliances/{appliance_id}/credential/rotate` — `platform_admin`-only rotation/reissue of an appliance's durable API key. Generates a brand-new key, invalidates the old one immediately, and returns the new raw key exactly once.
- RBAC reusing the existing human JWT/`require_roles` foundation — no new authentication mechanism, no changes to how appliances themselves authenticate.
- A new validation script exercising both endpoints end-to-end, including proving the old key stops working and the new key works, and rerunning KB-016's validation script unmodified as a regression gate.

## 3. Scope excluded/deferred

Explicitly **not** built in KB-017:

- **Frontend, admin UI, customer dashboard UI** — none were touched or scaffolded (see the KB-018 recommendation in section 19).
- **Wazuh deployment or alert ingestion** — out of scope entirely for this module.
- **Multi-key credential history** — rotation overwrites the single existing credential columns on `appliances`; there is no separate table recording every past key/hash/rotation event. Not strongly justified for this foundation module.
- **Automatic/scheduled credential rotation** — rotation is always an explicit, one-off `platform_admin` action; there is no worker or policy that rotates a credential on a timer or on suspicious activity.
- **Email/WhatsApp notification of a rotation event** — rotating a credential does not notify anyone; the `platform_admin` who called the endpoint is the only one who sees the new raw key, in the response body, once.
- **Appliance mutual TLS** — authentication remains entirely application-layer (API key), unchanged from KB-016.
- **Any change to appliance registration or heartbeat behavior** — `POST /appliance/register` and `POST /appliance/heartbeat` (KB-016) are completely unmodified; rotation only ever changes what is stored in the credential columns those two endpoints already read from.

## 4. Starting state and prerequisite modules

KB-017 builds directly on:

- **KB-015** (Admin Appliance Management API Foundation) — supplied the router (`appliance_management.py`), the `ADMIN_SOC_ROLES` read-role tuple (imported from `admin.py`), the `ADMIN_APPLIANCE_WRITE_ROLES` write-role precedent, and the `fetch_one_write()` "single `UPDATE ... RETURNING`, zero rows → `404`" pattern this module reuses exactly.
- **KB-016** (Appliance Registration and Heartbeat Receiver Foundation) — supplied the four credential columns on `appliances` (`appliance_api_key_hash`, `appliance_api_key_hint`, `appliance_key_created_at`, `appliance_key_last_used_at`), the `generate_appliance_api_key()`/`hash_secret_sha256()` helpers in `appliance_auth_service.py`, and the heartbeat verification logic (`verify_appliance_credentials()`) that rotation relies on to "just work" against a changed hash with zero code changes of its own.

No other prerequisite module changes were needed. Both required columns and both required helper functions already existed before this module started.

## 5. Files created/modified

**Created:**

- `scripts/kb017_validate_appliance_credential_visibility_rotation.sh`
- `docs/KB017_APPLIANCE_CREDENTIAL_VISIBILITY_ROTATION_COMPLETION.md` — this file.

**Modified:**

- `backend-api/app/api/routes/appliance_management.py` — added `ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES = ("platform_admin",)` (a distinct constant from the existing `ADMIN_APPLIANCE_WRITE_ROLES`, per Decision E), the `_APPLIANCE_CREDENTIAL_QUERY` constant, and the two new route functions `get_appliance_credential()`/`rotate_appliance_credential()`. Every existing function, constant, and import in this file is unchanged; the existing `GET`/`PATCH /admin/appliances/{appliance_id}` and activation-token endpoints (KB-015) were not touched.
- `backend-api/app/schemas/appliances.py` — added `ApplianceCredentialMetadata` and `ApplianceCredentialRotateResponse`. Every existing model (`ApplianceDetail`, `ApplianceUpdateRequest`, `ActivationTokenMetadata`, etc.) is unchanged.
- `docs/AI_PROMPT_LEDGER.md` — new KB-017 row (this same documentation pass).

**Not touched:** `backend-api/app/main.py` (no new router — both endpoints were added to the already-registered `appliance_management_router`), `backend-api/app/api/routes/appliance_agent.py`, `backend-api/app/services/appliance_auth_service.py` (its existing `generate_appliance_api_key()`/`hash_secret_sha256()` were reused unchanged), `backend-api/app/db/session.py` (rotation is a single `UPDATE ... RETURNING`, so the existing `fetch_one_write()` was sufficient — no need for the KB-016 `db_transaction()` helper), `backend-api/app/core/error_handlers.py` (neither new endpoint has a request body with a new field name to redact — `GET` takes only the existing `appliance_id` path parameter, `POST rotate` takes no body at all), `docker-compose.yml`, `.env`, `backend-api/requirements.txt`, every `postgres/init/*.sql` file, and every existing validation script (`kb008` through `kb016`).

**Validation-script bug fix (this file only):** the first validation run failed in the file-check section with `appliance_agent.py appears to have been modified for KB-017 - it should not have been touched`, even though `git diff` proved no working-tree or staged changes to that file. The check was a **false positive**: it used a content grep for the literal word `"credential"`, and `appliance_agent.py` legitimately already contains that word from KB-016 (e.g. in `X-Appliance-API-Key` header handling and comments) without KB-017 having touched the file at all. **Fixed** by replacing the content-grep checks for both `backend-api/app/main.py` and `backend-api/app/api/routes/appliance_agent.py` with `git diff --quiet --` and `git diff --cached --quiet --` checks against each file — the actual, correct way to prove a file has neither a working-tree nor a staged change. No application code was touched to fix this; it was purely a validation-script defect.

## 6. New endpoints

| Endpoint | Auth | Success | Errors |
|---|---|---|---|
| `GET /admin/appliances/{appliance_id}/credential` | Human JWT, `platform_admin`/`soc_manager`/`soc_analyst` | `200` | `401`/`403`/`404`/`422` |
| `POST /admin/appliances/{appliance_id}/credential/rotate` | Human JWT, `platform_admin` only | `200` | `401`/`403`/`404`/`422`/`500` |

Both endpoints live under `/admin/*` and use the existing `Depends(require_roles(...))` human-JWT foundation — neither is reachable by an appliance's own `X-Appliance-ID`/`X-Appliance-API-Key` headers, and neither changes how `POST /appliance/register` or `POST /appliance/heartbeat` authenticate.

## 7. RBAC/access-control behavior

| Role | `GET .../credential` | `POST .../credential/rotate` |
|---|---|---|
| `platform_admin` | `200` | `200` |
| `soc_manager` | `200` | `403` |
| `soc_analyst` | `200` | `403` |
| `customer_admin` / `customer_viewer` | `403` | `403` |
| No token / invalid token | `401` | `401` |

Read access reuses the existing `ADMIN_SOC_ROLES` tuple (imported from `admin.py`, unchanged) — the same read tier as appliance detail and activation-token list. Rotation uses a new, distinct `ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES = ("platform_admin",)` constant rather than reusing the existing `ADMIN_APPLIANCE_WRITE_ROLES` — the value is identical today, but keeping it separately named leaves room for credential-issuance permissions to diverge from general appliance-metadata-write permissions later without a rename (Decision E).

## 8. Credential metadata behavior

`GET /admin/appliances/{appliance_id}/credential` returns:

```json
{
  "appliance_id": "...",
  "has_appliance_api_key": true,
  "appliance_api_key_hint": "Ab12Cd",
  "appliance_key_created_at": "2026-07-14T10:32:00+00:00",
  "appliance_key_last_used_at": "2026-07-14T10:35:12+00:00",
  "status": "online",
  "last_seen_at": "2026-07-14T10:35:12+00:00"
}
```

The backing query (`_APPLIANCE_CREDENTIAL_QUERY`) never selects `appliance_api_key_hash` itself — only a boolean derived from it (`appliance_api_key_hash IS NOT NULL AS has_appliance_api_key`). The response model, `ApplianceCredentialMetadata`, has no `appliance_api_key` or `appliance_api_key_hash` field at all — the same "structurally impossible to leak" principle KB-015's `ActivationTokenMetadata` already uses for `token_hash`. An appliance that has never been issued a credential (e.g. a row created directly via SQL) returns `has_appliance_api_key: false` with the hint/timestamp fields `null`, not an error.

## 9. Credential rotation/reissue behavior

`POST /admin/appliances/{appliance_id}/credential/rotate` (no request body):

1. Generates a brand-new key via the existing, unchanged `generate_appliance_api_key()` (KB-016) — `secrets.token_urlsafe(32)`, 256 bits of randomness, returning `(raw_key, key_hash, key_hint)`.
2. Runs a single `UPDATE appliances SET appliance_api_key_hash = %s, appliance_api_key_hint = %s, appliance_key_created_at = now(), appliance_key_last_used_at = NULL WHERE id = %s RETURNING id::text, appliance_key_created_at::text;` via the existing `fetch_one_write()`.
3. Zero rows returned → `404` (`appliance_id` does not exist). A `UniqueViolation` on the (astronomically unlikely) SHA-256 collision against the KB-016 `appliances_appliance_api_key_hash_key` constraint is caught defensively and reported as a clean `500` "please retry" — the same defensive backstop KB-015 already uses for activation-token-hash collisions.
4. Returns `200` (not `201` — this mutates an existing appliance's credential fields, it does not create a new resource, matching KB-015's `PATCH .../revoke` precedent) with `appliance_id`, the new raw `appliance_api_key`, `api_key_hint`, the refreshed `appliance_key_created_at`, and a `message`. `appliance_api_key_hash` is absent from the response model — structurally impossible to return.
5. **`appliance_key_last_used_at` is reset to `NULL`** (Decision B) — after rotation this field means "last successful use of the *current* credential," not the now-dead previous one; leaving a stale non-null value would misleadingly suggest the new key had already been used.
6. **Appliance `status` is never changed by rotation** (Decision D) — credential lifecycle and operational status are kept as separate concerns; an admin who also wants to change status uses the existing, unmodified KB-015 `PATCH /admin/appliances/{appliance_id}`.
7. **Rotation is allowed for a `retired` appliance** (Decision D) and **even if `appliance_api_key_hash` was already `NULL`** (no credential ever issued) — both are treated as normal, successful `200` operations, supporting recovery/recommissioning and retroactively bringing older appliance rows under credential management.

## 10. Old-key/new-key heartbeat proof

Proven entirely through the existing, unmodified `POST /appliance/heartbeat` (KB-016) — rotation needed zero changes to heartbeat verification code, because the only thing rotation changes is the value stored in `appliance_api_key_hash`, which heartbeat already reads and compares via `hmac.compare_digest`:

1. Registered a fake appliance via `POST /appliance/register` using a real KB-015-issued activation token; captured the original raw key.
2. Heartbeat with the **original** key → `200` (baseline, before rotation).
3. `platform_admin` called `POST .../credential/rotate` → `200`; captured the new raw key; confirmed `appliance_key_created_at` changed from the registration-time value.
4. Heartbeat with the **original** (now-stale) key → `401` — proves the old key was invalidated immediately. Direct SQL confirmed `appliance_key_last_used_at` remained `NULL` after this rejected attempt (a failed authentication must never update appliance state).
5. Heartbeat with the **new** (rotated) key → `200` — proves the new key is active. Direct SQL and a follow-up `GET .../credential` both confirmed `appliance_key_last_used_at` was now non-null.

## 11. Retired appliance behavior

- Set the fake appliance's `status` to `retired` via the existing, unmodified KB-015 `PATCH /admin/appliances/{appliance_id}`.
- `POST .../credential/rotate` as `platform_admin` still returned `200` — rotation is allowed regardless of appliance status.
- A follow-up `GET .../credential` confirmed `status` was still `"retired"` — rotation did not change it.
- A heartbeat from that retired appliance, using the **freshly rotated** key, still returned `403` — proving the retired-appliance block in `verify_appliance_credentials()` (KB-016, unmodified) takes priority over valid credentials even immediately after a successful rotation.

## 12. Security and secret-handling notes

- `appliance_api_key_hash` is never selected into any response in this module — the credential-metadata query selects only `appliance_api_key_hash IS NOT NULL`, a boolean, never the column itself.
- The new raw appliance API key is returned **exactly once**, in the rotate response, and is never stored, logged, or returned by `GET .../credential`, by `GET /admin/appliances/{appliance_id}` (KB-015, untouched), or by any other endpoint.
- Neither new endpoint introduces a new request-body field name (`GET` takes only the existing `appliance_id` path parameter; `POST rotate` has no body at all, per Decision F) — `backend-api/app/core/error_handlers.py`'s `SENSITIVE_KEYS` needed zero changes for this module.
- Every query in this module uses an explicit column list — never `SELECT *`.
- `password_hash`/plaintext passwords are entirely untouched by this module (no relationship to `platform_users`).
- The validation script's full leak sweep (`response_has_sensitive_string`, `response_has_raw_activation_token`, `response_has_raw_appliance_api_key`, and a new `response_has_raw_rotated_appliance_api_key` covering both rotations performed during the run) ran on every single HTTP response captured during the run, including the negative/RBAC-denial responses.

## 13. Database/schema notes

**No schema migration was needed.** All four columns KB-017 reads/writes (`appliance_api_key_hash`, `appliance_api_key_hint`, `appliance_key_created_at`, `appliance_key_last_used_at`) were already added to `appliances` by KB-016's `postgres/init/003_kb016_appliance_registration_heartbeat.sql`, confirmed present before any implementation work began. No `postgres/init/*.sql` file was created or modified, no live-database migration script was run, and `appliances_appliance_api_key_hash_key` (the existing KB-016 unique constraint) was left exactly as-is — rotation's `UPDATE` still goes through the same constraint, defended by the same `UniqueViolation` catch pattern described in section 9.

## 14. Validation steps performed

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose build backend-api
docker compose up -d backend-api
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb017_validate_appliance_credential_visibility_rotation.sh
```

`scripts/kb017_validate_appliance_credential_visibility_rotation.sh` internally reruns `./scripts/kb016_validate_appliance_registration_heartbeat.sh` unmodified as its behavior-regression gate (which itself reruns KB-015 → KB-014 → KB-013 → KB-012 → KB-011 unmodified).

Confirmed by the passing run:

- `/health`, `/auth/roles`, `/docs` remain public; `/appliance/register` and `/appliance/heartbeat` (KB-016) remain registered and working.
- `GET /admin/appliances/{appliance_id}/credential` and `POST /admin/appliances/{appliance_id}/credential/rotate` both require a valid JWT — no token and a garbage token both return `401`.
- `customer_viewer` (customer role) is denied `403` on both endpoints.
- `platform_admin`, `soc_manager`, and `soc_analyst` can all read credential metadata (`200`).
- Only `platform_admin` can rotate — `soc_manager` and `soc_analyst` both get `403` on rotate.
- Credential metadata never exposed a raw key or `appliance_api_key_hash`; `has_appliance_api_key`, `appliance_api_key_hint`, and `appliance_key_created_at` were correct, and `appliance_key_last_used_at` was `null` before the first heartbeat.
- Rotation returned the new raw `appliance_api_key` exactly once, refreshed `appliance_key_created_at`, and reset `appliance_key_last_used_at` to `null`.
- After rotation, a heartbeat with the OLD key failed with `401` and did not update `appliance_key_last_used_at`; a heartbeat with the NEW key succeeded with `200` and did update it.
- Rotation succeeded for a retired appliance without changing its status; a heartbeat from that retired appliance still failed with `403` even with the freshly rotated key.
- Invalid UUID path parameters returned a clean `422`; unknown valid UUIDs returned a clean `404`.
- No response at any point exposed `token_hash`, `appliance_api_key_hash`, the raw activation token outside its one creation response, the original or either rotated raw appliance API key outside their own one-time responses, `password_hash`, or a password value.
- All fake KB-017 validation appliance/heartbeat/activation-token fixtures were cleaned up — 0 rows remaining afterward.
- `./scripts/kb016_validate_appliance_registration_heartbeat.sh` passed unmodified inside the KB-017 run.

Final validation result:

```
KB-017 APPLIANCE CREDENTIAL VISIBILITY AND ROTATION VALIDATION PASSED
```

## 15. Regression chain

```
KB-017 → KB-016 → KB-015 → KB-014 → KB-013 → KB-012 → KB-011
```

Each validation script reruns the previous module's script unmodified as its own regression gate. This run confirmed no observable behavior change to appliance registration/heartbeat, admin appliance management, user management, tenant management, route structure, auth, RBAC, tenant isolation, or validation-error redaction.

Post-validation safety check also confirmed:

- Only the expected files changed before this documentation pass: `backend-api/app/api/routes/appliance_management.py`, `backend-api/app/schemas/appliances.py`, `scripts/kb017_validate_appliance_credential_visibility_rotation.sh`.
- All protected/do-not-touch files unchanged; `.env` was not read or printed.
- Python syntax and Bash syntax both passed.
- Docker services healthy.
- Both new KB-017 paths present in `/openapi.json`.
- No fake KB-017 validation data left behind.
- Backend logs showed no `Traceback`/`ERROR`/`CRITICAL` entries.

## 16. Operational notes

- **Admins now have a safe, cheap way to answer "does this appliance have a working credential, and when was it last used?"** without querying the database directly — `GET .../credential` is a lightweight read, safe for `soc_manager`/`soc_analyst` as well as `platform_admin`.
- **Rotation is the recommended recovery path for a lost/compromised appliance API key** — it no longer requires issuing a brand-new activation token and creating a second appliance row (which would additionally fail with `409` on the existing `appliance_name`/`appliance_uuid` uniqueness constraints); the same appliance row keeps its identity, history, and heartbeat records, only the credential changes.
- **There is still no multi-key history.** If it becomes operationally important to know *when* a rotation happened (not just that `appliance_key_created_at` changed) or to audit *who* rotated a credential, a future module would need either a new audit-log entry per rotation or a dedicated credential-history table — deliberately not built here (see section 3).
- **The regression-gate chain is now six scripts deep** (KB-017 → KB-016 → KB-015 → KB-014 → KB-013 → KB-012 → KB-011) and continues to work well as a lightweight, cumulative regression suite.
- **Validation-script "file unmodified" checks must use `git diff`, not content grep**, going forward — the false-positive bug fixed in this module (section 5) is a reusable lesson: any file that might legitimately already contain a keyword related to the current module's feature area should be checked for the *absence of a diff*, never the *absence of a keyword*.

## 17. Rollback notes

- **Application rollback:** remove the two new functions (`get_appliance_credential()`, `rotate_appliance_credential()`) and the `ADMIN_APPLIANCE_CREDENTIAL_WRITE_ROLES` constant from `appliance_management.py`, remove `ApplianceCredentialMetadata`/`ApplianceCredentialRotateResponse` from `schemas/appliances.py`, delete the new validation script, rebuild `backend-api`. This restores the exact KB-016 validated behavior (tag `kb016-appliance-registration-heartbeat-validated`, commit `f699b74`) — no migration to reverse, since none was made.
- **Migration rollback:** not applicable — no schema change was made in this module.
- **Test data cleanup:** `scripts/kb017_validate_appliance_credential_visibility_rotation.sh` removes its own fake appliance (`kb017-validation-appliance`), its heartbeats (via `ON DELETE CASCADE`), and its fake activation token (`KB017 Validation Site (fake, safe to delete)`) both at the end of a successful run and in its failure trap — confirmed to leave 0 rows behind in the passing run.

## 18. Final state

- Branch: `kb017-appliance-credential-visibility-rotation`.
- Implementation complete, validated, and confirmed passing, including the full regression chain back through KB-011.
- **Not yet committed, tagged, or snapshotted** — commit ID, tag, and snapshot are all still pending a separate, explicit user instruction. This documentation pass does not create any of them.
- Files awaiting commit: `backend-api/app/api/routes/appliance_management.py`, `backend-api/app/schemas/appliances.py`, `scripts/kb017_validate_appliance_credential_visibility_rotation.sh`, plus this completion doc and the `docs/AI_PROMPT_LEDGER.md` update from this documentation pass.

## 19. Recommended next module

**Recommended: KB-018 Admin Frontend Foundation.**

Purpose: start the first visible, branded admin dashboard, consuming the backend APIs already built across KB-010 through KB-017, rather than adding further backend-only surface:

- Login page (against the existing `POST /auth/login`).
- Admin dashboard shell (navigation, session/token handling, role-aware visibility).
- Tenants page (`GET /admin/tenants`, `GET/POST/PATCH /admin/tenants/{tenant_id}`, KB-013).
- Users page (`GET/POST/PATCH /admin/users`, `/admin/users/{user_id}`, `/admin/users/{user_id}/password`, KB-014).
- Appliances page (`GET /admin/appliances`, `GET/PATCH /admin/appliances/{appliance_id}`, KB-015).
- Appliance credential metadata page/action (`GET .../credential`, `POST .../credential/rotate`, KB-017 — this module).
- Activation token create/list (`POST/GET /admin/tenants/{tenant_id}/appliance-activation-tokens`, `PATCH .../revoke`, KB-015).
- No Wazuh dependency yet.

This is recommended over starting Wazuh stack deployment and alert ingestion next, because the backend now has enough admin-facing surface area (auth, tenants, users, appliances, activation tokens, credentials) that a first visible dashboard delivers real, demonstrable value and lets a human operator actually exercise all of KB-010 through KB-017 through a UI instead of `curl`/`jq`. Wazuh deployment and alert ingestion should follow the first admin dashboard foundation — **unless the user decides to prioritize backend data ingestion first**, in which case that should be an explicit decision made before planning begins, not an assumption carried forward from this document. As with every prior module, KB-018 (or whichever module is chosen next) should be explicitly defined and approved by the user before any planning or implementation begins.
