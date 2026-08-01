# Google Drive + cron backup setup (MSSP)

Status: Operator setup guide for automated dated backups.  
Local path: `/home/secadmin/MSSP_Backups/<YYYY-MM-DD_HHMMSSZ>/`  
Remote path: Google Drive → `MSSP_Backups/<same timestamp>/`  
Scripts: `scripts/dr_scheduled_backup.sh`, `scripts/dr_install_backup_cron.sh`

Backups **never overwrite** a previous run — each run creates a new timestamp folder.

---

## What Cursor needs from you

Provide / complete these (no passwords in chat if you can avoid it):

| # | Item | Notes |
|---|---|---|
| 1 | **Google account** with enough Drive free space | Same account you want backups in |
| 2 | **rclone access** (one-time browser login) **or** a **Google Cloud service account JSON** | See options below |
| 3 | **Drive folder name** | Default: `MSSP_Backups` (created automatically) |
| 4 | **Schedule preference** | Default: every day at **02:15** server time |
| 5 | **How many local copies to keep** | Default: **7** dated folders on the control plane |
| 6 | Confirm passphrase file still exists | `/opt/mssp-control/.secrets/dr_backup_passphrase` |

You do **not** need to share your Google password with Cursor if you use Option A (interactive rclone) on the server yourself.

---

## Option A — rclone interactive (simplest)

On VM 100 (`secadmin`):

```bash
# Install rclone if missing
curl -fsSL https://rclone.org/install.sh | sudo bash
# or: sudo apt-get install -y rclone

rclone config
```

In the wizard:
1. `n` new remote  
2. Name: `gdrive`  
3. Storage: `drive` (Google Drive)  
4. Scope: full Drive (or drive.file)  
5. Follow the **browser link** to authorize  
6. Confirm remote `gdrive:` works:

```bash
rclone lsd gdrive:
rclone mkdir gdrive:MSSP_Backups
```

Then:

```bash
nano ~/.config/mssp-dr/backup.env
# set: MSSP_DR_ENABLE_GDRIVE=1

bash /opt/mssp-control/scripts/dr_install_backup_cron.sh
bash /opt/mssp-control/scripts/dr_scheduled_backup.sh
```

---

## Option B — service account (good for unattended servers)

1. In Google Cloud Console: create a project → enable **Google Drive API**.  
2. Create a **Service account** → download JSON key.  
3. Create a Drive folder `MSSP_Backups` in your Google account.  
4. **Share that folder** with the service account email (`...@....iam.gserviceaccount.com`) as Editor.  
5. Put the JSON on VM 100 (example):

```bash
install -m 600 /path/to/sa.json /opt/mssp-control/.secrets/gdrive_service_account.json
```

6. Configure rclone remote `gdrive` using that JSON (`service_account_file`).  
7. Set `MSSP_DR_ENABLE_GDRIVE=1` and run the install/test commands from Option A.

---

## What each backup folder contains

Same package as Path A cold DR:

- `MSSP_FULL_STACK_BACKUP_*.sql.gz.enc` + `.sha256`
- `mssp-control/` (code, `.env`, `.secrets`, ansible)
- `ssh_keys_secadmin.tar.gz.enc` + `.sha256`
- `infrastructure_manifest.json`, `CURSOR_DISASTER_MEMORY.md`, inventory docs

Local layout:

```text
/home/secadmin/MSSP_Backups/
  2026-08-01_083015Z/     ← one full backup (never overwritten)
  2026-08-02_083015Z/
  LATEST → symlink to newest
  logs/
```

Google Drive mirrors each timestamp under `MSSP/MSSP_Backups/<timestamp>/` as a **single**  
`<timestamp>.tar.gz` (fast). The control plane still keeps the full unpacked folder locally.  
Restore from Drive: download the tar → `tar -xzf <timestamp>.tar.gz`.

---

## Schedule (systemd timer — preferred)

Installed by `dr_install_backup_cron.sh` for user `secadmin`:

```bash
systemctl --user status mssp-dr-backup.timer
systemctl --user list-timers | grep mssp-dr
```

Default: daily at **02:15** local time (`OnCalendar=*-*-* 02:15:00`).  
Override when installing: `MSSP_DR_ON_CALENDAR='*-*-* 03:00:00' bash scripts/dr_install_backup_cron.sh`

So the timer still runs when nobody is logged in:

```bash
sudo loginctl enable-linger secadmin
```

If the `cron` package is installed, the same script also adds a crontab line as a backup.

---

## Security

- Do **not** commit `~/.config/mssp-dr/backup.env`, rclone tokens, or service account JSON to Git.  
- Drive copies contain secrets (encrypted archives + cold tree with `.env`). Treat the Drive folder as confidential.  
- Prefer a dedicated Google account or a private Shared Drive folder.

---

## After you finish Google auth

Tell Cursor:

> Google Drive rclone remote `gdrive` is ready — enable Drive upload and install the daily backup cron.

Then Cursor will flip `MSSP_DR_ENABLE_GDRIVE=1`, install cron, and run one test backup.
