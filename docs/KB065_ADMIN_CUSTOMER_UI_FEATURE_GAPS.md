# Admin & Customer Dashboard Feature Gap Checklist

Status: **Phase A implemented** (2026-07-25) — Admin Add Customer / Add User UI live  
Purpose: Confirm what the product promised vs what the UI actually does, before more SOC E2E work.  
Paused separately: commercial MSSP completeness + KB-064 full E2E (see `.cursor/rules/paused-work-and-ui-gaps.mdc`).

**Important clarification:** PostgreSQL + tenant/user tables + create APIs were **already running**. Nothing new needed to be “deployed as SQL.” The gap was only Admin UI forms. Lab and future prod share the same stack path (Compose + existing APIs).

---

## 1. Root cause of “no Add Customer” (fixed in Phase A)

| Layer | Reality |
|---|---|
| Backend | **Already built.** KB-013: `POST /admin/tenants`, `PATCH /admin/tenants/{id}`. KB-014: `POST /admin/users`, `PATCH` user + password. |
| Admin UI (before) | Read-only lists only. |
| Admin UI (now) | **Add Customer / Edit**, **Add User / Edit / Set password** on `http://192.168.0.201:3000/` (platform_admin). |
| Your requirement | Onboard every new customer from Admin dashboard — **never** touch DB/SQL for routine onboarding. |

Validation: `./scripts/kb065_validate_admin_customer_user_onboarding_ui.sh` (optional live API proof with `PLATFORM_ADMIN_PASSWORD`).

---

## 2. Admin dashboard gap matrix

Against `AGENTS.md` §1.1 and live UI at `http://192.168.0.201:3000/`.

| Capability | Backend API | Admin UI today | Gap |
|---|---|---|---|
| Customer/tenant onboarding (create) | Yes (KB-013) | **Yes** — Add Customer (KB-065) | Done |
| Edit tenant (status, SLA, etc.) | Yes (KB-013) | **Yes** — Edit (KB-065) | Done |
| Create customer / SOC users | Yes (KB-014) | **Yes** — Add User (KB-065) | Done |
| Disable user / set password | Yes (KB-014) | **Yes** — Edit + Set password (KB-065) | Done |
| Activation token generate/revoke | Yes | **Yes** (Appliances page, KB-019) | OK |
| Appliance credential view/rotate | Yes | **Yes** (KB-017/019 UI) | OK |
| Appliance health list | Yes | **Yes** (list) | Partial (no rich detail page) |
| Protected asset admin CRUD | **Yes** (KB-066) | **Yes** — Assets page | Done |
| Alert triage + customer_visible | Yes (KB-056) | **Yes** (detail) | OK |
| Incident triage + comments | Yes (KB-056) | **Yes** (detail) | OK |
| Analyst assignment | Via incident PATCH | **Yes** (detail form) | OK |
| Recommendations list | Yes (KB-062) | **Yes** | OK |
| Create/edit recommendation + visibility | **Yes** (KB-066) | **Yes** — Add/Edit | Done |
| Notifications list | Yes (KB-062) | **Yes** (list only) | Low (send worker not productized) |
| Monthly report authoring / publish | **Yes** (KB-066) | **Yes** — Reports page | Done |
| Audit / compliance visibility | **Yes** (KB-066 list) | **Yes** — Audit page | Done (viewer; write coverage grows over time) |
| Dashboard KPIs | Yes | **Yes** (clickable tiles) | OK |

---

## 3. Customer dashboard gap matrix

Against `AGENTS.md` §1.2 and portal on `:3001`.

| Capability | Status |
|---|---|
| Login, branded shell, account/password | **Done** (KB-021, KB-034) |
| Security summary dashboard | **Done** (KB-028) |
| Appliance health list + detail | **Done** (KB-023, KB-035) |
| Protected asset list + detail | **Done** (KB-023, KB-030) |
| Customer-visible alerts list + detail | **Done** (KB-022, KB-029) |
| Customer-visible incidents list + detail | **Done** (KB-025) |
| Recommendations list + detail | **Done** (KB-026, KB-027) |
| Monthly reports list + detail | **Done** (KB-024, KB-031) |
| Notification history | **Done** (KB-033) |
| Plain-English / business impact | **Partial** — fields exist; depend on SOC filling / AI workers (AI worker not live) |
| Customer action items | **Partial** — via recommendations + incident `customer_action_required` |
| Live SOC data without SOC approval | **Intentionally blocked** — `customer_visible` gate (correct for MSSP) |

Customer portal is largely **complete as a read-only safe portal**. Main pain is Admin cannot create the tenant/users that the portal belongs to.

---

## 4. Recommended build order (Admin first)

### Phase A — Customer onboarding (highest priority)

**Goal:** New paying customer without SQL.

1. **Add Customer** on Tenants page → calls `POST /admin/tenants`.
2. **Edit Customer** (status, SLA, criticality, timezone, notes) → `PATCH /admin/tenants/{id}`.
3. **Add User** on Users page (esp. `customer_admin` / `customer_viewer` tied to tenant) → `POST /admin/users`.
4. **Edit user** status/name + **Set password** → existing PATCH APIs.
5. Optional same-flow helper: after create tenant, deep-link to “Create first customer admin” + “Issue activation token” (token UI already exists under Appliances).

No new backend required for Phase A if we stick to KB-013/014 contracts.

### Phase B — Admin ops completeness

- Recommendations create/edit + set `customer_visible`
- Admin Reports page (create/publish monthly report) — may need new Admin APIs
- Protected assets admin view
- Audit log viewer

### Phase C — Resume paused work

- Return to MSSP readiness / Windows agent / KB-064 E2E when you ask

---

## 5. What we will not do in Phase A

- No `.env` edits or secret commits
- No schema rewrite
- No customer portal calling `/admin`
- No deleting tenants/users (soft status only — matches KB-013/014)

---

## 6. Decision needed from you

Choose one:

1. **Onboard wizard** — one Admin screen: New Customer → first admin user → optional activation token tip  
2. **Separate pages** — Add/Edit on Tenants, then Add/Edit on Users (simpler, matches existing nav)  
3. **Gap doc only for now** — approve this checklist, implement after you pick Phase A style  

Default recommendation: **(2) Separate pages first**, then optionally wrap into a wizard later.
