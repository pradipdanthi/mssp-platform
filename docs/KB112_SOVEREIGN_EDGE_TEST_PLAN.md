# KB-112 — NikTiar Sovereign Edge (Air-Gapped SOC) — Test Plan

**Status:** Foundation (step 1 of phased delivery).  
**Marketing name:** NikTiar Sovereign Edge — The Air-Gapped SOC.  
**Parent:** `PLATFORM_SERVICE_UNIFORMITY.md` (`sovereign_edge` deployment mode).

---

## 1. Product summary

Sovereign Edge extends the VM199 / NikTiar Edge appliance lineage:

| Aspect | Hybrid Edge (`on_prem_appliance`) | Sovereign Edge (`sovereign_edge`) |
|--------|-----------------------------------|-----------------------------------|
| Local ingestion & engines | Yes | Yes — full stack on-box |
| TheHive / Shuffle / unified portal | Cloud | **Local cluster** |
| Default cloud egress | Selected critical alerts | **None** |
| Optional cloud egress | Always on for mode | **Toggle** (SOC engineer only) |
| Cloud fleet visibility | Yes | **No** |
| License delivery | Channel `apply_entitlements` | **Offline JWS** — MSSP generates, engineer applies onsite |
| Tier upgrade | Portal request → cloud fulfillment | **Email → license file → engineer apply** |
| HA | Single node typical | **2-node active–active**, no shared SAN |
| Customer access | Cloud customer portal | **On-box dashboard only** (no admin, no appliance shell) |

Same subscription tiers (Silver / Gold / Platinum / CUSTOM). Deployment mode changes *where* components run and *what crosses the network*.

---

## 2. Resource-light test strategy (no extra Proxmox VMs)

We validate in **layers** on hardware already available:

| Layer | Where | New VMs? |
|-------|-------|----------|
| L0 — Mode helpers & RBAC contracts | CI / `pytest` | No |
| L1 — Single sovereign profile on Beta `.226` | Existing appliance | No |
| L2 — Air-gap (firewall block cloud `.201`) | Beta | No |
| L3 — Offline license apply | Beta + cloud license mint only | No |
| L4 — Dual logical nodes on **one** host | Beta (`sovereign-a` / `sovereign-b` instances) | No |
| L5 — Real 2-VM HA failover | Ephemeral clone VMs 221/222 | **Validated** (KB-115) |

---

## 3. Phase 1 — Foundation (this KB module)

### 3.1 Automated (CI / local)

- `backend-api/tests/test_sovereign_edge.py` — deployment mode helpers.
- `scripts/kb112_validate_sovereign_edge_foundation.sh` — schema, service module, admin UI option.
- RBAC matrix tests (next step): customer roles must not reach `/admin/*` on unified on-box API.

### 3.2 Acceptance criteria — mode & fulfillment

| Check | Expected |
|-------|----------|
| `deployment_mode = sovereign_edge` in DB constraint | Allowed |
| `is_sovereign_edge()` | True only for `sovereign_edge` |
| `cloud_fleet_visible()` | False for sovereign |
| `default_cloud_egress_enabled()` | False for sovereign |
| `offline_license_delivery()` | True for sovereign |
| Tier rollout cloud adapter sync | **Skipped** (local-only fulfillment) |
| Tier rollout appliance channel push | **Skipped** — `offline_license_manual` |
| Customer delivery label | Mentions Sovereign Edge / air-gapped |

---

## 4. Phase 2 — Single-node sovereign on Beta (no new VM)

**Host:** `192.168.0.226` (Beta) or VM199 when powered for bake.

1. Install full stack profile (TheHive, Shuffle, unified API/UI) — future bake step.
2. Set tenant `deployment_mode = sovereign_edge` in admin (lab tenant only).
3. **Air-gap:** `iptables` / `ufw` block outbound to cloud control plane except during egress-toggle test.
4. **Offline license:** mint JWS on cloud → SCP to appliance → `kevantic-cli license apply`.
5. **Renewal reminder:** short `exp` in test license → on-box banner; customer cannot apply license in UI.
6. **Egress toggle:** SOC engineer enables → fire critical alert → verify cloud receives (dedicated test window) → disable.

Validator (future): `scripts/kb112_validate_sovereign_single_node.sh`.

---

## 5. Phase 3 — RBAC unified dashboard

One origin (e.g. `https://<appliance-vip>/`), two personas:

| Test | SOC engineer | Customer |
|------|--------------|----------|
| Login | Full admin nav | Dashboard only |
| `GET /admin/tenants` | 200 | **403** |
| `GET /customer/incidents` | 200 | 200 |
| Direct URL `/admin/...` as customer | — | Redirect / 403 |
| SSH / `kevantic-cli` as customer OS user | — | Denied |
| License apply UI | Engineer only | Hidden / 403 |

Automate with `test_sovereign_rbac.py` + optional Playwright on Beta.

---

## 6. Phase 4 — Active–active on one host (logical cluster)

Simulate two nodes without a second Proxmox VM:

```
Beta host
├── sovereign-a  NIKTIAR_STATE_DIR=/var/lib/niktiar-a  API :8443
├── sovereign-b  NIKTIAR_STATE_DIR=/var/lib/niktiar-b  API :8444
└── VIP / keepalived on loopback for failover drill
```

Tests:

1. Pair/join bootstrap.
2. Write on A → readable on B within SLA.
3. `systemctl stop sovereign-a` → health on VIP passes.
4. Split-brain guard (network partition simulation via `iptables` drop between ports).

Validator: `scripts/kb113_validate_sovereign_ha_failover.sh`.

**Not claimed without 2 real nodes:** disk failure, rack redundancy, WAN partition latency.

---

## 7. Phase 5 — Ephemeral 2-VM HA sign-off (pre-GA)

1. Clone two ephemeral appliances from Beta (VM 210 → VMIDs 221/222) **or** alias mode on Beta.
2. Pair `topology=multihost` with peer replication over LAN.
3. Write on node A → readable on node B.
4. Stop node A → leader fails over to B; split-brain guard blocks stale A publish.

Validators: `scripts/kb115_provision_sovereign_ephemeral_ha.sh`,
`scripts/kb115_validate_sovereign_ephemeral_ha.sh`, `scripts/kb115_teardown_sovereign_ephemeral_ha.sh`.

Alias lab mode: `SOVEREIGN_HA_MODE=alias` uses Beta IPs `192.168.0.231` / `.232`.

---

## 8. Phase 6 — Tier upgrade (offline path)

1. Customer emails upgrade request (manual).
2. MSSP generates new license on cloud (license factory only).
3. Engineer applies on cluster.
4. Assert new `svc-*` engines; customer UI shows modules; customer never touched license file.

---

## 9. MSSP operations checklist (manual inventory)

| Field | Maintained by |
|-------|----------------|
| Customer name / site | MSSP spreadsheet or admin notes |
| Tier / entitlements | Admin tenant record |
| License JTI / expiry | MSSP + on-box `entitlements.json` |
| Renewal date | MSSP calendar; appliance sends local reminder |
| VPN access for remote SOC | Customer IT — not platform fleet metadata |

---

## 10. References

- `backend-api/app/services/sovereign_edge.py`
- `postgres/init/049_sovereign_edge_deployment_mode.sql`
- `PLATFORM_SERVICE_UNIFORMITY.md`
- `kevantic-appliance/scripts/bake_golden_vm199_fleet_reporting.sh`
- Beta appliance: `192.168.0.226`

---

## 11. Implementation roadmap (one-by-one)

| Step | Deliverable | Status |
|------|-------------|--------|
| 1 | KB-112 doc + `sovereign_edge` mode + helpers + validator | Done |
| 2 | RBAC route matrix (`sovereign_rbac.py`, `test_sovereign_rbac.py`, `kb112_validate_sovereign_rbac.sh`) | Done |
| 3 | Beta single-node sovereign profile + air-gap script | Done |
| 4 | Offline license renewal reminder on appliance | Done |
| 5 | Dual-instance cluster layout on one host | Done |
| 6 | Full stack bake (TheHive, Shuffle, unified UI) | Done |
| 7 | Ephemeral 2-VM HA sign-off before GA | Done |
