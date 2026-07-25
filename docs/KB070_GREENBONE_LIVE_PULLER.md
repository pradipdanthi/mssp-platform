# KB-070 — Greenbone Live / Instant Puller (GMP → Control Plane)

Status: **Implemented** — **instant** Task-Done hook on VM 109 + optional on-demand/SSH puller.  
Branch: `kb039-kb060-platform-roadmap-execution`  
Builds on: KB-068 (Greenbone live), KB-069 (sync API + Admin UI).

---

## 1. Purpose

Push **live scan findings** from Greenbone (VM 109) into the MSSP Control Plane as normalized `vulnerabilities` (+ draft recommendations for high/critical) **as soon as a scan finishes** — not on a 15-minute timer.

No Greenbone passwords or sync keys are stored in Git.

---

## 2. Instant path (primary)

```
Greenbone task → status Done
  → Alert "mssp-instant-scan-done-hook" (HTTP Get)
  → http://172.17.0.1:9271/hook/<token>  (host hook on VM 109)
  → mssp-greenbone-hook.service
  → GMP get_results (python-gvm, password from file mount — never sudo argv)
  → POST http://192.168.0.201:8000/integrations/vuln/sync
  → Admin → Vulnerabilities / Recommendations
```

| Piece | Location |
|---|---|
| Hook agent | `/opt/mssp-greenbone/bin/mssp_greenbone_hook_agent.py` (source: `scripts/kb070_greenbone_hook_agent.py`) |
| systemd | `mssp-greenbone-hook.service` on VM 109, listens `:9271` |
| Host map | `/opt/mssp-greenbone/config/greenbone_host_tenant_map.yml` |
| Alert name | `mssp-instant-scan-done-hook` (Task run status → Done, HTTP Get) |
| Lab task | `mssp-lab-linux-full-and-fast` (alert attached) |

Health check (on greenbone): `curl -fsS http://127.0.0.1:9271/health` → `ok`

---

## 3. On-demand / backup pull (secondary)

Manual or rare backup only — **not** the primary sync schedule:

```bash
cd /opt/mssp-control
DRY_RUN=1 ./scripts/kb070_pull_greenbone_findings.sh
./scripts/kb070_pull_greenbone_findings.sh
```

Optional cron (backup only, e.g. hourly) if the hook is down — **do not** use `*/15` as the main path.

---

## 4. Secrets (host-local only)

| Secret | Location |
|---|---|
| Greenbone admin password | VM 109 `/opt/mssp-greenbone/admin.secret.env` + `/opt/mssp-greenbone/secrets/admin.password` |
| Hook URL token | VM 109 `/opt/mssp-greenbone/secrets/hook_token` |
| Vuln sync API key | VM 100 `/opt/mssp-control/.secrets/vuln_sync_api_key` + copy on VM 109 `secrets/vuln_sync_api_key` |

**Never commit** these files. Password must **not** appear on `sudo` / `docker` command lines (journal can leak argv). Use file mounts into `gvm-tools`.

---

## 5. Host → tenant mapping

File: `/opt/mssp-control/config/greenbone_host_tenant_map.yml` (copied to greenbone for the hook)

- Maps scan host IPs to `tenant_short_code` + optional `asset_hostname`
- Default tenant for unmapped hosts: `DEMO`
- No secrets in this file

---

## 6. Commands

```bash
cd /opt/mssp-control
chmod +x scripts/kb070_*.sh

# Optional: start/reuse lab Full-and-fast scan of 192.168.0.215
./scripts/kb070_greenbone_start_lab_scan.sh

# When the task reaches Done, the hook pulls immediately.
# Manual backup pull:
./scripts/kb070_pull_greenbone_findings.sh

# Validate wiring + GMP connectivity
./scripts/kb070_validate_greenbone_live_puller.sh
```

Admin UI: `http://192.168.0.201:3000/vulnerabilities`  
GSA: `https://192.168.0.219`

---

## 7. Lab scan note

A Full-and-fast scan of the Linux endpoint can take a while. When status becomes **Done**, the alert fires the hook and sync runs within seconds.

Task name: `mssp-lab-linux-full-and-fast`.

---

## 8. Validation

Expected final line:

```text
KB-070 GREENBONE LIVE PULLER VALIDATION PASSED
```
