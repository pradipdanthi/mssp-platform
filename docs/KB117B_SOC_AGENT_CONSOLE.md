# KB-117b — SOC Agent Console (dedicated dashboard)

**URL (lab):** http://192.168.0.201:3002  
**URL for microphone/voice (HTTPS):** https://192.168.0.201:3443 — browsers block mic on plain HTTP LAN IPs.  
**Theme:** red / white  
**Auth:** same Admin/SOC JWT (`platform_admin`, `soc_manager`, `soc_analyst`)

TLS certs: `frontend-soc/certs/` (regenerate with `./scripts/soc_console_gen_tls.sh`).

### Microphone (push-to-talk)

Chrome’s built-in speech API often fails on lab self-signed HTTPS. Tia uses **push-to-talk**: browser records WAV → `POST /admin/soc-console/stt` → server transcription.

1. Open https://192.168.0.201:3443/ (Advanced → Proceed if asked).
2. Click **Mic** → when Chrome asks, choose **Allow**.
3. Speak, then click **Stop** (auto-stops after 15s). Text is filled and sent when auto-send is on.
4. If Chrome never asks / still blocked: address-bar **Not secure** → Site settings → Microphone → **Allow**, and Windows **Settings → Privacy → Microphone** allow Chrome.
5. Optional trust: download `/soc-lab.crt` and install into Trusted Root so the red “Not secure” badge clears.

## Purpose

A focused SOC workstation — not a second Admin portal.

**Ops layout (SOC workstation):**

- Top tiles: Security Alerts · Incidents · Events · Vulnerabilities · Patch Gaps · **Customers**
- **Alerts / Incidents** — full Admin-parity triage + EDR Isolate (`scripts/sync_soc_admin_parity.sh`)
- **Vulnerabilities** — scanner CVEs (Nuclei/Vuls/Greenbone). **Patch Gaps** — failed SCA/hardening checks (`/admin/compliance/patch-gaps`). **Events** — Secure Edge console.
- **Customers** → **Open here** / **Open on monitor** → standalone `/monitor/:shortCode` (alerts+incidents+vulns+patch only; no Tia / no global feed). Login shared via `localStorage`.
- Home: **Tia** chat (left) + **Active live feed** (right)
- Voice: Tia speaks replies only after mic push-to-talk (typed chat stays silent)

Re-sync after Admin triage/EDR UI changes:

```bash
./scripts/sync_soc_admin_parity.sh
docker compose build frontend-soc && docker compose up -d frontend-soc
```

## Tia (SOC agent)

- Persona + briefing facts: critical/high while away, FPs closed, incidents, customer notifications, AI triage actions
- Can update tickets when the analyst asks (alert status / incident status / internal comment) via `<<<TIA_ACTIONS>>>` blocks — audited
- Voice: browser picks the most natural English female voice; optional neural TTS with `TIA_TTS_ENABLED=true` + `TIA_TTS_API_KEY`

## Activity stream

| Endpoint | Role |
|----------|------|
| `GET /admin/soc-console/activity` | Snapshot |
| `GET /admin/soc-console/activity/stream` | SSE (Bearer JWT) + periodic `stack` events |
| `GET /admin/soc-console/stack` | KPI / stack pulse JSON |
| `GET /admin/soc-console/engines` | Engine wall (VM probes + per-tool streams) |
| `GET /admin/soc-console/queue` | Alert/incident queue |

Feed sources: `security_alerts`, `incidents`, `secure_edge_events`, `appliance_heartbeats`, `notification_events`, `audit_logs`, `customer_recommendations`, AI triage markers, plus in-memory console chat markers.

## Backend

| Endpoint | Role |
|----------|------|
| `GET /admin/soc-console/overview` | KPI strip |
| `GET /admin/soc-console/status` | Cursor chat readiness |
| `POST /admin/soc-console/chat` | Chat → SOC agent `/api/v1/chat` (Cursor) |
| Existing `/admin/alerts`, `/admin/incidents`, `/admin/secure-edge/events` | Lists |

Requires `SOC_AGENT_ENABLED=true` + `SOC_AGENT_TOKEN` (same as KB-117).

## Deploy

```bash
cd /opt/mssp-control
./scripts/production_deploy_control_plane.sh
# Sync agent chat endpoint to VM 117, then:
# curl -fsS http://192.168.0.201:3002/
```
