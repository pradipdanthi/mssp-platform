# KB-062 — Admin Recommendations and Notifications Lists

Status: **Implemented**  
Branch: `kb039-kb060-platform-roadmap-execution`

## Purpose

Make Admin dashboard KPI tiles for **Open Recommendations** and **Notifications Sent** open real pages, and give SOC cross-tenant read lists.

## APIs

- `GET /admin/recommendations` — latest 100 recommendations (all tenants), Admin/SOC roles only
- `GET /admin/notifications` — latest 100 notification events (preview only; no recipient address)

## UI

- `/recommendations` and `/notifications` in Admin portal
- Sidebar nav entries
- Dashboard KPI cards link to those routes

## Shuffle → control plane hop (companion)

Use `scripts/kb062_shuffle_control_plane_hop_helper.sh` for the HTTP action template.  
Until Shuffle HTTP hop is saved in the UI, `scripts/kb061_run_periodic_sync.sh` continues to pull TheHive → DEMO.

## Validation

```bash
./scripts/kb062_validate_admin_recommendations_notifications.sh
```

Expected:

```text
KB-062 ADMIN RECOMMENDATIONS NOTIFICATIONS VALIDATION PASSED
```

## Must not

- Expose notification recipient addresses/API keys to customer UI
- Commit `.secrets/` or sync keys
