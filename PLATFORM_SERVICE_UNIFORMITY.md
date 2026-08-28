# Platform Service Uniformity

**Status:** U1–U4 + CUSTOM tier complete (2026-08-28). Full on-prem stack remains on roadmap.

## Principle

Customers buy **one subscription tier** (`SILVER` | `GOLD` | `PLATINUM`, or admin-only `CUSTOM`).  
**Deployment mode** only changes *where engines run* and *what crosses the network* — not what they purchased.

There is **no separate appliance product SKU**. NikTiar Edge is a deployment option for the same tiers.

---

## One commercial model, one entitlement row

```
subscription_tier  →  tenant_entitlements (Postgres flags)  →  fulfillment router
                                                              ├─ cloud control plane
                                                              └─ appliance local engines (if applicable)
```

| Layer | Purpose | Customer-visible? |
|-------|---------|-------------------|
| `subscription_tier` | Silver / Gold / Platinum bundle (or CUSTOM bespoke) | Yes |
| `tenant_entitlements` | Authoritative capability flags | No (drives portal + engines) |
| `svc-01` … `svc-10` | Appliance **engine IDs** (license JWS) | No — admin fleet diagnostics only |

Mapping flags → `svc-*`: `tenant_entitlement_defaults.entitlements_to_service_ids()`.

---

## Deployment modes (fulfillment target, not SKU)

| Mode | Log path | Alert path to MSSP | Detection engines |
|------|----------|-------------------|-------------------|
| `cloud` | Agents → cloud Wazuh | Cloud Wazuh | Cloud SOC VMs |
| `on_prem_direct` | Agents → cloud Wazuh | Cloud Wazuh | Cloud SOC VMs |
| `cloud_appliance` | Agents → local appliance Manager | Scrubbed high-fidelity alerts only (KB-093P) | Local + cloud as matrix below |
| `on_prem_appliance` | Agents → local appliance Manager | Scrubbed high-fidelity alerts only | Local engines when licensed |
| `hybrid` | Mix per site | Appliance path for edge sites | Both targets per capability rules |

**Future:** `on_prem_full_stack` (entire stack on customer site; onsite or VPN remote SOC) — same tiers and flags; fulfillment target becomes customer cluster. Prompt TBD.

---

## Always cloud (every deployment mode)

These never run as full stacks on the NikTiar Edge appliance:

| Component | Role |
|-----------|------|
| **TheHive** | Central case management — appliance `svc-02` executes signed jobs only |
| **Shuffle** | Central SOAR — appliance `svc-03` runs approved local actions only |
| **Customer portal** | Same modules / tier gates for all tenants |
| **Admin portal** | Tier ops, fleet view, SOC workflows |

---

## Capability fulfillment matrix

Each internal `service_key` maps to entitlement flags, optional appliance engine, and sync targets.

| Capability | Min tier | Entitlement flag(s) | Appliance engine | Cloud sync on appliance tenant |
|------------|----------|---------------------|------------------|--------------------------------|
| Log & event monitoring | SILVER | `wazuh_siem` | `svc-01` | N/A (local Manager) |
| Incident response | SILVER | `thehive_mode` | `svc-02` worker | TheHive org (cloud) |
| Cloud & identity (ITDR) | SILVER | `cloud_identity_protection_enabled` | `svc-10` | Cloud IdP graph bind |
| Security automation | GOLD | `shuffle_mode` | `svc-03` worker | Shuffle (cloud only) |
| Vulnerability management | GOLD | `greenbone_enabled` | `svc-04` | **Skip** — local scanner |
| External attack surface | GOLD | `external_attack_surface_enabled` | `svc-09` | **Skip** — local probes |
| Continuous compliance | PLATINUM | `continuous_compliance_enabled` | `svc-05` | **Skip** — local SCA |
| NDR | PLATINUM | `zeek_enabled` | `svc-06` | **Skip** — local NDR |
| Threat intelligence | PLATINUM | `misp_enabled` | `svc-07` | Cloud MISP feed (portal) |
| Forensics | PLATINUM | `velociraptor_enabled` | `svc-08` | **Skip** — local collector |

Code: `backend-api/app/services/capability_fulfillment_service.py`.

---

## Tier rollout flow (uniform)

1. Admin provisions tier (`POST /admin/tenants/tier-rollout`).
2. `set_tenant_subscription_tier()` → sync entitlement bundle from tier.
3. `fulfill_tenant_capabilities()`:
   - Clear per-asset module coverage (tier = all active assets).
   - For each included capability: run **cloud control-plane sync** unless appliance owns the engine locally.
   - If `deployment_mode` uses appliance: mint signed license from flags → `apply_entitlements` on all online appliances.

Appliance tenants receive **one license push** derived from the same flags — not a parallel `svc-*` SKU workflow.

---

## CUSTOM tier (admin-only bespoke bundle)

**Not a public SKU.** Provisioned via `POST /admin/tenants/custom-tier-provision` from Tier Operations.

| Aspect | Behavior |
|--------|----------|
| **Who can buy** | Admin-only; not on customer upgrade matrix |
| **Entitlements** | Per-module flags from selected `catalog_keys` — no `sync_entitlements_for_tier()` overwrite |
| **API gates** | Standard tiers: rank check. CUSTOM: entitlement flag for `catalog_key` |
| **Fulfillment** | Same `fulfill_tenant_capabilities()` router as Silver/Gold/Platinum |
| **Customer portal** | Shows contracted modules list; no tier upgrade CTAs |
| **Tier rollout** | `POST /admin/tenants/tier-rollout` rejects CUSTOM target — use custom provision |

Code: `backend-api/app/services/custom_tier_service.py`, `capability_access_service.py`.

---

## Customer portal parity

- Same `MODULE_MIN_TIER` gates for every deployment mode at the same tier.
- Same NikTiar module names (no vendor stack names on customer UX).
- Appliance tenants see the same Gold/Platinum modules; data may originate from local engines or forwarded alerts, but labels and tier matrix match cloud SOC tenants.

---

## Admin UX guidance

| Surface | Shows |
|---------|--------|
| **Tier Operations** | Silver / Gold / Platinum + **Provision custom tier** + capability reference pricing |
| **Tenant entitlements** | Flags; CUSTOM uses per-module flags without bundle sync |
| **Appliance fleet** | `svc-*` as **local engine status** on the box — not a second entitlement editor |

---

## Related docs

- `PRODUCT_TIER_SOURCE_OF_TRUTH.md` — tier bundles and flags
- `PHASE_0_TIER_ROLLOUT.md` — tier rollout automation
- `docs/KB073_TENANT_DEPLOYMENT_MODE.md` — deployment mode enum
- `docs/KB093G_APPLIANCE_ISO_ENTITLEMENT_PLAN.md` — appliance engine catalogue
- `docs/KB093P_APPLIANCE_CRITICAL_ALERT_FORWARD.md` — alert egress only

## Roadmap (after uniformity)

1. ~~**U3 — Portal parity**~~ — tier + entitlement flags; delivery label on Service Portfolio.
2. ~~**U4 — Admin UX**~~ — fleet `svc-*` badges use Tier Operations catalog names.
3. ~~**CUSTOM** (4th admin-only tier)~~ — pick flags on same matrix; same fulfillment router.
4. **Full on-prem stack** — new deployment mode; same tiers; fulfillment target = customer cluster.
