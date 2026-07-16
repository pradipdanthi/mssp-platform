# KB-057 — Customer-Safe Live SOC Data Integration

Status: Implemented (pending validation/commit).  
Module type: Backend integration foundation.

## Purpose

KB-057 adds the first live, tenant-scoped path from a registered appliance into
the control plane:

`POST /appliance/alerts`

The endpoint accepts normalized alert metadata only. It authenticates with the
same `X-Appliance-ID` and `X-Appliance-API-Key` headers as the KB-016 heartbeat,
derives `tenant_id` from the authenticated appliance, and inserts the alert into
`security_alerts`.

## Customer-safety boundary

The request model uses Pydantic `extra="forbid"`. Its only accepted fields are:

- `source_tool`
- `external_alert_id`
- `severity`
- `alert_title`
- `alert_description` (optional)
- `event_time` (optional)
- `destination_host` (optional)

The schema intentionally has no `tenant_id`, `appliance_id`, `customer_visible`,
`raw_event`, `raw_json`, `details`, IP fields, credentials, internal notes,
MITRE/AI internals, or arbitrary JSON. An appliance cannot choose its tenant or
make an alert visible to a customer.

Every new row is inserted with `customer_visible = false` and `status = new`.
Visibility remains off until an authorized admin/SOC triage action approves it
under the KB-056 workflow. Existing customer alert APIs continue to filter on
`customer_visible = true`.

## Authentication and isolation

- Missing or invalid appliance credentials return `401`.
- A correctly authenticated retired appliance returns `403`.
- `tenant_id` and `appliance_id` come only from the verified appliance row.
- No JWT or customer/admin identity is accepted on this appliance endpoint.
- Raw API keys are never stored or logged by this module.

## Duplicate protection

The duplicate identity is:

`(tenant_id, source_tool, external_alert_id)`

No PostgreSQL schema change is permitted in this KB. The route therefore takes
a transaction-scoped PostgreSQL advisory lock for that tuple, checks for an
existing row, and inserts only when none exists. A repeated submission returns
the original `alert_id` with `duplicate = true`; concurrent repeats are
serialized by the lock.

## Files

- `backend-api/app/schemas/alert_ingest.py`
- `backend-api/app/api/routes/appliance_alert_ingest.py`
- `backend-api/app/main.py`
- `scripts/kb057_validate_customer_safe_live_soc_data_integration.sh`
- `docs/KB057_CUSTOMER_SAFE_LIVE_SOC_DATA_INTEGRATION.md`

No `postgres/init/`, `.env`, or `docker-compose.yml` changes.

## Validation

```bash
cd /opt/mssp-control
./scripts/kb057_validate_customer_safe_live_soc_data_integration.sh
```

Expected final line:

```text
KB-057 CUSTOMER-SAFE LIVE SOC DATA INTEGRATION VALIDATION PASSED
```
