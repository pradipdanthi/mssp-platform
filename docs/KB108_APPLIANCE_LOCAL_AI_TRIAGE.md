# KB-108 — Appliance-local AI triage (Ollama edge filter)

Status: Implemented (v1) in `kevantic-appliance/` + optional control-plane ingest fields.  
Complements KB-093P critical-alert forwarder and control-plane Tier-1 (`ai_tier1_triage.py` on VM 115).

## Goal

Keep full logs on the appliance. Before forwarding high/critical alert metadata to
cloud SOC, optionally run a **local** LLM triage. Only escalate actionable /
non-benign alerts; high-confidence false positives stay local.

**Architecture decision:** Ollama belongs on the **appliance** (prod SKU ≥32GB /
8 cores). Control-plane chat/Tier-1 on mssp-ai (VM 115) remains unchanged.

## Hook point

```text
alerts.json
  → critical_alert_watcher.process_event()
      → level ≥ KEVANTIC_FORWARD_MIN_LEVEL (default 10)
      → local_ai_filter.classify()   # feature-flagged
      → hold  → audit SQLite, do NOT POST
      → forward → TelemetryForwarder → POST /api/v1/telemetry/ingest
```

Wazuh Manager ingest is **not** blocked — the forwarder is a separate process.
v1 triage is synchronous in the forwarder loop (60s timeout default); high/critical
volume is expected to be low.

## Fail policy

| Setting | Default | Behavior |
|---------|---------|----------|
| `ENABLE_LOCAL_AI_FILTER` | `false` | Filter off → forward as today |
| `LOCAL_AI_FAIL_OPEN` | `true` | On Ollama timeout/error → **forward** (never drop) |
| `LOCAL_AI_FAIL_OPEN=false` | — | On AI failure → **hold** (operator opt-in) |

### Forward / escalate when

- Verdict `MALICIOUS` or `SUSPICIOUS`
- Verdict not `BENIGN_FALSE_POSITIVE`
- Wazuh level ≥ 12 / severity critical (always forward, even if model says benign)
- Benign but confidence below `LOCAL_AI_SUPPRESS_CONFIDENCE` (default 85)
- AI failure and fail-open

### Hold (local only) when

- Verdict `BENIGN_FALSE_POSITIVE` **and** confidence ≥ 85
- Still retained in local Manager / datalake; audit row in SQLite
  `local_ai_triage_audit` inside the appliance metadata DB

## Env flags

| Env | Default | Notes |
|-----|---------|-------|
| `ENABLE_LOCAL_AI_FILTER` | `false` | Also `KEVANTIC_LOCAL_AI_FILTER_ENABLED` |
| `LOCAL_AI_FAIL_OPEN` | `true` | |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Localhost only |
| `LOCAL_AI_MODEL` | `qwen2.5:7b` | Pulled at golden bake |
| `LOCAL_AI_TIMEOUT_SECONDS` | `60` | Cap 180 |
| `OLLAMA_CPU_THREADS` | `4` (lab) / `6` (prod) | Also `LOCAL_AI_NUM_THREAD` |
| `OLLAMA_CORE_PINNING` | `0-5` | taskset mask for ollama serve |
| `OLLAMA_KEEP_ALIVE` | `-1` | Model resident in RAM |
| `LOCAL_AI_CACHE_ENABLED` | `true` | Skip redundant Ollama calls |
| `LOCAL_AI_CACHE_TTL_SECONDS` | `86400` | Cache TTL |
| `LOCAL_AI_SUPPRESS_CONFIDENCE` | `85` | Benign hold threshold |

Set via `/etc/kevantic/appliance.env` (or `/etc/niktiar/appliance.env`) and/or
systemd unit `Environment=` lines on `kevantic-critical-alert-forwarder.service`.

## Files

| Piece | Path |
|-------|------|
| Filter | `appliance/telemetry/local_ai_filter.py` |
| Hook | `appliance/telemetry/critical_alert_watcher.py` |
| Cloud payload AI fields | `appliance/common/privacy.py` (`raw_event.appliance_ai` + optional top-level) |
| Ollama unit | `configs/systemd/ollama.service` + `ollama.service.d/override.conf` |
| Install | `scripts/install_appliance_ollama.sh` |
| Model pull | `scripts/pull_local_ai_model.sh` |
| Lab enable | `scripts/enable_local_ai_filter_on_appliance.sh` |
| Golden bake | `scripts/bake_golden_vm199_fleet_reporting.sh` |
| Ingest schema | `backend-api/app/schemas/alert_ingest.py` (optional fields) |

## Ollama hardening (appliance)

Unlike mssp-ai (binds `0.0.0.0:11434` on the lab LAN):

- `OLLAMA_HOST=127.0.0.1:11434` — **not** exposed to WAN/LAN
- **CPU pinning:** `ollama-serve-pinned.sh` runs `taskset -c ${OLLAMA_CORE_PINNING}` (default `0-5`)
- **Thread budget:** `OLLAMA_CPU_THREADS` (lab **4**, prod **6**); mirrored as `LOCAL_AI_NUM_THREAD`
- `OLLAMA_NUM_PARALLEL=1`, `MAX_LOADED_MODELS=1`, `KEEP_ALIVE=-1` (model stays resident — avoids reload CPU spikes)
- Profile file: `/etc/kevantic/ollama.env` (set `KEVANTIC_APPLIANCE_PROFILE=prod` before install for prod defaults)
- **Inference cache:** SQLite `local_ai_triage_cache` dedupes identical telemetry (default TTL 24h)
- Bake asserts no `0.0.0.0:11434` listener

Disk: model `qwen2.5:7b` ≈ **4.7 GB** under `/usr/share/ollama`.

## Enable on lab appliance 210 (or Beta 226)

```bash
cd /opt/mssp-control
./kevantic-appliance/scripts/enable_local_ai_filter_on_appliance.sh junexis@192.168.0.226
# or packer@… depending on SSH user
```

Requires ≥16GB RAM recommended for pull/load; prod SKU ≥32GB.

Manual:

```bash
# on appliance
sudo bash /usr/local/sbin/install_appliance_ollama.sh
sudo bash /usr/local/sbin/pull_local_ai_model.sh
# in /etc/kevantic/appliance.env:
ENABLE_LOCAL_AI_FILTER=true
LOCAL_AI_FAIL_OPEN=true
sudo systemctl restart kevantic-critical-alert-forwarder
```

## Control plane

Optional ingest fields (absent = OK, no break):

- `appliance_ai_verdict`, `appliance_ai_confidence`, `appliance_ai_summary`
- Also nested under `raw_event.appliance_ai`

VM 115 / control-plane Tier-1 is **not** removed.

## Known limits (v1)

- No VirusTotal / TI enrichment on appliance (cloud Tier-1 still richer)
- Sync triage in forwarder loop (not a separate async queue yet)
- Golden lab VM may restore to 8GB after bake; enable filter only on ≥16–32GB clones
- Filter default **off** on golden; enable per site via env
