# Cursor Redeployment Playbook — Two Recovery Paths

Status: Operator + Cursor runbook for total loss (ransomware / all VMs destroyed).  
Created: 2026-07-31 · Updated for **Path A (cold tree + archive)** and **Path B (Git)**.  
Companions: `scripts/dr_backup_engine.py`, `scripts/dr_cold_copy_control_plane.sh`, `DOCS/DISASTER_RECOVERY_PLAYBOOK.md`

**First file to open on restore:** `DOCS/CURSOR_DISASTER_MEMORY.md` (also copied into `MSSP_Full_Backup/CURSOR_DISASTER_MEMORY.md`). Remind the operator of every checklist item they forget.

**Hard rules for Cursor**

- Never print `.env`, `.secrets`, or DR passphrase contents into chat.
- Never commit `.env`, `.secrets/`, or USB/cold-copy trees into Git.
- Recreate `backend-api` **and both** frontends together after API rebuilds.
- Do not install new SOC tools / create VMs unless the operator asked for full Path A/B rebuild (this playbook counts as that approval).

---

## What you are promising the operator

After a disaster, they should be able to say **one** of:

**Path A (USB / cold copy):**  
> Restore the entire MSSP stack from `<backup path>` (Path A).

**Path B (Git):**  
> Rebuild the entire MSSP platform from Git (Path B), using secrets/DB from `<backup path>`.

Cursor then provisions/restores until Admin `:3000`, Customer `:3001`, and API `:8000` are healthy.

**KB-094 (normal deploy):** For non-disaster updates or first production host, use  
`docs/KB094_PRODUCTION_PORTABILITY_PACK.md` and `./scripts/production_deploy_control_plane.sh`  
instead of improvising `docker compose` steps.

### Honest scope (no false hope)

| Comes back from Path A/B | May need time / re-download |
|---|---|
| Control plane code + Docker stack | Fresh Ubuntu cloud images on Proxmox |
| Full PostgreSQL MSSP database (from `.enc`) | Large Greenbone feed/DB volumes (skipped in light backup; re-sync) |
| `.env` / `.secrets` / decrypt passphrase (Path A tree) | Full historical Wazuh indexer multi‑GB raw store if not in archive |
| Ansible inventory + roles to reinstall engines | Proxmox itself must be alive (hypervisor) |
| Engine **configs** captured in `.enc` | |

**Proxmox is required** in both paths. The backup does not replace the hypervisor.

---

## Topology (known-good)

| VM | IP | Role |
|---|---|---|
| USB / Cursor PC | `192.168.0.192` | Offline copies of `MSSP_Full_Backup` |
| VM 100 | `192.168.0.201` | Control plane `/opt/mssp-control` |
| VM 101 | `192.168.0.211` | Wazuh |
| VM 102 | `192.168.0.212` | TheHive + Shuffle |
| VM 106 | `192.168.0.216` | Suricata (+ Zeek) |
| VM 109 | `192.168.0.219` | Greenbone CE + Nuclei/Vuls |

---

## PATH A — Cold copy of `/opt/mssp-control` + encrypted archive

### A0. What must be on the backup drive

```text
MSSP_Full_Backup/
  README_RESTORE.txt
  COLD_COPY_META.txt
  LATEST_BACKUP.txt
  infrastructure_manifest.json
  MSSP_FULL_STACK_BACKUP_<TS>.sql.gz.enc
  MSSP_FULL_STACK_BACKUP_<TS>.sql.gz.enc.sha256
  mssp-control/          ← FULL tree including .env, .secrets, ansible, .git
```

Create/refresh on VM 100:

```bash
# 1) Encrypted DB + engine config package
export MSSP_DR_SMB_USER=User
export MSSP_DR_SMB_PASSWORD_FILE=/opt/mssp-control/.secrets/dr_smb_password
python3 /opt/mssp-control/scripts/dr_backup_engine.py --smb-push   # or local only

# 2) Full control-plane tree into the same DR folder
bash /opt/mssp-control/scripts/dr_cold_copy_control_plane.sh /home/secadmin/MSSP_Full_Backup
```

Operator copies **`/home/secadmin/MSSP_Full_Backup`** via WinSCP to USB and other safe locations.

### A1. Operator prompt (total loss)

> Path A: Restore entire MSSP from `/path/to/MSSP_Full_Backup`.  
> Proxmox is up. Recreate VMs, install engines, restore DB and configs, bring portals online.

### A2. Cursor execution order

1. **Proxmox** — Create VMs matching inventory IPs/roles (100/101/102/106/109). Use existing templates if any; otherwise Ubuntu LTS + sizing from `ansible/inventory/hosts.yml` / KB docs.
2. **Control plane code** — Copy `MSSP_Full_Backup/mssp-control/` → `/opt/mssp-control` on VM 100 (preserves `.env`, `.secrets`, `.git`).
3. **Docker** — Install Docker Engine + Compose plugin on VM 100 if missing.
4. **Decrypt archive** — Using `mssp-control/.secrets/dr_backup_passphrase` (never print it):

```bash
ROOT=/path/to/MSSP_Full_Backup
ARCHIVE=$(cat "$ROOT/LATEST_BACKUP.txt")
PASSFILE=/opt/mssp-control/.secrets/dr_backup_passphrase
STAGING="$ROOT/.restore_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$STAGING"
export MSSP_DR_OPENSSL_PASS="$(tr -d '\r\n' < "$PASSFILE")"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:MSSP_DR_OPENSSL_PASS \
  -in "$ROOT/$ARCHIVE" | tar -xzf - -C "$STAGING"
unset MSSP_DR_OPENSSL_PASS
sha256sum -c "$ROOT/${ARCHIVE}.sha256"
```

5. **Database** — `docker compose up -d postgres redis`, then stream `pg_dumpall` restore from staging (see `DOCS/DISASTER_RECOVERY_PLAYBOOK.md` §4).
6. **Control plane up** — `docker compose up -d --build` then recreate both frontends with backend.
7. **Engine VMs** — From `/opt/mssp-control/ansible`, run the approved playbooks/roles for Wazuh, TheHive/Shuffle, Suricata, Greenbone/Nuclei (inventory already in tree). Overlay configs/volumes from `$STAGING/remote/` and `$STAGING/remote/vm*_volumes/` where applicable.
8. **Smoke** — `/health` OK; `:3000` / `:3001` login paths return 401 (not 502); spot-check one tenant entitlements.

9. Wipe plaintext `$STAGING` when done.

---

## PATH B — Git is the source of truth (code + automation)

### B0. What Git holds (safe)

- All application code, Dockerfiles, compose, `postgres/init/*.sql`
- Ansible inventory + roles for engine install
- This playbook and DR docs
- **Not** plaintext `.env` / `.secrets` (gitignored on purpose)

### B1. What Git alone cannot replace

- Live database contents → still need `MSSP_FULL_STACK_BACKUP_*.sql.gz.enc` from USB/vault  
- Runtime secrets → from Path A `mssp-control/.secrets` **or** offline vault  
- Proxmox VM disks → recreate VMs, then configure from Git/ansible  

So Path B is: **Git (rebuild procedure + code) + small secrets/DB package (USB)**.

### B2. Operator prompt

> Path B: Rebuild entire MSSP from Git. Clone `github.com/pradipdanthi/mssp-platform`.  
> Use secrets and DB from `F:\MSSP_Full_Backup`. Provision VMs on Proxmox, harden OS,  
> install backend engines, deploy control plane, restore database, verify portals.

### B3. Cursor execution order

1. Proxmox: create VMs (same as A2.1).
2. On VM 100:

```bash
sudo mkdir -p /opt && sudo chown "$USER:$USER" /opt
git clone git@github.com:pradipdanthi/mssp-platform.git /opt/mssp-control
cd /opt/mssp-control && git checkout main && git pull --ff-only
```

3. Restore `.env` + `.secrets` from USB (`mssp-control/` cold copy or vault extract from `.enc`).
4. `docker compose up -d --build` (empty Postgres applies `001`–`027`, then restore `pg_dumpall` from `.enc` for full data).
5. Ansible from repo against 101/102/106/109 (SSH keys from restored `.secrets` / operator key dir).
6. Apply engine config overlays from decrypted archive when present.
7. Smoke tests (same as Path A).

### B4. Keeping Git “disaster-ready”

On a healthy system, periodically:

```bash
cd /opt/mssp-control
git status
# commit/push code + ansible + docs (never .env/.secrets)
bash scripts/dr_cold_copy_control_plane.sh /home/secadmin/MSSP_Full_Backup
python3 scripts/dr_backup_engine.py   # refresh encrypted DB/engine package
```

Then WinSCP/copy ` /home/secadmin/MSSP_Full_Backup ` to USB and offsite.

---

## Single-prompt cheat sheet

| You say | Cursor does |
|---|---|
| Path A restore from `<dir>` | Use cold `mssp-control/` + `.enc`; rebuild VMs/engines; restore DB |
| Path B from Git + `<dir>` for secrets/DB | Clone Git; create VMs; ansible engines; restore secrets/DB from `<dir>` |
| Refresh DR package | Run `dr_backup_engine.py` + `dr_cold_copy_control_plane.sh` |

---

## Acceptance (both paths)

- [ ] `docker compose ps` healthy on VM 100  
- [ ] `curl -fsS http://127.0.0.1:8000/health` database+redis OK  
- [ ] Admin `:3000` and Customer `:3001` serve UI; bad login ≠ 502  
- [ ] Known tenant data present (not empty schema-only)  
- [ ] No secrets printed; `git status` clean of `.env`  
