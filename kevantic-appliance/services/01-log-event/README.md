# svc-01 Log & Event Monitoring — Wazuh Manager + Fluent Bit + collectors

Modular Kevantic appliance service. Enabled only when entitlement includes `svc-01` (except core SKU rules for svc-01).

Agents enroll to this **local Manager** only. High/critical metadata is forwarded to
cloud SOC by `kevantic-critical-alert-forwarder` (KB-093P) — raw logs stay on-prem.

## Layout (target)

- `systemd/` or Quadlet unit templates
- `container/` image reference + config
- `agent/` optional `agent.conf` fragments pushed via local Manager

See `docs/SERVICE_MATRIX.md`, KB-093, and KB-093P.
