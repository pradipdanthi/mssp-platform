# KB-115 — NikTiar™ Secure Edge: Dedicated HA + Physical appliance

**Status:** Product default (2026-10-26). Shared multi-tenant edges are **not** a commercial offering.

---

## Product rule

Every customer gets a **dedicated** NikTiar Secure Edge for their organization only.

| Offering | When to use |
|---|---|
| **Dedicated HA pair (default)** | Customer has VMs / hypervisor / cloud VMs. Two nodes (active/standby or active/active VIP) for resilience. |
| **Physical appliance** | Customer has **no** virtual infra. Ship **1U** boxes (same Secure Edge stack) to the customer site. |

There is **no** shared edge that hosts multiple paying customers on one node.

---

## Environment (every node)

```bash
SECURE_EDGE_MODE=dedicated
NIKTIAR_TENANT_CODE=<CUSTOMER_SHORT_CODE>   # required — pins this appliance to one tenant
SECURE_EDGE_FORM_FACTOR=ha_pair             # or: physical
SECURE_EDGE_HA_ROLE=primary                 # primary | secondary (HA pair only)
SECURE_EDGE_HOSTNAME=edge-<tenant>-a        # unique per node
```

Dashboard top-left shows form factor labels such as **Dedicated · HA pair** or **Dedicated · Physical** — never “shared”.

---

## Dedicated HA pair (virtual)

1. Deploy the Secure Edge stack twice (node A + node B) with the **same** `NIKTIAR_TENANT_CODE`.
2. Put a VIP / load balancer in front for HTTP(S) 80/443 (and DNS 53 if using NikTiar DNS Filter).
3. Sync or independently manage zones via control plane; both nodes pull the same tenant sites.
4. Lab reference: VM 116 pattern — clone to a second VM for HA.

---

## Physical 1U appliance (customer site)

Same Docker Compose stack as the virtual edge, installed on a hardened Ubuntu appliance image (or future NikTiar Secure Edge ISO).

1. Rack two 1U units for HA when resilience is required (same as HA pair).
2. Cable WAN / LAN; set static IPs; point customer DNS (or NikTiar DNS Filter) as designed.
3. Register appliance to control plane with activation token + `NIKTIAR_TENANT_CODE`.
4. Operator uses appliance dashboard `:9080` for local NGFW/WAF/DNS policy; control plane Admin portal for fleet visibility.

Physical vs virtual differs only in **form factor and where it is racked** — not in product features.

---

## What “zones” mean on a dedicated edge

Multiple hostnames (zones) on one dedicated edge = **multiple sites for the same customer**, not multi-tenant sharing.

---

## Related

- Appliance UI / stack: `docs/KB114_NIKTIAR_SECURE_EDGE.md`
- Product names: `docs/NIKTIAR_PRODUCT_NAMES.md`
