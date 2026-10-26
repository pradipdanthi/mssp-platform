# NikTiar™ Secure Edge

Self-hosted **NikTiar WAF + NikTiar Firewall (NGFW) + DNS Filter + Bot Defense**.

**Product default:** **Dedicated** per customer — **HA pair** (virtual) or **physical 1U** at the customer site. Shared multi-tenant edges are **not** offered.

**Product names (UI):** see `/opt/mssp-control/docs/NIKTIAR_PRODUCT_NAMES.md` — never expose upstream package brands in dashboards or portals.

**Lab:** VM 116 · dashboard `http://192.168.0.217:9080/`

| Env | Meaning |
|---|---|
| `SECURE_EDGE_MODE=dedicated` | Always (default). `shared` is coerced to dedicated. |
| `SECURE_EDGE_FORM_FACTOR=ha_pair` \| `physical` | Virtual HA pair vs physical appliance |
| `NIKTIAR_TENANT_CODE` | Pins this node to one customer |

## Quick deploy

```bash
cd docker
cp .env.example .env   # set NIKTIAR_TENANT_CODE + form factor
docker compose build dashboard agent dns-feed-sync
docker compose up -d
```

- Runbook: `docs/KB114_NIKTIAR_SECURE_EDGE.md`
- Dedicated HA + physical: `docs/KB115_SECURE_EDGE_DEDICATED_HA_PHYSICAL.md`
