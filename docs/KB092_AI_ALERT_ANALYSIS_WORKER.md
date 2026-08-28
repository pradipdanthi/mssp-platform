# KB-092 — AI Alert Analysis Worker

**Status:** IMPLEMENTED (Phase A MVP) — 2026-08-12  
**Provider (lab):** Local Ollama on **VM 115** `mssp-ai` (`192.168.0.227`) — model `qwen2.5:7b`

### VM 115 sizing (required for stable 7B)

| Resource | Minimum for `qwen2.5:7b` | Lab observed issue |
|----------|--------------------------|---------------------|
| **RAM** | **16 GiB** (32 GiB recommended) | **7.6 GiB** → runner evicted every request (~80–90s reload, 100% CPU spikes) |
| **vCPU** | 8 | OK at 8 cores with `taskset -c 0-5` + `num_thread=2` |
| **Swap** | 8 GiB emergency buffer | Added `/swapfile` — prevents OOM kill but **does not** replace RAM |

Proxmox: `qm set 115 --memory 16384` then reboot guest or `systemctl restart ollama`.

Systemd template: `scripts/mssp-ai/ollama.service.override.conf.example` + `ollama-warmup.sh`.  
**Brand context:** Supports “AI-ready” → “AI-assisted plain-English alerts” after live proof  

---

## 1. Why this exists

The control plane already had AI-named fields + KB-091 rule templates.  
KB-092 adds a real LLM worker that fills **empty / generic** customer-safe fields via an OpenAI-compatible endpoint (Ollama).

---

## 2. Runtime architecture

```
Alert ingest (soc_sync / appliance / telemetry→appliance)
        │
        ▼
  RPUSH mssp:ai:alert_analysis  { alert_id, tenant_id }
        │
        ▼
  Worker thread in mssp-backend-api (when AI_ALERT_ENABLED=true)
        │
        ├─ LOAD alert WHERE id AND tenant_id
        ├─ CALL Ollama http://192.168.0.227:11434/v1/chat/completions
        └─ UPDATE COALESCE empty columns only
```

**Precedence:** SOC/admin PATCH → AI fill → KB-091 templates → sync stub  

**Never** auto-sets `customer_visible`.

---

## 3. Config (`.env` → `docker-compose.yml` → backend-api)

| Variable | Lab value |
|---|---|
| `AI_ALERT_ENABLED` | `true` |
| `AI_ALERT_PROVIDER` | `openai_compatible` |
| `AI_ALERT_BASE_URL` | `http://192.168.0.227:11434/v1` |
| `AI_ALERT_API_KEY` | `ollama` (unused by Ollama; placeholder OK) |
| `AI_ALERT_MODEL` | `qwen2.5:7b` |
| `AI_ALERT_MIN_SEVERITY` | `high` |
| `AI_ALERT_TIMEOUT_SECONDS` | `90` |

Flag **defaults false** in Compose if unset.

---

## 4. Files

| Path | Role |
|---|---|
| `backend-api/app/services/ai_alert_analysis.py` | Prompt, LLM client, COALESCE persist |
| `backend-api/app/services/ai_alert_queue.py` | Redis queue + daemon worker |
| `backend-api/app/main.py` | Starts worker on API startup |
| `backend-api/app/services/soc_sync_service.py` | Enqueue after SOC sync |
| `backend-api/app/api/routes/appliance_alert_ingest.py` | Enqueue after new appliance alert |
| `docker-compose.yml` | Env passthrough |
| `scripts/kb092_validate_ai_alert_analysis_worker.sh` | Validator |

---

## 5. Validation

```bash
cd /opt/mssp-control
./scripts/kb092_validate_ai_alert_analysis_worker.sh
```

---

## 6. Marketing note

Keep website at **“AI-ready”** until a live high/critical alert shows AI-filled summary on Admin/Customer portals, then upgrade to **“AI-assisted plain-English alerts”**.
