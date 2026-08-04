# svc-09 EASM — internal perimeter probes

Modular Junexis appliance service. Enabled only when entitlement includes `svc-09` (except core SKU rules for svc-01).

## Layout (target)

- `systemd/` or Quadlet unit templates
- `container/` image reference + config
- `agent/` optional `agent.conf` fragments pushed via local Manager

See `docs/SERVICE_MATRIX.md` and KB-093.
