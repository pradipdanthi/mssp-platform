# KB-077 — Greenbone **Enterprise** Migration Plan (deferred)

Status: **Deferred procurement** — user directed **$0 scanner licenses until ~5–10 customers**.  
**Primary free stack is now Nuclei + Vuls** (`docs/KB078_NUCLEI_VULS_FREE_STACK.md`). This KB remains the Enterprise upgrade path when spend is approved.  
Module type: Migration plan + procurement gate (no paid license purchased by this doc alone).  
Date: 2026-07-28 (revised same day — free-stack pivot via KB-078).

Builds on: KB-052, KB-068 (CE deploy), KB-069, KB-070, KB-053, KB-076, **KB-078**.

---

## 0. Relationship to KB-078

| Item | Value |
|---|---|
| Now | Run **Nuclei + Vuls** as primary free coverage; keep Greenbone **Community** optional |
| Later | When customer volume justifies cost, execute this KB’s Enterprise phases |
| Do not | Buy Enterprise feed/appliance in this module |

---

## 1. Locked product decision (when Enterprise is funded)

| Decision | Value |
|---|---|
| Target scanner (paid path) | **Greenbone Enterprise** (appliance / commercial path + **Enterprise Feed**) |
| Community Edition (VM 109 Docker) | Optional classic NVT backup alongside free stack until Enterprise cutover |
| Customer exposure | Never — Greenbone stays SOC/backend only |
| Control plane | Keep KB-069/070 adapter contracts; re-point to Enterprise host after cutover |

We will **not** waste cycles pretending Community Feed equals enterprise coverage — and we will **not** spend on Enterprise until the business gate clears.

---

## 2. Why this requires a commercial step (cannot skip)

Greenbone does **not** put the full **Enterprise Feed** into free Docker Community Edition.

| Path | What you get |
|---|---|
| Community Edition (current VM 109) | Community Feed — incomplete for enterprise networks |
| **Greenbone Enterprise Appliance / TRIAL + Enterprise Feed key** | Full enterprise VT coverage, compliance packs, vendor support path |

**Blocker for “deploy Enterprise now”:** a **subscription / trial key** (or purchased appliance) from Greenbone.  
Agents cannot invent or pirate that key. Once you provide Trial ISO/OVA + feed test key (or purchase confirmation), we execute install on Proxmox.

Official entry points (verify current URLs when executing):

- Enterprise Trial download / test: [https://www.greenbone.net/en/testnow/](https://www.greenbone.net/en/testnow/)  
- Feed comparison: [https://www.greenbone.net/en/feed-comparison/](https://www.greenbone.net/en/feed-comparison/)  
- Buy / sales: Greenbone “Buy” / contact sales for perpetual MSSP production

---

## 3. Target architecture (post-cutover)

```
Customer networks / protected assets (tenant-scoped)
  → Greenbone Enterprise scanner (Proxmox VM — replaces CE role)
  → Enterprise Feed (daily)
  → GMP / Task-Done hook → MSSP control plane (KB-069/070 pattern)
  → vulnerabilities + recommendations (customer-safe)
  → Admin/SOC dashboards only for raw findings
```

| Item | Target |
|---|---|
| Hypervisor | Same Proxmox as today |
| Suggested VM | New VM (e.g. **109b** or replace 109 after freeze) — **do not** dual-write production until validated |
| RAM / disk | Follow Greenbone Enterprise appliance sizing (typically **larger than CE’s 9 GB**; confirm against chosen model docs before create) |
| IP | Prefer keep `192.168.0.219` after CE decommission **or** new IP + update adapter secrets/map |
| Auth | SOC-only HTTPS; password/API secrets host-local only |
| Multi-tenant | Scan targets tagged/mapped per `tenant_id` / short_code (fail-closed) |

---

## 4. Migration phases (Enterprise-only path)

### Phase E0 — Procurement gate (YOU)

Choose one:

1. **Trial now:** Download Greenbone Enterprise TRIAL appliance + request **14-day Enterprise Feed test key**  
2. **Buy now:** Contact Greenbone sales for production appliance + Enterprise Feed subscription sized for MSSP  

Deliverables we need from you before install:

- [ ] Trial OVA/ISO available on a machine that can upload to Proxmox **or** purchase order / download credentials  
- [ ] Enterprise Feed key (trial or production) — store only on scanner host (never Git / never chat)  
- [ ] Approval of VM size (vCPU/RAM/disk) and whether to **replace** VM 109 or run parallel  

### Phase E1 — Deploy Enterprise on Proxmox (agent, after E0)

1. Create Proxmox VM from Enterprise appliance image  
2. Network: lab/prod VLAN, SOC-only management access  
3. Install feed subscription key; run feed sync; confirm Enterprise Feed status  
4. Create SOC admin user; store secrets host-local  
5. Validation: UI up, feed = Enterprise, sample network scan succeeds  

### Phase E2 — Cut over control plane

1. Point KB-070 / GMP credentials at Enterprise host  
2. Re-validate tenant map fail-closed  
3. End-to-end: scan → sync → Admin vuln → promote recommendation → customer-safe view  
4. Freeze CE Docker stack; snapshot; decommission or power off CE  

### Phase E3 — MSSP production ops

1. Per-tenant scan schedules from entitlements  
2. Authenticated-scan credential vault (SOC-only)  
3. Backup/restore runbook for Enterprise appliance + MSSP DB  
4. Monitoring (feed age, scan failures)  

---

## 5. Explicit stop list (no more nonsense)

**Do not** (unless user reverses this decision):

- Spend modules “making Community look enterprise”
- Claim Community Feed is enterprise-complete
- Purchasing Greenbone Enterprise licenses / appliances in this KB alone (wait for E0)
- Put Greenbone UI in front of customers
- Treat the platform as a disposable lab — on-prem is the production MSSP path

**Do:**

- Run Nuclei + Vuls as the primary free stack (KB-078) until E0 clears
- Treat CE as optional NVT backup
- Execute E1–E3 as soon as E0 materials exist

Historical Options A/B/C (pre–KB-078): Option A = stay on Community; Option B = trial Enterprise; Option C = buy Enterprise. **Option B/C remain the paid path when funded.** Phase 1 wiring (control-plane adapter) already exists via KB-069/070.

---

## 6. Validation (this revision)

```bash
cd /opt/mssp-control
./scripts/kb077_validate_greenbone_enterprise_readiness_plan.sh
```

---

## 7. Immediate ask (one reply)

Reply with **one** line so we start E1 without delay:

- `TRIAL ready` — you have Trial image + will place feed key on host (or tell us when uploaded to Proxmox storage)  
- `BUY path` — you are purchasing; paste model name / expected delivery (no secrets)  
- `Need help sizing` — we propose Proxmox VM size + checklist only (still no install until image/key exist)
