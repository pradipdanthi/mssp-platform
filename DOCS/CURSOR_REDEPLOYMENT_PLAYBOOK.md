# Cursor Redeployment Playbook — MSSP Full Stack DR

Status: Machine-readable instructions for **Cursor** when the operator says:

> “Redeploy the entire MSSP stack using the backup at `F:\MSSP_Full_Backup`”  
> **or**  
> “Rebuild the entire infrastructure from Git”

Created: 2026-07-31  
Companion docs: `DOCS/DISASTER_RECOVERY_PLAYBOOK.md`, `scripts/dr_backup_engine.py`

**Hard rules for Cursor**

- Never print `.env`, `.secrets`, or DR passphrase contents into chat.
- Never commit `.env`, `.secrets/`, or anything under the USB backup root.
- Prefer streaming restore; do not leave plaintext SQL dumps on VM root disks.
- Recreate `backend-api` **and both** frontends together after API rebuilds.

---

## 0. Topology (known-good)

| VM | IP | Role |
|---|---|---|
| Cursor / USB host | `192.168.0.192` | Windows PC with USB at `F:\MSSP_Full_Backup` (SMB 445) |
| VM 100 | `192.168.0.201` | Control plane `/opt/mssp-control` |
| VM 101 | `192.168.0.211` | Wazuh |
| VM 102 | `192.168.0.212` | TheHive + Shuffle |
| VM 106 | `192.168.0.216` | Suricata (+ Zeek colocated) |
| VM 109 | `192.168.0.219` | Greenbone CE + Nuclei/Vuls |

USB access from VM 100: **SMB/CIFS** (SSH to `.192` is typically closed).  
Linux mount point: `/mnt/mssp-dr-usb` → share `MSSP_Full_Backup`.

---

## 1. Operator trigger phrases → Cursor mode

| Operator says | Cursor mode |
|---|---|
| Redeploy from `F:\MSSP_Full_Backup` | **Mode A — Backup restore** (this playbook §§2–6) |
| Rebuild from Git | **Mode B — Git greenfield** (§7) then optionally hydrate DB from backup |
| Run a new full backup | Execute `python3 scripts/dr_backup_engine.py` (§8) |

---

## 2. Target environment verification (Mode A)

1. Confirm Cursor workspace is the control-plane host (or SSH into `192.168.0.201`).
2. Verify Docker + Compose:

```bash
docker --version
docker compose version
cd /opt/mssp-control && docker compose ps
```

3. Ensure USB is reachable from VM 100:

```bash
# Preferred: already mounted
ls -la /mnt/mssp-dr-usb/MSSP_Full_Backup

# Or mount (credentials via files — never echo passwords):
export MSSP_DR_SMB_HOST=192.168.0.192
export MSSP_DR_SMB_SHARE=MSSP_Full_Backup
export MSSP_DR_SMB_USER='<windows-user>'
export MSSP_DR_SMB_PASSWORD_FILE=/opt/mssp-control/.secrets/dr_smb_password
python3 scripts/dr_backup_engine.py --mount-smb --skip-remote   # mount path used by engine
# For restore-only, mount manually with mount.cifs if preferred.
```

4. Confirm backup artifacts exist:

```text
F:\MSSP_Full_Backup\MSSP_FULL_STACK_BACKUP_<TIMESTAMP>.sql.gz.enc
F:\MSSP_Full_Backup\MSSP_FULL_STACK_BACKUP_<TIMESTAMP>.sql.gz.enc.sha256
F:\MSSP_Full_Backup\infrastructure_manifest.json
F:\MSSP_Full_Backup\LATEST_BACKUP.txt
```

5. Verify checksum **before** decrypt:

```bash
ROOT=/mnt/mssp-dr-usb/MSSP_Full_Backup   # or $MSSP_DR_BACKUP_ROOT
cd "$ROOT"
ARCHIVE=$(cat LATEST_BACKUP.txt)
sha256sum -c "${ARCHIVE}.sha256"
```

Abort on mismatch.

---

## 3. Repository & secrets restoration

### 3.1 Clone / sync code

```bash
sudo mkdir -p /opt
# if missing:
git clone git@github.com:pradipdanthi/mssp-platform.git /opt/mssp-control
cd /opt/mssp-control
git fetch --all
git checkout main
git pull --ff-only
git log -1 --oneline
```

### 3.2 Unpack vault from encrypted backup (into staging on USB, then copy)

Passphrase lives in offline vault or `/opt/mssp-control/.secrets/dr_backup_passphrase` (gitignored).

```bash
ROOT=/mnt/mssp-dr-usb/MSSP_Full_Backup
ARCHIVE=$(cat "$ROOT/LATEST_BACKUP.txt")
PASSFILE=/opt/mssp-control/.secrets/dr_backup_passphrase
RESTORE_STAGING="$ROOT/.restore_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RESTORE_STAGING"

export MSSP_DR_OPENSSL_PASS="$(tr -d '\r\n' < "$PASSFILE")"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:MSSP_DR_OPENSSL_PASS \
  -in "$ROOT/$ARCHIVE" | tar -xzf - -C "$RESTORE_STAGING"
unset MSSP_DR_OPENSSL_PASS
```

Copy secrets (do not cat them):

```bash
cd /opt/mssp-control
install -m 600 "$RESTORE_STAGING/vault/mssp-control.env" .env
mkdir -p .secrets && chmod 700 .secrets
cp -a "$RESTORE_STAGING/vault/secrets/." .secrets/
chmod 600 .secrets/* 2>/dev/null || true
```

Confirm directory layout:

```bash
test -f docker-compose.yml && test -d backend-api && test -d postgres/init
ls postgres/init/02{1,2,3,4,5,6,7}_*.sql
```

---

## 4. Decryption & database restoration

### 4.1 Start Postgres only (empty volume for true DR)

```bash
cd /opt/mssp-control
# WARNING: destroys local DB volume — only on confirmed dead/empty target
# docker compose down
# docker volume rm mssp-control_postgres_data   # confirm name via docker volume ls
docker compose up -d postgres redis
docker compose ps
```

Wait until Postgres healthy.

### 4.2 Stream SQL back in (from USB staging; no copy to /tmp on VM)

The encrypted package contains `postgres/pg_dumpall.sql.gz`:

```bash
gunzip -c "$RESTORE_STAGING/postgres/pg_dumpall.sql.gz" \
  | docker compose exec -T postgres \
      psql -U mssp_admin -d postgres -v ON_ERROR_STOP=1
```

(`pg_dumpall` restores roles + databases; connect to `postgres` maintenance DB.)

### 4.3 Integrity checks

```bash
docker compose exec -T postgres psql -U mssp_admin -d mssp_control -c "\dt tenant_*"
docker compose exec -T postgres psql -U mssp_admin -d mssp_control -c \
  "SELECT count(*) AS tenants FROM tenants;"
# Expect Phase tables among others:
# tenant_compliance_*, tenant_easm_*, tenant_cloud_identity_*,
# tenant_vulnerability_*, tenant_ndr_*, tenant_threat_intel_*
```

Wipe restore staging on USB when done:

```bash
rm -rf "$RESTORE_STAGING"
```

---

## 5. Service orchestration

```bash
cd /opt/mssp-control
docker compose up -d --build
docker compose up -d --build --force-recreate backend-api frontend-admin frontend-customer
docker compose ps
```

Health gate (loop until OK, max ~2 minutes):

```bash
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health | jq -e '.database=="ok" and .redis=="ok"' >/dev/null; then
    echo HEALTH_OK; break
  fi
  sleep 4
done
```

Engine VMs (101/102/106/109): restore remote tar captures from staging `remote/vm*.tar.gz` onto those hosts only when those VMs were rebuilt; otherwise reconnect adapters using restored `.env` / `.secrets`. Do **not** install new SOC tools unless a named KB allows it.

---

## 6. Verification smoke test (acceptance)

Cursor must run all of these and fix failures in-session:

```bash
# API
curl -fsS http://127.0.0.1:8000/health | jq .

# Portals via nginx (expect 401 on bad login — not 502/405)
curl -sS -o /dev/null -w "admin %{http_code}\n" -X POST http://127.0.0.1:3000/api/auth/login \
  -H 'Content-Type: application/json' -d '{"email":"x","password":"y"}'
curl -sS -o /dev/null -w "customer %{http_code}\n" -X POST http://127.0.0.1:3001/api/auth/login \
  -H 'Content-Type: application/json' -d '{"email":"x","password":"y"}'

# Static portals
for p in 3000 3001; do curl -sS -o /dev/null -w ":$p %{http_code}\n" http://127.0.0.1:$p/; done
```

Catalog / entitlements (use a real admin JWT; do not paste secrets):

- Confirm customer Service Portfolio can show Cards 1–10.
- Phase engines ACTIVE when data present: Compliance, EASM, ITDR, VMaaS, NDR, Threat Intel (Cards 5,9,10,4,6,7).

Optional admin syncs if DB restored but engines empty:

```text
POST /admin/ndr/{tenant}/sync
POST /admin/threat-intel/{tenant}/sync
POST /admin/vmaas/{tenant}/sync
… (other phase sync routes as deployed)
```

**Pass criteria:** health OK, portals 200, login paths not 502, schema through `027`, no secret leakage in git status.

---

## 7. Mode B — Rebuild from Git only

When no USB backup is available:

1. Follow §3.1 clone.
2. Recreate `.env` + `.secrets` from offline vault (not from Git).
3. `docker compose up -d --build` — Postgres init applies `postgres/init/001`…`027` automatically on **empty** volume.
4. Re-run Admin onboarding / phase syncs to repopulate tenant data.
5. Smoke test §6.

Data loss vs Mode A: tenant history not restored unless a DB dump is later applied.

---

## 8. Creating backups (Cursor / operator)

On VM 100, with USB shared from `192.168.0.192`:

```bash
cd /opt/mssp-control
# One-time: Windows user + password file (gitignored)
# echo -n 'WINDOWSPASS' > .secrets/dr_smb_password && chmod 600 .secrets/dr_smb_password
export MSSP_DR_SMB_USER='<windows-user>'
export MSSP_DR_SMB_PASSWORD_FILE=/opt/mssp-control/.secrets/dr_smb_password
python3 scripts/dr_backup_engine.py --mount-smb
```

If the share is already mounted at `/mnt/mssp-dr-usb/MSSP_Full_Backup`:

```bash
export MSSP_DR_BACKUP_ROOT=/mnt/mssp-dr-usb/MSSP_Full_Backup
python3 scripts/dr_backup_engine.py
```

Outputs on USB:

- `MSSP_FULL_STACK_BACKUP_<TS>.sql.gz.enc` (AES-256-CBC, mode 440, best-effort immutable)
- `*.sha256`
- `infrastructure_manifest.json`

Passphrase file (restore key): `.secrets/dr_backup_passphrase` — **back up offline separately**.

---

## 9. Windows host prep checklist (192.168.0.192)

1. Insert USB; confirm drive letter `F:`.
2. Create folder `F:\MSSP_Full_Backup`.
3. Share it as SMB name **`MSSP_Full_Backup`** (Read/Write for the backup account).
4. Allow File and Printer Sharing / SMB on the LAN profile.
5. From VM 100, confirm `TCP 445` to `192.168.0.192` (already validated in lab).
6. Provide Cursor with Windows username; store password only in `.secrets/dr_smb_password` on VM 100.

---

## 10. Cursor session checklist (copy/paste)

When asked to redeploy from USB:

- [ ] Mount or resolve `MSSP_DR_BACKUP_ROOT` to USB content
- [ ] `sha256sum -c` on latest archive
- [ ] Decrypt+extract to USB staging (not `/tmp`)
- [ ] Restore `.env` / `.secrets` without printing
- [ ] Start postgres/redis; stream `pg_dumpall` restore
- [ ] `docker compose up -d --build` + recreate both frontends
- [ ] Health + portal smoke (§6)
- [ ] Remove plaintext staging on USB
- [ ] `git status` clean of secrets
