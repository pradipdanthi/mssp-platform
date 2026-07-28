# KB-084 — EDR Lifecycle, Forensics Storage, Process Trees, Endpoint Configs

Status: Implemented (control plane).  
Date: 2026-07-28

## Goals

Close operational gaps after KB-083:

1. Action execution feedback loop (`PENDING` → `EXECUTING` → `SUCCESS`/`FAILED` → `VERIFIED`)
2. Large forensic package direct upload (presigned URL; not through SOAR webhook body)
3. Richer process-tree normalization (Sysmon / Osquery / Auditd + GUID/PID fallback)
4. Standardized endpoint config templates + admin download API

## API additions

| Method | Path | Auth |
|--------|------|------|
| POST | `/v1/edr/actions/callback` | `X-EDR-Callback-Key` or `X-SOC-Sync-Key` |
| PUT | `/v1/edr/forensics/upload/{artifact_id}?token=` | HMAC token |
| GET | `/v1/edr/forensics/download/{artifact_id}?token=` | HMAC token |
| POST | `/v1/edr/forensics/complete` | callback key |
| GET | `/admin/onboarding/agent-configs/{os_type}` | JWT admin/SOC/customer_admin |

`POST /v1/edr/actions/execute` now supports `UNISOLATE_HOST` and returns lifecycle statuses (`executing`, `success`, `failed`, `verified`). Legacy `executed` is normalized to `success` in responses.

## Forensics storage

Default backend: **local object store** under `EDR_FORENSICS_STORAGE_PATH` (default `/var/lib/mssp/forensics`) with tenant-partitioned keys:

`{tenant_id}/{endpoint_id}/{timestamp}_{artifact_id}.zip`

When `COLLECT_FORENSICS` runs, the control plane:

1. Creates `edr_forensic_artifacts` row
2. Issues time-limited upload URL in the Shuffle trigger payload
3. Agent/collector PUTs the ZIP directly
4. Optional `forensics/complete` callback attaches size/SHA256 metadata
5. UI shows a time-limited download URL (no binary proxy through list APIs)

Optional future: set `EDR_S3_BUCKET` (+ credentials) for MinIO/S3; architecture keys stay identical.

## Process trees

Ingest enrichment writes `edr_process_events`. Tree builder prefers `ProcessGuid` lineage, then `ParentProcessId` correlation. UI shows signed/unsigned hints, command lines, and MITRE tags. Customer UI never names third-party engines.

## Templates

Repo path: `templates/endpoint-configs/`

- `sysmon-windows-baseline.xml`
- `osquery-endpoint-pack.conf`
- `wazuh-agent-parameters.conf`

Copied into the API image at `backend-api/app/endpoint_configs/`.

## Migration

```bash
./scripts/kb084_apply_edr_lifecycle_migration.sh
```

## Validation

```bash
./scripts/kb084_validate_edr_lifecycle_gaps.sh
```

## UI

Admin + Customer EDR panels: status badges (Executing… / Isolated / Failed / Restored), Un-isolate, Retry, forensic download links.
