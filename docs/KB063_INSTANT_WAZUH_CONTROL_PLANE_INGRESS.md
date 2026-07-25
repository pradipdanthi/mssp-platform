# KB-063 — Instant Wazuh → Control Plane Ingress (SLA path)

Status: **Live**  
Branch: `kb039-kb060-platform-roadmap-execution`

## Why

A 5-minute pull is too slow for SOC SLA. High-severity Wazuh alerts must appear on Admin dashboards **immediately**.

## New path

```text
Wazuh (level ≥ 10)
  → POST /integrations/soc/hooks/wazuh/{token}   (control plane, instant DB write)
  → background forward to Shuffle webhook         (TheHive ticket still created)
  → Admin Alerts/Incidents update within seconds
```

The old 5-minute TheHive pull timer remains as a **backup reconciler**, not the primary path.

## Security

- Ingress token is a path secret in gitignored `.secrets/wazuh_ingress_token`
- Wrong token → **404** (no enumeration)
- Shuffle webhook URL stored in `.secrets/shuffle_webhook_url` (not in Git)
- Customer visibility still defaults to **false** until SOC triage

## Proof (lab)

- Instant simulated ingress created incident `INC-DEMO-TH-0008`
- Live Wazuh rule 100049 posted to the new hook URL and created a high alert/incident in DEMO

## Operator notes

- Do **not** commit `.secrets/`
- Wazuh `ossec.conf` shuffle `hook_url` now points at the control-plane ingress URL
