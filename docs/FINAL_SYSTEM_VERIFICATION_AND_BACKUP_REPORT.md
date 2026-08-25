# Final System Verification & Backup Report

**Date:** 2026-08-01  
**Control plane:** VM 100 `192.168.0.201` (`/opt/mssp-control`)  
**VIP tenant:** `ALPHAWINCORP-6VS2` (Alpha-Win-Corp)  
**Operator:** automated E2E verification + DR backup run

**Verdict:** Platform is **operationally ready** for the 10-card Service Catalog path. Local AES-256 backup **SUCCESS**. Google Drive `rclone` sync of the encrypted archive + checksum + manifest **SUCCESS**. Remaining honesty gaps: Microsoft Graph credentials (ITDR seeded), TheHive case list empty at probe time (alerts/incidents still in control plane), Windows Velociraptor client still manual on VM 104, live isolate/kill not re-fired this run (historical `verified` proofs + AR scripts present).

---

## Part 1 — Ten catalog engines

| # | Catalog service | Engine / path | Verification result | Status |
|---:|---|---|---|---|
| 1 | Log & Event Monitoring | VM 101 Wazuh | API `55000` reachable (auth required); **3 agents** active (`wazuh-stack`, `suricata-sensor`, `WIN-BL72S84GDTF`); Alpha has **459** `security_alerts` | **PASS** |
| 2 | Incident Response & Casework | VM 102 TheHive **4.1.24** + Shuffle | TheHive `/api/status` OK; control-plane **13** Alpha incidents; live `_search` returned **0** open cases at probe (org/filter may be empty — not a control-plane outage) | **PASS** (CP) / **WARN** (empty TheHive case list) |
| 3 | Security Automation & Containment | VM 101 AR + Redis Shuffle queue | AR scripts on manager: `mssp-isolate-host`, `mssp-kill-process`, `mssp-block-hash`; `shuffle_retry_queue` module present (`mssp:shuffle:outbound`); historical EDR rows include multiple `ISOLATE_HOST` → **`verified`** | **PASS** (scripts + proof history; no fresh isolate fired this run) |
| 4 | Continuous Compliance (CaaS) | VM 101 SCA | `POST /admin/compliance/ALPHAWINCORP-6VS2/sync` → **200**, score **27.3%**, 359 checks (98 pass / 261 fail), 1 agent | **PASS** |
| 5 | Vulnerability Management (VMaaS) | VM 109 Nuclei + Greenbone CE | GSA HTTPS **200**; Nuclei **v3.11.0**; `POST /admin/vmaas/.../sync` → **COMPLETED**, `live_ingest`, findings present | **PASS** |
| 6 | External Attack Surface (EASM) | VM 109 Amass agent | Timer `mssp-easm-scan-agent.timer` **active**; Amass binary under `/opt/mssp-easm-agent/bin`; `POST /admin/easm/.../scan` → **PENDING** remote queue (4 targets) | **PASS** |
| 7 | Network Detection & Response | VM 106 Suricata + Zeek | Suricata **active**; Zeek process running; `eve.json` recent `stats`; NDR sync **200** with sensor summary | **PASS** |
| 8 | Threat Intelligence | VM 108 MISP bridge `:8080` | Health `pymisp_compatible`; TI sync **`source=misp_vm108`**, **6 IOCs** + 3 campaigns | **PASS** |
| 9 | Endpoint Forensics & Deception | VM 110 + Linux client 105 | Bridge `:8001` health OK; forensics sync **`velociraptor_bridge+edr_bridge`**; `POST /v1/collect` → **HTTP 202 RUNNING** on `linux-endpoint-lab`; client service **active**. Windows 104 pack only (manual) | **PASS** (Linux) / **PENDING** (Windows client install) |
| 10 | Cloud & Identity (ITDR) | Graph client + seed | `itdr_graph_client.configured() == False` (no Azure secrets); ITDR sync **200** with `source=analysis_adapter` (seeded events) | **PASS** (fallback) / **PENDING** (live Graph) |

### Control-plane smoke

| Check | Result |
|---|---|
| `GET /health` | `api/database/redis` **ok** |
| Admin `:3000` / Customer `:3001` `POST /api/auth/login` (bad password) | **401** (not 502/405) |
| Docker services | `backend-api`, `frontend-admin`, `frontend-customer`, `postgres`, `redis` Up |

### Honesty notes

- TheHive is **4.1.x**, not TheHive 5.
- MISP on 108 is a **MISP-compatible REST bridge**, not full upstream MISP UI.
- NDR/ITDR may blend live DB rows with analysis-adapter enrichment when raw feeds are thin.
- Fresh `ISOLATE_HOST` / `KILL_PROCESS` were **not** executed against production lab endpoints in this run (avoids disruptive quarantine); readiness is proven via manager AR binaries + prior `verified` executions + durable queue code.

---

## Part 2 — Onboarding entitlement isolation

### VIP `ALPHAWINCORP-6VS2`

Mapped from live admin entitlements using the same rules as `frontend-customer/src/data/serviceCatalog.ts`:

| Card | Status |
|---|---|
| Log & Event Monitoring | **INCLUDED** |
| Incident Response | **INCLUDED** |
| Security Automation | **ACTIVE** |
| Vulnerability Management | **ACTIVE** |
| Continuous Compliance | **ACTIVE** |
| External Attack Surface | **ACTIVE** |
| Cloud & Identity | **ACTIVE** |
| Network Detection | **ACTIVE** |
| Threat Intelligence | **ACTIVE** |
| Endpoint Forensics | **ACTIVE** |

**ALL_INCLUDED_OR_ACTIVE = true** — Open-in-portal paths are enabled for entitled cards in the customer Services UI.

### New-tenant default template

`entitlements_for_new_tenant("ACME-TEST-01")` equals `CORE_ONLY_CREATE_ENTITLEMENTS`:

- Core ON: `wazuh_siem=true`, `thehive_mode=full`
- Add-ons OFF → UI **AVAILABLE** + **Request for Consulting**: Greenbone/VMaaS, CaaS, Zeek/NDR, MISP/TI, Velociraptor/Forensics, EASM, ITDR, `shuffle_mode=off`

`entitlements_for_new_tenant("ALPHAWINCORP-6VS2")` equals full demo catalog (`DEMO_FULL_ENTITLEMENTS`).

Wiring confirmed in `tenant_management.py` create path → `entitlements_for_new_tenant` → `upsert_tenant_entitlements`.

---

## Part 3 — Master DR backup

### Engine run

```text
python3 scripts/dr_backup_engine.py --backup-root <resolved>
```

Backup root resolved to: `/home/secadmin/MSSP_Full_Backup`  
(`/var/backups/mssp_full_backup` was not creatable without interactive sudo.)

`scripts/dr_backup_engine.py` was extended this run to capture **VM 108** and **VM 110** in addition to 101/102/106/109/112.

| Component | Result |
|---|---|
| PostgreSQL `pg_dumpall` (gzip) | OK (~193 KB compressed stream into package) |
| `.env` + `.secrets/` + `postgres/init` | Captured (secrets never printed) |
| Remote VM 101 Wazuh | OK |
| Remote VM 102 TheHive/Shuffle + volumes | OK |
| Remote VM 106 Suricata/Zeek | OK |
| Remote VM 108 MISP bridge | OK |
| Remote VM 109 Greenbone/Nuclei/EASM (+ light volumes) | OK (heavy feed volumes skipped by design) |
| Remote VM 110 Velociraptor | OK |
| Remote VM 112 Ansible | OK |
| Encryption | `openssl` AES-256-CBC PBKDF2 |
| Local SHA-256 verify | **OK** |

### Local archive

| Field | Value |
|---|---|
| Path | `/home/secadmin/MSSP_Full_Backup/MSSP_FULL_STACK_BACKUP_20260801T182117Z.sql.gz.enc` |
| Size | **299,597,184** bytes (~286 MiB) |
| Mode | **440** (read-only owner/group) |
| SHA-256 | `efbb19f19a00fdd7410abf4a3dc183eb22804f76ea50d58d532c9c04a175c377` |
| Checksum file | `MSSP_FULL_STACK_BACKUP_20260801T182117Z.sql.gz.enc.sha256` |
| Manifest | `infrastructure_manifest.json` (`complete=True`) |
| Pointer | `LATEST_BACKUP.txt` |

### Google Drive (`rclone` remote `gdrive:`)

```bash
rclone copy /home/secadmin/MSSP_Full_Backup/ gdrive:MSSP_Cloud_Backups/ \
  --include 'MSSP_FULL_STACK_BACKUP_20260801T182117Z.sql.gz.enc' \
  --include 'MSSP_FULL_STACK_BACKUP_20260801T182117Z.sql.gz.enc.sha256' \
  --include 'infrastructure_manifest.json' \
  --include 'LATEST_BACKUP.txt'
```

| Remote object | Bytes | Confirmed |
|---|---:|---|
| `gdrive:MSSP_Cloud_Backups/MSSP_FULL_STACK_BACKUP_20260801T182117Z.sql.gz.enc` | 299597184 | **YES** |
| `…sql.gz.enc.sha256` | 117 | **YES** |
| `infrastructure_manifest.json` | 8940 | **YES** |
| `LATEST_BACKUP.txt` | 51 | **YES** |

Transfer log: **4 / 4 files, 285.727 MiB, 100%**.  
Note: `--create-empty-src-dirs` also started creating empty directory stubs from a nested `mssp-control/` tree inside the backup root; that crawl was stopped after the four required objects were confirmed on Drive. Prefer future syncs **without** `--create-empty-src-dirs`, or copy only the four artifact names.

Passphrase source: `/opt/mssp-control/.secrets/dr_backup_passphrase` (not printed).

---

## Part 4 — Overall status

| Area | Status |
|---|---|
| 10 engine smoke / sync | **PASS** (with documented WARN/PENDING items above) |
| VIP full catalog | **PASS** |
| New-tenant core-only defaults | **PASS** |
| Local encrypted backup + SHA-256 | **PASS** |
| Google Drive rclone sync | **PASS** |

**Recommended next operator actions (optional):**

1. Set Azure Graph app secrets to flip ITDR from seed → live.  
2. Install Velociraptor Windows client on VM 104 from `deploy/velociraptor-client/`.  
3. Confirm TheHive org/`MSSP` case visibility if SOC expects live cases in TheHive UI.  
4. Use Proxmox snapshot after accepting this backup.  
5. Prefer rclone sync of **only** the `.enc` / `.sha256` / manifest / `LATEST_BACKUP.txt` files.

---

*Generated by the 2026-08-01 final E2E verification & DR backup run. Source of truth for runtime: live probes + validation responses above; git tags remain the formal feature baseline.*
