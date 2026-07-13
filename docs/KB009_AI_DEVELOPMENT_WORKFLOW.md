# KB-009: AI Development Workflow

Module: KB-009A — AI development rules and prompt framework
Status: Documentation only. No runtime code was changed in this module.
Location: `/opt/mssp-control/docs/KB009_AI_DEVELOPMENT_WORKFLOW.md`

This document explains, in plain language, how ChatGPT, Cursor, and Claude are meant to work together on this project, what the branch/validation workflow is, and how AI prompts should be structured going forward.

---

## 1. Purpose of Each AI Tool

This project uses three different AI tools, each for a different job. Using the right tool for the right job keeps changes safe and reviewable.

### ChatGPT (planning / architecture partner)

- Used for high-level planning, architecture discussion, and thinking through trade-offs before any code is written.
- Used to draft KB module plans (like this one) and to reason about security/tenant-isolation implications before implementation.
- Does not directly touch the repository. Its output is plans, explanations, and draft text that a human or a coding agent (Cursor/Claude) then implements.

### Cursor (primary coding agent / IDE)

- Used for actually reading the repository, writing files, running commands, and making the real code changes on the VM.
- Follows the rules in `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/mssp-control-plane.mdc` automatically for every request.
- Every Cursor-made change must go through: inspect → plan → edit → show `git status --short` → give validation commands → stop (no auto-commit).

### Claude (coding agent inside Cursor, or Claude Code)

- Same repository, same rules as Cursor — `AGENTS.md` and `CLAUDE.md` apply equally.
- Used interchangeably with Cursor's own model for implementation work, or for a "second opinion" review of a Cursor-made change.
- Must read the same files first (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/mssp-control-plane.mdc`, `docs/AI_PROMPT_LEDGER.md`) before acting.

### Future coding agents

- Any future AI coding agent added to this workflow must be pointed at `AGENTS.md` as its primary rulebook. If the tool supports a tool-specific convention file (like `CLAUDE.md` for Claude, or `.cursor/rules/*.mdc` for Cursor), a matching file should be added for it, mirroring the same rules.

---

## 2. Development Workflow

The general flow for any new piece of work (a "KB module") is:

1. **Plan (ChatGPT or Cursor Plan mode).** Describe the goal, the affected files, the security/tenant-isolation implications, and get a short written plan before writing code.
2. **Confirm state (Cursor/Claude).** Confirm current Git branch, `git status`, and read the relevant existing files.
3. **Implement (Cursor/Claude).** Make only the planned changes, following `AGENTS.md` rules — modular backend code, tenant isolation, no hardcoded secrets, complete production-ready files.
4. **Validate (human + agent together).** Run the relevant validation commands/scripts and confirm expected output.
5. **Review (human).** The non-coder user reviews the plain-language explanation, the file list, and the validation output.
6. **Commit (human decision only).** The AI agent never commits automatically. The human decides when to stage and commit, and with what commit message.
7. **Record (docs/AI_PROMPT_LEDGER.md).** Log the prompt, files changed, validation result, and commit ID once committed.

---

## 3. Branch Model

- `main` (or the primary branch) holds known-good, validated states. The last fully validated foundation is tagged `kb008-validated-foundation` at commit `c52bca1`.
- Each KB module (or related group of changes) is developed on its own feature branch, named `kbNNN-short-description` (e.g. `kb009-developer-workflow`, and going forward `kb010-auth-rbac`, etc.).
- Work happens on the feature branch. Validation happens on the feature branch. Only after validation passes and the human approves does the branch get merged/tagged into the main line — that merge/tag step is a human decision, not something an AI agent does automatically.
- Known-good states should be tagged (e.g. `kb008-validated-foundation`) so there is always an easy rollback point.
- AI agents must confirm the current branch (`git branch --show-current`) before making any change, and must not switch or create branches unless explicitly instructed.

---

## 4. Validation Discipline

No KB module is considered "done" until its validation passes and the output has been shown to the user.

Baseline commands that must keep working after every module:

```bash
cd /opt/mssp-control
git branch --show-current
git status --short
docker compose ps
curl -fsS http://localhost:8000/health | jq .
./scripts/kb008_validate_backend_api_foundation.sh
```

Rules:

- Every module that changes backend behavior should add its own validation script under `scripts/`, following the `kb008_validate_backend_api_foundation.sh` pattern: clear section headers, explicit pass/fail checks (`fail()` helper), non-zero exit on failure, and a clear final "VALIDATION PASSED" message.
- Validation output must always be shown to the user, including failures. Failures are never hidden or summarized away.
- If a validation script fails, the AI agent must show the exact failure and propose a specific fix, not a vague retry.

---

## 5. How Prompts Will Be Used

- Prompts to AI coding agents should follow the templates in `docs/PROMPT_TEMPLATES.md` (planning, implementation, debugging, code review).
- Every prompt should state: the KB module it belongs to, the exact goal, any files that must not be touched, and the validation expected at the end.
- Significant AI-assisted changes (anything that touches code, schema, or infrastructure) should be logged in `docs/AI_PROMPT_LEDGER.md` with: date, KB module, short prompt summary, files changed, validation result, and commit ID (once committed).
- Prompts should never ask an AI agent to skip security rules, tenant isolation, or the do-not-touch list from `AGENTS.md`. If a prompt seems to require that, the plan should be reconsidered before implementation.

---

## 6. Current Module: KB-010 (Phase 1 complete)

**KB-010 — Authentication / Login + Role-Based Access Control (RBAC), Phase 1** has been implemented:

- A secure login endpoint (`POST /auth/login`) against the existing `platform_users` table.
- Password hashing with bcrypt (`platform_users.password_hash`, added via migration).
- JWT token issuance and verification (`GET /auth/me`).
- Role-based access control matching the updated `platform_users.role` values (`platform_admin`, `soc_manager`, `soc_analyst`, `customer_admin`, `customer_viewer` — the top role was renamed from `super_admin` to `platform_admin` as part of this module).
- `require_tenant_match(...)` foundation so customer-role tokens can only ever access their own `tenant_id` (built, not yet attached to any endpoint).
- New modular backend files under `backend-api/app/core/`, `backend-api/app/db/`, `backend-api/app/api/`, `backend-api/app/schemas/`, and `backend-api/app/services/`, per the structure defined in `AGENTS.md`.
- Validation script: `scripts/kb010_validate_auth_rbac.sh`.

**Deferred to a later phase/module:** protecting the existing `/admin/*` and `/customer/*` preview endpoints (Phase 2), and account-lockout hardening columns.

KB-010 Phase 2 or KB-011 should not begin until explicitly started in a new prompt, using the prompt templates in `docs/PROMPT_TEMPLATES.md`.
