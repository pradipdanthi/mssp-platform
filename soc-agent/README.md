# MSSP SOC Analyst Agent (Cursor subscription LLM)

Reduces human SOC effort with Tier-1/2 style triage. **Does not use lab Ollama** (that stays on control-plane Tier-1).

| | |
|---|---|
| VM | **117** `mssp-soc-agent` · `192.168.0.228` |
| Service | `mssp-soc-agent.service` (systemd + Cursor CLI) |
| Health | http://192.168.0.228:8443/health |
| Ingest | `POST http://192.168.0.228:8443/api/v1/ingest` |
| Auth | Header `X-Soc-Agent-Token` |

## One-time: Cursor API key

1. Cursor Dashboard → **Settings → API Keys** → create key  
2. On VM 117:

```bash
sudo nano /opt/soc-agent/.env
# set: CURSOR_API_KEY=...
sudo systemctl restart mssp-soc-agent
curl -fsS http://127.0.0.1:8443/health   # llm.cursor.available should be true
```

## Test

```bash
TOKEN=$(grep TOKEN= /opt/soc-agent/data/OPERATOR_TOKEN.txt | cut -d= -f2)  # or from control-plane copy
curl -fsS -X POST http://192.168.0.228:8443/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-Soc-Agent-Token: $TOKEN" \
  -d '{"alert_id":"TEST-001","title":"Suspicious PowerShell Execution with Encoded Payload","source_ip":"198.51.100.23","severity":"high"}'
```

See `docs/OBJECTIVE_AND_INTEGRATION.md`.
