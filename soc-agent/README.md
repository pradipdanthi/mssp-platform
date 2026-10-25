# MSSP SOC Analyst Agent

Autonomous alert ingestion → enrichment → triage → escalation dossiers.

| Item | Value |
|---|---|
| Lab VM | **117** `mssp-soc-agent` |
| IP | `192.168.0.228` |
| Webhook | `http://192.168.0.228:8088/api/v1/ingest` |
| Health | `http://192.168.0.228:8088/health` |
| Auth | Header `X-Soc-Agent-Token` |

Deploy path on VM: `/opt/soc-agent`.
