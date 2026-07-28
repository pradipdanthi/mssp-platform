# KB-082 — All-Device SOC Alert Taxonomy (Admin)

Status: Implemented (additive, non-breaking).

## Goal

Categorize normalized `security_alerts` for SOC triage without changing core DB schema or breaking existing `/admin/alerts` consumers.

## Backend

- **Module:** `backend-api/app/services/soc_alert_taxonomy.py`
  - `derive_asset_category(alert_row)` — maps `source_tool`, Wazuh/Suricata/Zeek/Nuclei/Vuls/Greenbone metadata in `raw_event` to slugs such as `endpoints_windows`, `network_ids_sensors`, `vuln_infra_cve`.
  - Unknown → `uncategorized` (safe fallback).
  - `enrich_alert_row()` adds `asset_category`, `asset_category_label`, `device_type`, and optional contextual columns for API responses only.

- **API (additive):**
  - `GET /admin/alerts?asset_category=<slug>` — optional filter (applied after fetch window; default list unchanged when param omitted).
  - `GET /admin/alerts/taxonomy-summary` — per-slug counts for sidebar badges.
  - Alert detail triage route returns enriched fields.

Query param name is **`asset_category`** (not `category`) to match internal slug naming.

## Admin UI

- **Sidebar:** `AlertTaxonomyNav` on Alerts page — tree + count badges from taxonomy-summary.
- **URL:** `?category=<slug>` mirrors filter (maps to `asset_category` API param).
- **Columns:** Context-aware table headers per taxonomy mode (endpoints, network, vuln, etc.).
- **Default:** “All devices” — same flat feed as before.

Customer portal is **unchanged** (no engine names; no taxonomy nav).

## Zeek (VM 106 co-location)

Zeek is planned on **suricata-sensor** (`192.168.0.216`) alongside Suricata:

1. **Preferred:** Second capture NIC via Proxmox — `scripts/kb047_proxmox_add_zeek_capture_nic.sh` + guest `kb047_configure_zeek_capture_nic_vm106.sh`.
2. **Interim:** Shared mirror on `enp6s19` — `ZEEK_CAPTURE_IF=enp6s19 ./scripts/kb047_install_zeek_docker_vm106.sh`.
3. **Wazuh:** Ansible role `zeek_wazuh` — localfile for Zeek logs → same ingress as other agents.
4. **Taxonomy:** When `source_tool=zeek` or Zeek rule metadata is present, alerts map to **Network IDS / Sensors** (`network_ids_sensors`).

See `docs/KB047_ZEEK_COLOCATED_SURICATA_SENSOR.md` (if present) and playbook `ansible/playbooks/zeek-on-suricata-sensor.yml`.

## Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb082_validate_soc_alert_taxonomy.sh
./scripts/kb082_validate_soc_alert_taxonomy.sh
```

After deploy, as SOC user: open Admin → Alerts, select a category, confirm list loads; `/admin/alerts/taxonomy-summary` returns counts.

## Non-breaking guarantees

- No schema migrations required for KB-082.
- Existing alert list/detail fields preserved; enrichment is response-only.
- Missing metadata → `uncategorized`, not errors.
