# KB-091 — Enterprise containment honesty & platform gap register

Status: Active remediation register (2026-07-30).  
Audience: Product owner + engineering.  
Rule: **Never claim containment success without endpoint-proven effect.**

## Incident that forced this register

Customer isolate showed **Isolated / verified**, but the Windows host could still ping the gateway. Root cause:

1. Control plane treated “Wazuh Manager accepted Active Response” + “agent still online” as proof of isolation.
2. Agent-online is *expected* during isolation (manager IP allow-listed) and proves nothing about LAN blocking.
3. Windows AR scripts were likely not installed / old firewall approach was weak.
4. Packaging validators only proved ZIP membership — not live containment.

That is a **false-confidence / market-readiness failure**, not a cosmetic UI bug.

## Today's build + standalone Windows proof (no GPO)

**Build:** default-deny network quarantine AR + honest Dispatched UI/API + `Test-MsspQuarantineProof.ps1`.

**SOC if quarantine fails later (e.g. GPO host):** treat as containment failure → network/identity compensating controls; never mark Isolated.

**Standalone pass:** log `QUARANTINE ACTIVE applied=true`, all profiles Outbound=Block, LAN probes fail, Manager path OK, then Un-isolate restores.

## Critical gaps (security false confidence)

| ID | Gap | Status |
|---|---|---|
| C1 | Kill / block-hash marked success on dispatch only | **Mitigated (label honesty)** — endpoint callback still TODO |
| C2 | UI “Success” for kill/block | **Fixed** → **Dispatched** |
| C3 | Block-hash only appends a text file; no WDAC/AppLocker/ASR | **Documented in API message**; enforcement TODO |
| C4 | AR scripts swallow errors; no control-plane callback | Open |
| C5 | `/v1/edr/actions/callback` unused by AR scripts | Open |
| C6 | `get_agent_os` defaulted to linux | **Fixed** → `unknown` fail-closed |
| C7 | Shared callback API key can forge success across tenants | Open |

## High gaps (production containment)

| ID | Gap | Status |
|---|---|---|
| H1 | Windows AR validators are packaging-only | Open — need live ping-fail / taskkill proof script |
| H2 | Manager AR registration is manual SSH; no preflight in UI | Open |
| H3 | No functional unit/integration tests for `.ps1` netsh/taskkill | Open |
| H4 | Dual AR source trees (`deploy/` vs `endpoint_configs/`) | Sync script added; single-source build still TODO |
| H5 | No durable async retry for AR | Open |
| H6 | No endpoint self-test of isolation | Open (harden script shipped; proof callback TODO) |
| H7 | Empty process tree vs missing Sysmon not distinguished in onboarding health | Open |
| H8 | Customer admin can isolate/kill with only client confirm | Policy decision pending |
| H9 | Hardcoded lab manager IP defaults | Acceptable for current on-prem; must parameterize for multi-site |

## Platform UX gaps (non-EDR)

Search + server pagination exist for Alerts/Incidents (Admin+Customer). Still missing at scale for: Tenants, Assets, Appliances, Users, Reports, Recommendations, Notifications, Audit (hard caps), Vulns.

## Remediation waves

### Wave 0 — Honesty (done / in this change set)

- Stop isolate auto-**verified** on agent-online alone.
- Kill / isolate / unisolate / block-hash UI → **Dispatched** until verified.
- Fail closed on unknown agent OS.
- Harden Windows isolate to `blockoutbound` profile policy.
- Gap register (this doc).
- Sync Windows AR pack copies + honesty validator.

### Wave 1 — Prove containment (next, required before marketing “EDR response”)

1. AR scripts POST real exit status to `/v1/edr/actions/callback` (per-execution token preferred).
2. Live lab validator: isolate → gateway ping fails; kill → PID gone; only then PASS.
3. Manager AR command preflight API + Admin warning if unregistered.
4. Either wire real **Block hash** enforcement or hide/disable the button.

### Wave 2 — Enterprise controls

- Per-tenant/per-execution callback auth (retire shared forgeable key model).
- SOC co-sign / rate-limit for customer-initiated isolate/kill.
- Telemetry health onboarding gate (Sysmon flowing) next to process tree.
- Single AR source of truth in build pipeline.

### Wave 3 — Scale UX

- Pagination/search/export for remaining Admin/Customer lists.
- Confirmation modal consistency for all destructive actions.

## Owner commitment

Until Wave 1 live proof passes on Windows agent **006** (or successor):

- Do **not** tell operators “isolation works end-to-end.”
- Do **not** treat packaging validators as containment validation.
- Prefer **Dispatched** / **Failed** over optimistic green badges.
