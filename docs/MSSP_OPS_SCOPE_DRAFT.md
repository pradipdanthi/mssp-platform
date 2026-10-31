# MSSP operating scope draft (evidence-based)

Date: 2026-10-30 · Lab control plane `192.168.0.201`  
This is **not** a staffing contract, SLA, or compliance certificate.

## What the platform can do today (technical)

| Capability | Evidence |
|---|---|
| Admin / Customer / SOC portals + shared API auth | HTTP 200 homes; bad login 401 on API and nginx proxies |
| Tenant isolation on customer APIs | Wrong-tenant list/detail → **404 Tenant not found** (BETA viewer vs ALPHA) |
| Wazuh manager → control-plane ingress | `custom-mssp-ingress` → alert + incident on ALPHA; TLS verify with pinned CA |
| Human incident path (no TIA) | Assign, comment, ownership_state/age_hours on admin+SOC lists |
| Escalation queue semantics | `queued → sent (local_file_sink) → acknowledged`; WhatsApp still unconfigured |
| Encrypted backup restore (isolated) | Decrypt `MSSP_FULL_STACK_BACKUP_*.sql.gz.enc` → temp Postgres; 3 tenants; **524** alerts in backup vs **3** live after wipe |
| TIA typed assist | Greetings; customer counts (0 jobs); criticality vs stored severity |

## Responsibility matrix (solo builder — aspirational roles)

| Function | Who today | Notes |
|---|---|---|
| Detection eng / platform | Owner | Engines on Proxmox; no 24/7 coverage claimed |
| SOC triage | Owner | Human path works without TIA/LLM |
| Customer onboarding | Owner | Lab tenants only; commercial onboarding on hold |
| On-call paging | **Unstaffed** | No WhatsApp recipients; local sink ≠ real-world page |
| Backup operator | Automated timer 20:00 + owner | Restore drill done isolated; live overwrite never tested here |

## Explicit non-claims

- Staffed 24/7 response
- Autonomous containment / auto-close of customer cases
- Physical microphone voice acceptance
- Production WhatsApp delivery
- Windows endpoint live AR callback with the **new** dedicated EDR key (fleet publish awaiting operator approval)
