# Cursor Disaster Memory — Mandatory Restore Checklist

Status: **Read this FIRST** whenever the operator asks to rebuild after a disaster.  
Created: 2026-08-01  
Audience: Cursor (and operator reminders)

This file exists so the operator can forget details and still get a full rebuild.  
**If anything below is missing from the conversation, YOU must remind them.**

---

## Operator one-liner (expected)

> Path A: Restore the entire MSSP stack from `<COMPLETE_BACKUP_FOLDER>`.  
> Proxmox was wiped / reinstalled. Bring everything back online.

`<COMPLETE_BACKUP_FOLDER>` is **one** folder that already contains everything below.  
Examples (any **one** complete package — do not mix folders):

- `/home/secadmin/MSSP_Backups/LATEST` (recommended local pointer)
- `/home/secadmin/MSSP_Backups/2026-08-01_093514Z` (any dated full run)
- Extracted Google Drive archive: `MSSP/MSSP_Backups/<timestamp>/<timestamp>.tar.gz` → extract → use that folder
- Older USB copy: `/home/secadmin/MSSP_Full_Backup` **only if** it still has the required files listed below

Also accept: “rebuild from backup”, “disaster recovery”, “bare metal restore”.

---

## What the operator must bring

**One complete package folder** (not scattered files from different dates):

| Item inside that folder | Why |
|---|---|
| `READ_ME_FIRST_RESTORE.txt` | Operator orientation |
| `MSSP_FULL_STACK_BACKUP_*.sql.gz.enc` + `.sha256` | Database + engine configs |
| `mssp-control/` | Full `/opt/mssp-control` including `.env` / `.secrets` / ansible |
| `ssh_keys_secadmin.tar.gz.enc` + `.sha256` | Deploy keys for engine VMs |
| `MSSP_IP_PROXMOX_INVENTORY.md` | Guest IPs / hostnames / VMIDs |
| `CURSOR_DISASTER_MEMORY.md` | This checklist |
| Decrypt passphrase | `mssp-control/.secrets/dr_backup_passphrase` (unlocks DB archive **and** SSH keys) |

**Never print** passphrase, `.env`, or private keys in chat.

### Anti-confusion rules (mandatory)

1. **Never mix** archives from date A with `mssp-control/` from date B.  
2. **Ignore** any `.old_backups/` leftovers — they are not part of restore (delete if found).  
3. Google Drive holds the **same** package as a single `<timestamp>.tar.gz` inside a dated folder — extract first, then treat like local.  
4. Nightly jobs create a **new** dated folder each time; they do not overwrite the previous complete package.  
5. `/home/secadmin/MSSP_Backups/LATEST` always points at the newest complete local package.

Scheduled backup details: `docs/DR_GOOGLE_DRIVE_BACKUP_SETUP.md`.

---

## Remind the operator (even if they forget)

1. **Proxmox must be reinstalled first** on the physical server (backup of Proxmox host is optional; installer ISO is enough).  
2. **Proxmox management IP can be NEW.**  
3. **Guest VM IPs and hostnames should stay the SAME** (see inventory table).  
4. **Ubuntu Server LTS ISO** must be in Proxmox storage (download/upload if missing).  
5. **Same LAN subnet** `192.168.0.0/24` strongly preferred.  
6. **VM 112 (Ansible automation controller) is REQUIRED** — recreate and restore it with the other core VMs (backed up in the encrypted archive as `remote/vm112_*`).  
7. **Heavy Greenbone feeds** may re-download for hours; MSSP portals can go live before feeds finish.  
8. Re-copy USB / confirm Google Drive after any new cold-copy / key packing.  
9. After restore: smoke Admin `:3000`, Customer `:3001`, API `:8000` `/health`, and Ansible on VM 112.

---

## Bare-metal sequence Cursor MUST follow

### Phase 0 — Confirm package
```bash
ls "<BACKUP>/MSSP_FULL_STACK_BACKUP_"*.sql.gz.enc
ls "<BACKUP>/mssp-control/.env" "<BACKUP>/mssp-control/.secrets/dr_backup_passphrase"
ls "<BACKUP>/ssh_keys_secadmin.tar.gz.enc"
ls "<BACKUP>/MSSP_IP_PROXMOX_INVENTORY.md"
sha256sum -c "<BACKUP>/"*.sha256
```

### Phase 1 — Proxmox + network
- Confirm Proxmox UI/SSH works.
- Ensure `vmbr0` on `192.168.0.0/24` (capture bridge later for Suricata/Zeek if needed).
- Ensure Ubuntu Server LTS ISO present.

### Phase 2 — Create guest VMs (same IDs/IPs/names)

| VMID | Name / hostname | IP | Role |
|---:|---|---|---|
| 100 | mssp-control | 192.168.0.201 | Control plane |
| 101 | wazuh-stack | 192.168.0.211 | Wazuh |
| 102 | thehive-shuffle / thehiveshuffle | 192.168.0.212 | TheHive + Shuffle (+ Tenzir if present) |
| 106 | suricata-sensor | 192.168.0.216 | Suricata + Zeek (co-located) |
| 109 | greenbone | 192.168.0.219 | Greenbone CE + Nuclei + Vuls |
| 112 | automation | 192.168.0.222 | **Required** Ansible automation controller |
| 104 | windows-endpoint-lab | 192.168.0.214 | Optional test endpoint (not required for core MSSP) |

### Phase 3 — Restore VM 100 control plane
1. Install Docker + Compose on VM 100.  
2. Copy `mssp-control/` → `/opt/mssp-control` (preserves `.env`, `.secrets`, ansible, git).  
3. Restore SSH keys:

```bash
PASSFILE=/opt/mssp-control/.secrets/dr_backup_passphrase
export MSSP_DR_OPENSSL_PASS="$(tr -d '\r\n' < "$PASSFILE")"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:MSSP_DR_OPENSSL_PASS \
  -in "<BACKUP>/ssh_keys_secadmin.tar.gz.enc" | tar -C /home/secadmin -xzf -
unset MSSP_DR_OPENSSL_PASS
chmod 700 /home/secadmin/.ssh
chmod 600 /home/secadmin/.ssh/id_ed25519_* 2>/dev/null || true
chmod 644 /home/secadmin/.ssh/*.pub /home/secadmin/.ssh/known_hosts 2>/dev/null || true
chown -R secadmin:secadmin /home/secadmin/.ssh
```

4. Decrypt main archive; restore `pg_dumpall` into Postgres (see `docs/DISASTER_RECOVERY_PLAYBOOK.md` / Path A in `CURSOR_REDEPLOYMENT_PLAYBOOK.md`).  
5. `docker compose up -d --build` then recreate **backend + both frontends**.

### Phase 4 — Backend engines (full live set today)
From VM 100, using `/opt/mssp-control/ansible` + restored SSH keys, redeploy/configure:

| Host | Must install / restore |
|---|---|
| 101 | Wazuh Manager + Indexer + Dashboard |
| 102 | TheHive + Shuffle (and Tenzir if was present) |
| 106 | Suricata + Zeek co-located + Wazuh agent |
| 109 | Greenbone CE + Nuclei + Vuls |
| 112 | Ansible controller: restore `/home/secadmin/mssp-automation` + `/home/secadmin/.ssh` (controller deploy keys) from `remote/vm112_*` |

Apply overlays from decrypted archive `remote/` and `remote/vm*_volumes/` when present.

### Phase 5 — Control-plane service engines (in DB, not separate VMs)
Confirm Customer/Admin capabilities after DB restore:

- Compliance (SCA), EASM, ITDR, VMaaS, NDR, Threat Intelligence  

### Phase 6 — Acceptance (do not stop early)
- [ ] `curl -fsS http://192.168.0.201:8000/health` → database+redis OK  
- [ ] Admin `:3000` and Customer `:3001` load; bad login ≠ 502  
- [ ] At least one known tenant shows data  
- [ ] Engine hosts SSH’able with restored keys  
- [ ] No secrets printed; wipe plaintext decrypt staging  

---

## How / when to use `ssh_keys_secadmin.tar.gz.enc`

| When | Action |
|---|---|
| **Normal day** | Keep it next to the main `.enc` on USB/offsite; do not unpack casually |
| **After VM 100 is restored** | Decrypt with **same** `dr_backup_passphrase`, extract into `/home/secadmin/.ssh` **before** ansible to 101/102/106/109 |
| **If missing** | STOP and remind operator — engine rebuild will fail without keys or new key exchange |

Passphrase file path after control-plane restore:  
`/opt/mssp-control/.secrets/dr_backup_passphrase`

---

## Path B reminder (Git-only)

If they say “rebuild from Git”: still need this USB for **DB + secrets + SSH keys**. Git alone is code/ansible docs — not live data or private keys.

---

## Related files

- `docs/CURSOR_REDEPLOYMENT_PLAYBOOK.md` — Path A / Path B procedures  
- `docs/MSSP_BARE_METAL_RECOVERY.md` — Proxmox wipe notes  
- `docs/MSSP_IP_PROXMOX_INVENTORY.md` — IP table  
- `scripts/dr_backup_engine.py` / `scripts/dr_cold_copy_control_plane.sh` — refresh backups on a healthy system  
