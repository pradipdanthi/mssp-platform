# CLAUDE.md — Claude / Cursor Operating Instructions

Status: Permanent reference document. Created in KB-009A; refreshed in **KB-032** (AI context doc sync).
Audience: Claude (in Cursor or Claude Code), and any other AI coding agent that reads a `CLAUDE.md` convention file.

This file tells you how to operate in this repository. `AGENTS.md` is the full rulebook. `CONTEXT.md` is the short “where we are now” snapshot. Read them with this file.

**Source of truth:** Live git tags/commits, validation-script output, and inspected source files beat stale documentation. If docs disagree with `git log` / `git tag`, say so and trust git.

---

## 1. Files to Read First (every session)

Before doing anything in this repository, read, in this order:

1. `/opt/mssp-control/CONTEXT.md` — current validated state through KB-031+ and next candidates.
2. `/opt/mssp-control/AGENTS.md` — full project rules, architecture, security, tenant isolation.
3. `/opt/mssp-control/.cursor/rules/mssp-control-plane.mdc` — condensed always-applied Cursor rules.
4. `/opt/mssp-control/docs/AI_PROMPT_LEDGER.md` — prior AI-assisted changes.
5. The specific source files for the current task — **always inspect before planning or editing**.

If any of these are missing or out of date versus git tags, say so before proceeding.

---

## 2. Behavior Rules

Short form (must remain searchable): **planning before implementation**, **no .env**, **no /admin** from customer frontend, **validation before commit**.

- **Inspect before acting:** branch, `git status`, tags, and relevant source files.
- **Plan before implementing:** plain-language plan + exact file list; **do not implement until the plan is reviewed/approved** (unless the user already gave an implement-now approved scope).
- **Minimal, targeted changes** for the current KB only.
- **Complete output only** — no placeholders / TODOs in production files.
- **Respect protected paths** unless the task explicitly allows them: `.env`, `docker-compose.yml`, `postgres/init/`, `frontend-admin/` (for customer work), and do-not-touch files in `AGENTS.md`.
- **Never restart Docker** unless explicitly instructed.
- **Never commit / stage / tag** unless the user explicitly asks in that same request.
- **Never commit before validation passes.**
- **Security first:** never print `.env`, never hardcode secrets, never leak tenant data, never return password hashes, parameterized SQL only.
- Customer frontend must **never** call `/admin`.

---

## 3. Output Style (this user is not a programmer)

- Explain in plain English; always give full paths under `/opt/mssp-control/`.
- Complete edits only — never “add the rest yourself.”
- Exact copy-pasteable commands + expected success signals.
- After changes: summary, file list, `git status --short`, validation command — then **stop and wait**. Do not commit.

---

## 4. What to Avoid

- Do not invent runtime code when the task is docs-only (KB-032).
- Do not touch `docker-compose.yml`, `.env`, or `postgres/init/` without explicit approval.
- Do not call `/admin` from `frontend-customer`.
- Do not expose forbidden customer fields (secrets, IPs, raw JSON/metrics, `report_file_path`, internal notes, stack traces, appliance credentials, etc.).
- Do not convert the product to Streamlit or expose Wazuh to customers.
- Do not start the next feature KB until the user explicitly kicks it off.

---

## 5. Validation Discipline

Every change needs a verification path. Docs-only modules use a docs validation script (e.g. `scripts/kb032_validate_ai_context_doc_sync.sh`). Feature modules need their `scripts/kb0NN_validate_*.sh` and must pass before commit/tag.

Baseline health checks:

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose ps
curl -fsS http://localhost:8000/health | jq .
```

Safe delivery order: **validation script first → then commit → then tag → then Proxmox snapshot** (only when the user requests each step).

---

## 6. Current Module Context (through KB-031; KB-032 = docs sync)

**Latest validated feature:** **KB-031** Customer Report Detail UI — commit `d27bdea`, tag `kb031-customer-report-detail-validated`.

**Customer portal working (port 3001):** dashboard v2; alerts/incidents/assets/reports/recommendations **lists**; detail pages for alerts, incidents, protected assets, reports, and recommendations. Appliance **detail** is still deferred. Customer UI uses `/customer/*` only — **no `/admin`**.

**Auth / isolation:** JWT + bcrypt; `get_current_user` + `require_tenant_match`; wrong tenant → **404**.

**KB-032:** AI Context and Documentation Sync — updates `AGENTS.md`, `CLAUDE.md`, Cursor rules, `CONTEXT.md`, ledger, and validation script only. **No backend/frontend/schema/compose/.env runtime changes.**

**Next feature candidates after KB-032 is validated/committed:**

1. Customer notifications history
2. Customer appliance detail
3. Account/profile hardening

Do not implement those until planning is approved.
