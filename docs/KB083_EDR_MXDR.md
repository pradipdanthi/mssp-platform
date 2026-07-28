# KB-083 — EDR & MXDR platform wiring

Status: Implemented (additive).

## Approved policy (owner, 2026-07-28)

| Topic | Decision |
|--------|-----------|
| **Containment RBAC** | **Co-managed:** `customer_admin` may `ISOLATE_HOST` / `KILL_PROCESS` / `COLLECT_FORENSICS` / `BLOCK_HASH` within their tenant. `customer_viewer` read-only. SOC (`platform_admin`, `soc_manager`) may act on any tenant; `soc_analyst` can view telemetry (execute: platform_admin + soc_manager on admin UI). |
| **Forensics** | **Hybrid:** `COLLECT_FORENSICS` → Shuffle webhook with workflow name `EDR_SHUFFLE_FORENSICS_WORKFLOW` (default `EDR_COLLECT_FORENSICS`). Offline collector via Shuffle until `VELOCIRAPTOR_SERVER_URL` is set (VM 110). |

## API (browser path `/api/v1/edr/...`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/edr/telemetry/process-tree` | Sysmon / Osquery process tree |
| GET | `/v1/edr/incidents/deep-dive` | Endpoint card + MITRE + tree + recent actions |
| POST | `/v1/edr/actions/execute` | Containment / forensics |
| GET | `/v1/edr/actions/{id}` | Action status |
| GET | `/v1/edr/metrics/summary` | MTTC, telemetry rate, isolated count |

## Database

`postgres/init/014_kb083_edr_actions.sql` — `edr_action_executions`, `edr_endpoint_isolation`, `edr_telemetry_stats`.

Live apply: `./scripts/kb083_apply_edr_migration.sh`

## Ingress

Wazuh instant hook now persists `raw_event` + `mitre_mapping` on `security_alerts` (KB-083 enrichment).

## Env (optional)

- `EDR_SHUFFLE_FORENSICS_WORKFLOW` — Shuffle workflow for triage / offline collector
- `VELOCIRAPTOR_SERVER_URL` — future direct server routing
- Existing `SHUFFLE_WEBHOOK_URL` / `.secrets/shuffle_webhook_url`

## Validate

```bash
cd /opt/mssp-control
./scripts/kb083_validate_edr_mxdr.sh
```

## Ops note

Wazuh **active-response** command names (`firewall-drop`, custom kill/hash) must exist on the Manager for live isolation/kill to succeed; failures are logged and returned as `failed` on the action record.
