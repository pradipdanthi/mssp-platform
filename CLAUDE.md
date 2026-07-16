# CLAUDE.md — Claude / Cursor Operating Instructions

Status: Permanent reference document. Created in KB-009A; refreshed in **KB-032** and **KB-036** (enterprise architecture roadmap).
Audience: Claude (in Cursor or Claude Code), and any other AI coding agent that reads a `CLAUDE.md` convention file.

This file tells you how to operate in this repository. `AGENTS.md` is the full rulebook. `CONTEXT.md` is the short “where we are now” snapshot. Read them with this file.

**Source of truth:** Live git tags/commits, validation-script output, and inspected source files beat stale documentation.

---

## 1. Files to Read First (every session)

1. `/opt/mssp-control/CONTEXT.md` — current state through KB-035+ and enterprise architecture summary.
2. `/opt/mssp-control/docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` — full MSSP/SOC/MDR/XDR roadmap, deployment models, KB-037–060.
3. `/opt/mssp-control/AGENTS.md` — full project rules, security, tenant isolation.
4. `/opt/mssp-control/.cursor/rules/mssp-control-plane.mdc` — condensed Cursor rules.
5. `/opt/mssp-control/docs/AI_PROMPT_LEDGER.md` — prior AI-assisted changes.
6. Source files for the current task — **always inspect before planning or editing**.

---

## 2. Behavior Rules

Short form: **planning before implementation**, **no .env**, **no /admin** from customer frontend, **validation before commit**.

- Plan before implementing; stop for approval unless implement scope already approved.
- **Do not install Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor, or create VMs 101–111** unless the current KB explicitly approves it.
- Customer frontend must **never** call `/admin`.
- Never commit before validation passes.
- Guide the non-coder user **one step at a time** when they ask for lab workflow.

---

## 3. Output Style (this user is not a programmer)

- Plain English; full paths under `/opt/mssp-control/`.
- Complete edits only; exact copy-pasteable commands + expected success signals.
- After changes: summary, file list, `git status --short`, validation command — then **stop and wait**.

---

## 4. What to Avoid

- Do not invent runtime code for docs-only modules (KB-032, KB-036).
- Do not expose raw logs, raw Wazuh/Suricata/Zeek data, or forbidden fields to customers.
- Do not convert the product to Streamlit or expose Wazuh/third-party UIs directly to customers.
- Do not start KB-037+ until the user explicitly kicks it off.

---

## 5. Validation Discipline

Docs-only: `scripts/kb036_validate_mssp_platform_architecture_roadmap.sh`  
Feature modules: their `scripts/kb0NN_validate_*.sh` until PASS.

Safe delivery: **validation → commit → tag → snapshot** (user-driven each step).

---

## 6. Current Module Context

**Latest validated feature:** KB-035 Customer Appliance Detail UI — `1ac1df3`, tag `kb035-customer-appliance-detail-validated`.

**Control plane (VM 100):** Admin/SOC foundation + full customer portal through KB-035. **No live SOC ingestion yet.**

**KB-036:** Enterprise MSSP/SOC/MDR/XDR architecture and deployment model roadmap — docs only. Covers cloud/on-prem/hybrid models, full capability stack (Wazuh, Suricata, Zeek, TheHive, Shuffle, MISP, Greenbone, Velociraptor, etc.), VM 100–111, KB-037–060 sequence.

**Normalization rule:** Control plane consumes tenant-scoped records (`tenant`, `source_platform`, `asset`, `alert`, `incident`/`case`, `recommendation`, `vulnerability`, `report`, `visibility_status`, `sync_health_status`) regardless of source engine.

**Next:** KB-037+ only when user explicitly approves — see KB-036 roadmap doc.
