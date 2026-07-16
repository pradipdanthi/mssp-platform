# KB-032 — AI Context and Documentation Sync

Status: Implemented (pending validation/commit).  
Branch: `kb032-ai-context-doc-sync`  
Type: **Documentation / AI context only** — no runtime code, schema, compose, or `.env` changes.

## Purpose

Git commits and tags already show the lab validated through **KB-031** (`d27bdea`, `kb031-customer-report-detail-validated`), but agent context files had drifted (still describing ~KB-012). KB-032 realigns AI-facing documentation so Cursor/Claude/other agents plan safely without inventing outdated architecture or breaking boundaries.

## Why this was needed

Stale docs caused risk of:

- Planning against wrong “current module”
- Ignoring existing customer portal list/detail coverage
- Forgetting protected paths (`.env`, compose, schema, admin frontend)
- Forgetting “validation before commit” and “plan before implement”

## Files updated / added

| Path | Role |
|---|---|
| `AGENTS.md` | Baseline through KB-031; workflow; customer portal map; source-of-truth note |
| `CLAUDE.md` | Operating instructions refreshed for KB-031/032 |
| `.cursor/rules/mssp-control-plane.mdc` | Always-applied Cursor rules refreshed |
| `CONTEXT.md` | Recreated snapshot (>5KB) of current lab state |
| `docs/AI_PROMPT_LEDGER.md` | KB-025…KB-031 marked validated/committed; KB-032 row added |
| `docs/KB032_AI_CONTEXT_DOC_SYNC.md` | This record |
| `scripts/kb032_validate_ai_context_doc_sync.sh` | Docs-only validation gate |

## Explicitly unchanged

- `backend-api/` runtime code
- `frontend-customer/` runtime code
- `frontend-admin/`
- `postgres/init/`
- `docker-compose.yml`
- `.env`

## Current validated feature pointer

- KB-031 Customer Report Detail UI
- Commit `d27bdea`
- Tag `kb031-customer-report-detail-validated`

## Safety workflow restated

1. Inspect git + files before planning
2. Plan before implementation
3. No `.env` / unapproved compose / schema / admin-frontend edits
4. Customer frontend: **no `/admin`**
5. Validation script PASS before commit
6. Then commit → tag → Proxmox snapshot (user-driven)

## Next feature candidates (not started)

1. Customer notifications history
2. Customer appliance detail
3. Account/profile hardening

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb032_validate_ai_context_doc_sync.sh
./scripts/kb032_validate_ai_context_doc_sync.sh
```

Expected final line:

```text
KB-032 AI CONTEXT DOC SYNC VALIDATION PASSED
```
