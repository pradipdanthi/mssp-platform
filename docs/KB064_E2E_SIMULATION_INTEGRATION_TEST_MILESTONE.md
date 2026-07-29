# KB-064 — End-to-End Simulation & Integration Testing Milestone

Status: **Planned / partially ready** (2026-07-25)  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: Milestone / test plan (no schema change required to start)

## 1. Objective

After core infrastructure, integrations, and dashboards are established, run a controlled **end-to-end integration test** with simulated telemetry and attacks, then prove the full MSSP path into both Admin and Customer USP dashboards.

## 2. Scope

| # | Area | Requirement |
|---|---|---|
| 1 | Agent onboarding | **One Linux agent** + **one Windows agent** enrolled in Wazuh |
| 2 | Attack simulation | Controlled alerts on both endpoints (Atomic Red Team, EICAR, and/or custom scripts) |
| 3 | Pipeline | Wazuh → Shuffle → TheHive (case/alert creation) |
| 4 | Control plane | Instant/normalized ingest into PostgreSQL (KB-061/063 path) |
| 5 | Dashboards | Admin + Customer portals show alerts/cases/metrics correctly (customer data only after `customer_visible`) |

## 3. Readiness gate (agents must check before prompting to start)

Prompt the human to start this milestone only when **all** of the following are true, or clearly list gaps:

| Gate | Ready now? | Notes |
|---|---|---|
| Wazuh Manager live | **Yes** | VM 101 / 4.14.6 |
| Linux agent onboarded | **No** | VM 105 decommissioned — reinstall manually, then re-enroll |
| Windows agent onboarded | **No** | Still required before full E2E |
| Wazuh → Shuffle → TheHive | **Yes** | KB-049 proven |
| Instant Wazuh → control plane | **Yes** | KB-063 live (seconds) |
| Admin dashboard alerts/incidents | **Yes** | KB-056 + sync |
| Customer dashboard surfaces | **Partial** | UI ready; needs SOC `customer_visible=true` for live synced rows |
| Suricata path (optional enrich) | **Yes** | VM 106 / rule 86601 (network side; not a substitute for Windows endpoint) |

**Current recommendation:** Start **Phase A** (Linux-only rehearsal) anytime; start **full milestone** after Windows agent onboarding.

## 4. Test phases

### Phase A — Linux rehearsal (can run now)
1. Confirm agent 001 Active  
2. Run one controlled high-severity simulation on Linux  
3. Confirm: Wazuh alert → control plane incident/alert (instant) → Shuffle/TheHive  
4. Admin UI shows new row within seconds  
5. SOC marks `customer_visible` → Customer UI shows safe summary  

### Phase B — Windows onboarding (blocker for full scope)
1. Provision/enroll Windows lab endpoint into Wazuh  
2. Prove agent Active on Manager  

### Phase C — Dual-endpoint attack simulation
1. Atomic Red Team / EICAR / custom scripts on Linux + Windows  
2. Record rule IDs, severities, timestamps  

### Phase D — Full dashboard validation
1. Admin: alerts, incidents, KPIs update  
2. Customer: only approved visible items; tenant isolation still holds  
3. Capture pass/fail checklist in this doc §6  

## 5. Safety rules

- Simulations stay in **lab VMs only**  
- No production systems  
- No secrets in Git/docs  
- Customer portal never gets raw Wazuh/TheHive JSON, IPs, or internal notes  
- Prefer reversible / documented attack techniques  

## 6. Pass checklist (fill during execution)

- [ ] Linux agent Active  
- [ ] Windows agent Active  
- [ ] Controlled alert from Linux observed in Wazuh  
- [ ] Controlled alert from Windows observed in Wazuh  
- [ ] Shuffle execution succeeded  
- [ ] TheHive alert/case created  
- [ ] Control plane alert/incident created (instant path)  
- [ ] Admin dashboard shows both endpoint alerts/incidents  
- [ ] After SOC visibility approval, Customer dashboard shows safe summaries  
- [ ] Cross-tenant isolation spot-check (DEMO vs DEMO2) still 404  

## 7. Agent behavior (standing instruction)

When backend ingest, Wazuh/Shuffle/TheHive path, and Admin/Customer alert-incident views are sufficiently built **and** Windows agent onboarding is done (or user explicitly asks to run Linux-only rehearsal), the agent must **proactively prompt** the human:

> “E2E simulation milestone is ready / partially ready. Shall we start Phase A (Linux) or wait for Windows agent onboarding?”

Do not silently skip this milestone after major integration KBs.

## 8. Validation (docs gate)

```bash
cd /opt/mssp-control
test -f docs/KB064_E2E_SIMULATION_INTEGRATION_TEST_MILESTONE.md
grep -q 'Windows agent' docs/KB064_E2E_SIMULATION_INTEGRATION_TEST_MILESTONE.md
grep -q 'proactively prompt' docs/KB064_E2E_SIMULATION_INTEGRATION_TEST_MILESTONE.md
```
