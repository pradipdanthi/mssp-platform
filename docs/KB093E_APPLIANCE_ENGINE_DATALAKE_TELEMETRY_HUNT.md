# KB-093E — Junexis Edge Appliance Engine (DuckDB/Parquet + Telemetry + Hunt)

Status: Implemented on appliance tree + thin control-plane ingest routes.  
Extends KB-093 B1/B2. Prompt was truncated after hunt payload; completed with result callback contract below.

## What this adds

| Module | Path | Role |
|--------|------|------|
| A — Archiver | `junexis-appliance/appliance/datalake/archiver.py` | Wazuh/Zeek/Suricata JSON → daily ZSTD Parquet under `/var/log/junexis/datalake/YYYY/MM/DD/` + SQLite metadata |
| A — Query | `junexis-appliance/appliance/datalake/query_engine.py` | DuckDB search by IP / domain / hash / CVE |
| B — Forwarder | `junexis-appliance/appliance/telemetry/forwarder.py` | Anonymize + POST `/api/v1/telemetry/ingest`; SQLite buffer + exponential backoff |
| C — Hunter | `junexis-appliance/appliance/hunting/retrospective_sweeper.py` | Local retrospective IOC hunt |
| C — API | `junexis-appliance/appliance/api/local_app.py` | `POST /appliance/v1/jobs/retrospective-hunt` (loopback by default) |

Metadata DB: `/var/lib/junexis/appliance_local.db`

## Hunt job contract

**Request** `POST /appliance/v1/jobs/retrospective-hunt`

```json
{
  "job_id": "job_123",
  "iocs": ["192.168.1.50", "d41d8cd98f00b204e9800998ecf8427e", "CVE-2026-1234"],
  "lookback_days": 90
}
```

**Callback** `POST https://api.junexis.com/api/v1/telemetry/hunt-results`  
(Headers: `X-Appliance-ID`, `X-Appliance-API-Key`) — metadata hits only, no raw logs.

## Cloud ingest

`POST https://api.junexis.com/api/v1/telemetry/ingest`  
Implemented on control plane as alias into KB-057 safe alert ingest (same field forbid list). **Production:** move to Appliance Management plane (KB-093 §12).

## Privacy

`appliance/common/privacy.py` redacts passwords, tokens, email bodies, raw_event, and strips IPs from cloud-bound payloads (KB-057 alignment).

## Validate

```bash
cd /opt/mssp-control
./scripts/kb093e_validate_appliance_engine.sh
```

## Run local job API (dev)

```bash
cd /opt/mssp-control/junexis-appliance
export PYTHONPATH=$PWD
export JUNEXIS_STATE_DIR=/tmp/jx-engine JUNEXIS_LOG_DIR=/tmp/jx-logs
python3 -m appliance.api.local_app
```
