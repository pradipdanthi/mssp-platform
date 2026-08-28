# Platform Service Uniformity

**Status:** Canonical — Silver / Gold / Platinum delivery is identical across deployment modes.  
**Last updated:** 2026-08-28  
**Full reference:** `PLATFORM_SERVICE_UNIFORMITY.md`

## Commercial model

- Customers buy **one subscription tier** only: `SILVER`, `GOLD`, or `PLATINUM`.
- The legacy **10 capability modules** are **not separate SKUs** — internal ops labels mapped to the same entitlement flags on cloud and appliance.
- **Deployment mode** (cloud vs NikTiar Edge) changes where engines run, not what was purchased.
- Customer self-service: **tier upgrade requests** (`tier_gold`, `tier_platinum`).
- MSSP fulfillment: **set `subscription_tier`** → `sync_entitlements_for_tier()` → `fulfill_tier_capabilities()` (uniform router).

## Cloud-only components (all deployment modes)

- **TheHive** — central case management (appliance runs local IR worker only).
- **Shuffle** — central SOAR (appliance runs local automation worker only).
- **Customer / Admin portals** — same tier gates and module names everywhere.

## Tier definitions (customer-facing — NikTiar only)

| Tier | Positioning | Key capabilities |
|------|-------------|------------------|
| **Silver** | Cloud & Identity ITDR | NikTiar identity telemetry, MFA fatigue, impossible travel, Kerberoasting, portal MFA, 90-day retention |
| **Gold** | Core MDR | Everything in Silver + NikTiar Core EDR, automated host containment, Pre-LLM AI veto gate, NikTiar Aegis VM sync, NikTiar perimeter EASM sync |
| **Platinum** | Full MXDR | Everything in Gold + NikTiar DeepSight NDR, NikTiar Spectre DFIR, 90-day retrospective sweeps, NikTiar analytics OLAP & archival |

## Capability module → minimum tier

| `service_key` (internal) | Portal module | Min tier |
|--------------------------|---------------|----------|
| `log_event_monitoring` | Alerts / SIEM | SILVER |
| `incident_response` | Incidents / SOC cases | SILVER |
| `cloud_identity_protection` | ITDR | SILVER |
| `security_automation` | EDR containment | GOLD |
| `vulnerability_management` | Vulnerabilities | GOLD |
| `external_attack_surface` | Attack Surface (EASM) | GOLD |
| `continuous_compliance` | Compliance | PLATINUM |
| `network_detection_response` | NDR | PLATINUM |
| `threat_intelligence` | Threat Intel / ThreatLens | PLATINUM |
| `endpoint_forensics_deception` | Forensics | PLATINUM |

## Entitlement flags (`tenant_entitlements`)

| Flag | Silver | Gold | Platinum |
|------|--------|------|----------|
| `cloud_identity_protection_enabled` | ✓ | ✓ | ✓ |
| `wazuh_siem` | ✓ | ✓ | ✓ |
| `wazuh_retention_days` | 90 | 90 | 90 |
| `thehive_mode` | read_only | full | full |
| `shuffle_mode` | off | standard | standard |
| `greenbone_enabled` | — | ✓ | ✓ |
| `greenbone_cadence` | off | weekly | daily |
| `external_attack_surface_enabled` | — | ✓ | ✓ |
| `zeek_enabled` | — | — | ✓ |
| `misp_enabled` | — | — | ✓ |
| `velociraptor_enabled` | — | — | ✓ |
| `continuous_compliance_enabled` | — | — | ✓ |

Source: `backend-api/app/services/subscription_tier_service.py`

## Customer portal gating

- **Primary:** `subscription_tier` via `MODULE_MIN_TIER` in `frontend-customer/src/config/tierConfig.ts`
- Nav and `EntitlementGate` use tier only (not per-module boolean flags for customer UX).
- Service Portfolio: tier matrix + upgrade requests only.

## Admin portal

- **Tier Operations:** provision tier upgrades (`POST /admin/tenants/tier-rollout`).
- **Capability modules:** internal pricing and adoption counts (reference only).
- **Appliance fleet:** `svc-01`…`svc-10` shown as local engine status — not a separate SKU layer.
- **Advanced overrides:** collapsed entitlement toggles for MSSP exceptions (future CUSTOM tier).

## Request / provision workflow

```
Customer → tier upgrade request (tier_gold / tier_platinum)
       → service_consultation_requests (status pipeline)
Admin  → review in Service Requests
       → tier rollout (order # + confirmation email)
       → subscription_tier updated + entitlements synced
       → fulfill_tier_capabilities() (cloud adapters + appliance license from same flags)
```

## Retired

- **Bronze** tier — remove from all customer-facing copy.
- Per-service customer “Request for Consulting” as primary purchase path.
- Public vendor names (Wazuh, Suricata, Zeek, ClickHouse) on kevantic.com — use NikTiar branding only.

## Code references

| Concern | Location |
|---------|----------|
| Tier bundles | `subscription_tier_service.py` |
| Route enforcement | `tier_enforcement.py` — wired on ITDR, EDR, NDR, VMaaS, EASM, compliance, threat intel, forensics, Okta ingest |
| Tier rollout API | `tenant_management.py` → `POST /admin/tenants/tier-rollout` |
| Uniform fulfillment | `capability_fulfillment_service.py` |
| Appliance engine map | `tenant_entitlement_defaults.py` → `entitlements_to_service_ids()` |
| Demo tenant short codes | `subscription_tier_service.py` → `DEMO_TENANT_SHORT_CODES` |
| Catalog keys | `service_catalog.py`, `service_catalog_pricing.py` |
| Customer tier UI | `subscriptionTierMatrix.ts`, `SubscriptionTierMatrix.tsx` |
| Admin tier ops | `tierCapabilityMap.ts`, `TierRolloutPanel.tsx` |
| Capability → tier map | `tierCapabilityMap.ts` (admin + customer) |
