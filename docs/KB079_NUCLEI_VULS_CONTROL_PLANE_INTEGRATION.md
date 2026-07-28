# KB-079 — Nuclei + Vuls control-plane integration (end-to-end)

Status: **Implementation** — scanners on VM 109; sync → Admin triage → customer-safe recommendations.  
Builds on: KB-069, KB-070, KB-078, KB-053, KB-076.

---

## 1. Purpose

Deliver **full MSSP vulnerability management** as a sellable service:

1. **Scan** (Nuclei + Vuls on VM 109, tenant-scoped targets)
2. **Normalize** → `POST /integrations/vuln/sync` (`source_platform`: `nuclei` | `vuls`)
3. **Admin/SOC** triage on **Vulnerabilities** page → promote to recommendations
4. **Customer** portal: entitlement gate + service summary (no raw scanner output)

Greenbone CE remains an optional additional source via KB-070.

---

## 2. Architecture

```
config/vuln_scan_targets.yml (tenant-scoped, no secrets)
  → VM 109: Nuclei / Vuls
  → scripts/kb079_* on control plane (pull + normalize + sync)
  → PostgreSQL vulnerabilities
  → Admin promote → customer_recommendations (customer_visible)
  → Customer Vulnerabilities tab + Recommendations
```

---

## 3. Configuration

| File | Role |
|---|---|
| `config/vuln_scan_targets.yml` | Per-tenant `nuclei_targets` and optional `vuls_servers` |
| `.secrets/vuln_sync_api_key` | Same key as KB-069/070 (never Git) |
| VM 109 `/opt/mssp-vuln-free/vuls/config.toml` | Vuls SSH scan config (host-local) |

Only add targets with **written customer scope approval**.

---

## 4. Operations (fully automatic)

**You do not run shell scripts** for normal scanning.

| Step | What happens |
|---|---|
| 1 | Customer has **Vulnerability Management** entitled (Add/Edit customer) |
| 2 | SOC adds **protected assets** (IP or hostname) in Admin → Assets |
| 3 | **VM 109 agent** (systemd timer, every 15 min) calls `GET /integrations/vuln/scan-plan` |
| 4 | Agent runs **Nuclei** on due tenants (weekly/monthly cadence) and **POST /integrations/vuln/sync** |
| 5 | Admin triages → promote → customer **Recommendations** |

**On-demand (Admin API, no scripts):**  
`POST /admin/vulnerabilities/request-scan/{short_code}` — queues that customer for the next agent cycle.

**One-time install (platform ops):**  
`./scripts/kb079_install_vuln_scan_agent_on_109.sh` and  
`./scripts/kb079_apply_vuln_scan_scheduler_migration.sh`

Legacy manual pull scripts (`kb079_pull_*.sh`) remain for break-glass debugging only.

---

## 5. APIs (previous §4)

| Endpoint | Audience | Purpose |
|---|---|---|
| `POST /integrations/vuln/sync` | Scanner workers | Ingest (keyed) |
| `GET /admin/vulnerabilities?source_platform=nuclei` | Admin/SOC | Triage |
| `GET /customer/vulnerabilities/{short_code}/summary` | Customer | Service status only |

Entitlement flag: `greenbone_enabled` / `greenbone_cadence` (product name: **Vulnerability Management**).

---

## 6. Customer safety

- No Nuclei/Vuls/Greenbone UI for customers
- No raw JSON, template dumps, or IPs in customer APIs
- Findings become visible only via **promoted** recommendations (`customer_visible=true`)

---

## 7. Validation

```bash
cd /opt/mssp-control
./scripts/kb079_validate_nuclei_vuls_integration.sh
```

---

## 8. Future: Pentest-as-a-service (portfolio — not in this KB)

Recommended approach when you are ready:

| Layer | Suggestion |
|---|---|
| **Product** | Separate entitlement `penetration_testing` (project-based, not continuous scan) |
| **Delivery** | Scoped engagements: external, internal, web app; report PDF + executive summary in portal |
| **Tooling** | Reuse Nuclei for automated checks; add **manual methodology** (OWASP WSTG / PTES) + optional Burp/Metasploit in isolated lab — never expose tools to customers |
| **Workflow** | Admin: create engagement → assign targets → import findings → customer deliverable report (KB-067 pattern) |
| **Legal** | Signed ROE + rules of engagement per customer before any testing |

We can draft **KB-080 Pentest service module** when Nuclei/Vuls continuous service is validated in production.
