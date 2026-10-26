# KB-117 — Enterprise SOC Agent Integration

**Status:** Implemented (lab)  
**VM:** 117 `mssp-soc-agent` `192.168.0.228:8443`  
**Goal:** Cursor subscription LLM acts as expert deep triage + action *proposal* brain without duplicating Admin/Customer portals or auto-executing containment.

## Architecture

1. Existing ingest (Wazuh/appliance/ITDR/Secure Edge) → `security_alerts` → Redis `ai_alert_queue`.
2. Pipeline: KB-092 explain (Ollama) → KB-096 SOC assist (Ollama) → **deep/expert**.
3. When `SOC_AGENT_ENABLED=1`, deep stage calls VM 117 first; Ollama `run_tier1_triage` is fallback only.
4. Agent may also `POST /api/v1/soc-agent/triage-result` (callback) with the same token.
5. Results land in existing `ai_*` columns; optional draft `customer_recommendations` (`category=soc_agent`, `customer_visible=false`).
6. Escalation reuses KB-116 `decide_escalation` → `soc_notifier`. **Never auto-ISOLATE / auto-ITDR.**

## Control plane env (VM 100 `.env`)

```bash
SOC_AGENT_ENABLED=true
SOC_AGENT_URL=http://192.168.0.228:8443
SOC_AGENT_TOKEN=<same as agent SOC_AGENT_INGEST_TOKEN>
SOC_AGENT_CALLBACK_TOKEN=<optional; defaults to SOC_AGENT_TOKEN>
SOC_AGENT_TIMEOUT_SECONDS=90
SOC_AGENT_MIN_SEVERITY=medium
# Keep AI_DEEP_TRIAGE_ENABLED=true for Ollama fallback when agent is down
```

## Agent env (VM 117 `/opt/soc-agent/.env`)

```bash
CURSOR_API_KEY=<cursor dashboard key>
SOC_AGENT_INGEST_TOKEN=<shared secret>
MSSP_CALLBACK_URL=http://192.168.0.201:8000
MSSP_CALLBACK_TOKEN=<same as SOC_AGENT_TOKEN on control plane>
```

## Fan-in coverage

| Source | Path |
|--------|------|
| Wazuh / TheHive sync | Existing `enqueue_ai_alert_analysis` |
| Appliance telemetry | Existing enqueue |
| ITDR Okta/AD | Enqueue after alert create |
| Secure Edge high/block | Promote to `security_alerts` (`source_tool=secure_edge`) + enqueue |

## Safety

- Feature flags default off until env set.
- Agent/network failures never break ingest (soft-fail).
- Containment remains human/SOAR via Admin EDR + ITDR remediate APIs.
- No new portal UI; no schema migrations.

## Validate

```bash
cd /opt/mssp-control
python3 -m unittest backend-api.tests.test_soc_agent_integration -v
python3 scripts/verify_platform_state.py
./scripts/production_deploy_control_plane.sh
./scripts/run_post_change_checks.sh
```
