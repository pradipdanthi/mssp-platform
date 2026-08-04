# svc-10 ITDR — AD/LDAP + identity API collectors

Modular Junexis appliance service. Enabled only when entitlement includes `svc-10` (except core SKU rules for svc-01).

## Layout (target)

- `systemd/` or Quadlet unit templates
- `container/` image reference + config
- `agent/` optional `agent.conf` fragments pushed via local Manager

See `docs/SERVICE_MATRIX.md` and KB-093.
