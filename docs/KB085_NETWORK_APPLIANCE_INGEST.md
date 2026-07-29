# Network appliance syslog → control plane (KB-085)

Goal: accept firewall/switch syslog (pfSense / VyOS / FortiGate) as
`network_appliance` alerts without binding to an endpoint agent id.

## Ingest conventions

When forwarding through Wazuh or direct SOC sync, set:

- `source_tool`: `network_appliance` (preferred), or leave decoder-based detection
- Do **not** require `agent.id` for tenant mapping when using tenant group tags /
  `tenant_short_code` on the sync payload
- Include vendor markers in message/rule groups (`fortigate`, `pfsense`, `vyos`,
  `filterlog`) so taxonomy maps to:
  - `asset_category` = `security_edge_appliances`
  - `device_type` = `network_appliance`

## Suricata / Zeek

Continue to use `source_tool` = `suricata` / `zeek` → `network_ids_sensors`.

## Example SOC sync fragment

```json
{
  "tenant_short_code": "BETALINUX",
  "source_tool": "network_appliance",
  "alert_title": "Firewall block",
  "raw_event": {
    "decoder": { "name": "fortigate-firewall" },
    "data": { "action": "deny", "srcip": "10.0.0.5", "dstip": "8.8.8.8" }
  }
}
```
