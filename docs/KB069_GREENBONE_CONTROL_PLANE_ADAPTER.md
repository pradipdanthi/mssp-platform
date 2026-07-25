# KB-069 — Greenbone → Control Plane Vulnerability Adapter

Status: **Implemented** — schema + ingest API + Admin UI promote-to-recommendation.  
Branch: `kb039-kb060-platform-roadmap-execution`  
Builds on: KB-052/053 (plans), KB-068 (Greenbone VM 109 live), KB-026/027/066 (recommendations).

---

## 1. Purpose

Bring **normalized Greenbone findings** into the MSSP Control Plane so SOC can review them in Admin and promote high/critical items into **customer recommendations** — without exposing raw scan data to the customer portal.

---

## 2. What shipped

| Layer | Detail |
|---|---|
| Schema | `vulnerabilities` table + `customer_recommendations.related_vulnerability_id` |
| Ingest | `POST /integrations/vuln/sync` with `X-Vuln-Sync-Key` |
| Admin API | `GET /admin/vulnerabilities`, detail, `POST .../promote-recommendation` |
| Admin UI | **Vulnerabilities** nav page — list, view, promote |
| Customer portal | **Unchanged** — customers only see recommendations when `customer_visible=true` |
| Secrets | `.secrets/vuln_sync_api_key` (gitignored) mounted into backend |

---

## 3. KB-053 rules applied

- Critical/High auto-create a **draft recommendation** (`customer_visible=false`) on ingest unless overridden
- Medium/Low skip auto-create unless `create_recommendation=true`
- Dedup key: `(tenant_id, source_platform, external_finding_id)`
- Plain-English recommendation text; no raw NVT/XML to customers
- Wrong-tenant asset ID on ingest → **422**

---

## 4. Operator commands

```bash
cd /opt/mssp-control

# Migration (once)
chmod +x scripts/kb069_create_vulnerabilities.sh
./scripts/kb069_create_vulnerabilities.sh

# Ensure sync key exists (never commit)
mkdir -p .secrets
[ -f .secrets/vuln_sync_api_key ] || openssl rand -hex 32 > .secrets/vuln_sync_api_key
chmod 600 .secrets/vuln_sync_api_key

# Rebuild API + Admin UI after code change
docker compose up -d --build backend-api frontend-admin

# Sample ingest into DEMO
chmod +x scripts/kb069_ingest_sample_finding.sh
./scripts/kb069_ingest_sample_finding.sh

# Validate
chmod +x scripts/kb069_validate_greenbone_control_plane_adapter.sh
./scripts/kb069_validate_greenbone_control_plane_adapter.sh
```

Admin UI: `http://192.168.0.201:3000/vulnerabilities`

---

## 5. Explicit deferrals

| Item | Later |
|---|---|
| Live GMP pull from VM 109 into sync API | **KB-070** (`scripts/kb070_pull_greenbone_findings.sh`) |
| Customer vulnerability list page | Not required — recommendations are the customer artifact |
| Authenticated scan credential vault UI | Future admin KB |

---

## 6. Validation

Expected final line:

```text
KB-069 GREENBONE CONTROL PLANE ADAPTER VALIDATION PASSED
```
