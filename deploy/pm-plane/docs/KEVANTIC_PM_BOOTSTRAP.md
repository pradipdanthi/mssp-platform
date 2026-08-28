# Kevantic PM — initial Plane workspace setup

After first login at **http://localhost:8080**, create this structure so it mirrors how we build the MSSP platform.

---

## 1. Workspace

| Field | Value |
|-------|--------|
| Name | **Kevantic** |
| Slug | `kevantic` |
| Description | MSSP control plane, appliances, portals, marketing |

---

## 2. Projects (one per program area)

Create these **Projects** inside the workspace:

| Project | Identifier | Purpose |
|---------|------------|---------|
| Platform Control Plane | `CTRL` | VM 100, backend-api, Postgres, admin/customer portals |
| Appliance & Edge | `EDGE` | VM 199 golden, Wazuh AR, NikTiar Edge Node |
| Marketing & Public Web | `WEB` | kevantic.com, tier copy, Hostinger deploy |
| Security Engines | `ENG` | Wazuh, Suricata, ClickHouse, identity ITDR |
| Ops & Demo | `OPS` | Demo tenants, lab validation, runbooks |

---

## 3. Milestones (completed work — for context)

Add milestones so history is not lost:

### CTRL — Platform Control Plane

| Milestone | Status | Notes |
|-----------|--------|-------|
| Phase 1 — Source of truth | Done | `PRODUCT_TIER_SOURCE_OF_TRUTH.md` |
| Phase 2 — Portal tier alignment | Done | Admin Tier Ops, customer tier-only gating |
| Phase 4 — Backend hardening | Done | Route guards, greenbone constraint, Silver reset |
| Phase 5 — Tier upgrade testing | **Next** | Customer request → admin rollout |

### WEB — Marketing

| Milestone | Status |
|-----------|--------|
| Phase 3 — Marketing 3-tier NikTiar | Done |

---

## 4. Issue types to use

| Type | When |
|------|------|
| **Epic** | Whole phase (e.g. "Phase 5 tier upgrade E2E") |
| **Feature** | Deliverable (e.g. "Admin tier rollout email") |
| **Bug** | Regression |
| **Chore** | Deploy, bake golden, FTP |
| **Doc** | Design decisions — link to repo markdown |

**Rule:** Put design truth in Git (`/opt/mssp-control/*.md`); Plane issue = tracker + link.

Example issue description:

```markdown
## Goal
Provision Gold tier from customer portal request through admin approval.

## Repo links
- `backend-api/app/api/routes/tenant_management.py` — tier-rollout
- `frontend-admin/.../TierRolloutPanel.tsx`

## Acceptance
- [ ] Silver tenant submits tier_gold request
- [ ] Admin provisions via Tier Operations
- [ ] Customer nav unlocks Gold modules
```

---

## 5. Modules (optional per project)

**CTRL** modules: `Backend`, `Admin Portal`, `Customer Portal`, `Database`

**WEB** modules: `kevantic-website`, `website-niktiar`, `FTP deploy`

---

## 6. Cycles (2-week sprints)

Name examples:

- `2026-W35` — Tier testing + PM deploy
- `2026-W36` — Golden bake + Phase 5 closeout

---

## 7. Pages (wiki-lite)

Create a **Page** per major doc:

| Page title | Link to repo file |
|------------|-------------------|
| Tier source of truth | `PRODUCT_TIER_SOURCE_OF_TRUTH.md` |
| Marketing updates | `MARKETING_WEBSITE_UPDATES.md` |
| PM deploy runbook | `deploy/pm-plane/README.md` |

Paste summary + GitHub path; do not duplicate full specs.

---

## 8. Git integration (recommended)

Settings → Integrations → **GitHub** → connect `pradipdanthi/mssp-platform`

Then link issues to commits/PRs with issue IDs in commit messages:

```text
feat(portal): tier rollout panel CTRL-42
```

---

## 9. Users

| Role | Who |
|------|-----|
| Admin | You (instance owner) |
| Member | Dev collaborators |

---

## 10. What NOT to track in Plane

- Secrets (`.env`, FTP passwords)
- Raw customer data
- Full markdown specs (keep in repo; link only)

---

*This bootstrap matches MSSP platform phases as of Aug 2026.*
