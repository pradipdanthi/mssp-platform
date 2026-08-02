#!/usr/bin/env bash
# MSSP scheduled full DR backup (dated folders, no overwrite).
# Creates local copy under ~/MSSP_Backups/<timestamp>/ and optionally uploads to Google Drive via rclone.
#
# Never commits secrets. Never prints passphrase/.env contents.
set -euo pipefail

REPO_ROOT="${MSSP_CONTROL_ROOT:-/opt/mssp-control}"
CONFIG="${MSSP_DR_SCHEDULE_ENV:-$HOME/.config/mssp-dr/backup.env}"
if [[ -f "$CONFIG" ]]; then
  # shellcheck disable=SC1090
  set -a
  # Only load KEY=value lines (no command substitution)
  # shellcheck disable=SC1091
  source "$CONFIG"
  set +a
fi

LOCAL_ROOT="${MSSP_DR_LOCAL_ROOT:-$HOME/MSSP_Backups}"
KEEP_LOCAL="${MSSP_DR_KEEP_LOCAL:-7}"
RCLONE_REMOTE="${MSSP_DR_RCLONE_REMOTE:-gdrive}"
# One place on Google Drive (under the MSSP folder).
RCLONE_PATH="${MSSP_DR_RCLONE_PATH:-MSSP/MSSP_Backups}"
ENABLE_GDRIVE="${MSSP_DR_ENABLE_GDRIVE:-0}"
PASSFILE="${MSSP_DR_BACKUP_PASSPHRASE_FILE:-$REPO_ROOT/.secrets/dr_backup_passphrase}"
LOG_DIR="${MSSP_DR_LOG_DIR:-$HOME/MSSP_Backups/logs}"
STATUS_FILE="${MSSP_DR_STATUS_FILE:-$LOCAL_ROOT/STATUS.json}"
LOCK_FILE="${MSSP_DR_LOCK_FILE:-$LOCAL_ROOT/BACKUP_RUNNING.lock}"
TS="$(date -u +%Y-%m-%d_%H%M%SZ)"
DEST="$LOCAL_ROOT/$TS"
LOG_FILE="$LOG_DIR/backup_${TS}.log"

mkdir -p "$LOCAL_ROOT" "$LOG_DIR" "$DEST"

write_status() {
  local state="$1"
  local message="${2:-}"
  local finished_at=""
  if [[ "$state" != "running" ]]; then
    finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi
  cat > "$STATUS_FILE" <<EOF
{
  "state": "$state",
  "message": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$message"),
  "timestamp_utc": "$TS",
  "started_at_utc": "${STARTED_AT_UTC:-}",
  "finished_at_utc": "$finished_at",
  "pid": $$,
  "local_path": "$DEST",
  "log_file": "$LOG_FILE",
  "gdrive_enabled": "$ENABLE_GDRIVE",
  "gdrive_path": "${RCLONE_REMOTE}:${RCLONE_PATH%/}/$TS",
  "host": "$(hostname)"
}
EOF
  chmod 644 "$STATUS_FILE" 2>/dev/null || true
}

cleanup_lock() {
  rm -f "$LOCK_FILE" 2>/dev/null || true
}

on_exit() {
  local rc=$?
  trap - EXIT
  if [[ $rc -eq 0 ]]; then
    write_status "success" "Backup finished successfully"
  else
    write_status "failed" "Backup failed (exit $rc) — see $LOG_FILE"
  fi
  cleanup_lock
}

if [[ -f "$LOCK_FILE" ]]; then
  old_pid="$(awk '{print $1}' "$LOCK_FILE" 2>/dev/null || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "BACKUP ALREADY RUNNING (pid=$old_pid). See $STATUS_FILE"
    exit 0
  fi
  rm -f "$LOCK_FILE"
fi

STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "$$ $STARTED_AT_UTC $TS" > "$LOCK_FILE"
write_status "running" "Full DR backup in progress"
trap on_exit EXIT

exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[dr-scheduled $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

die() { log "FAILED: $*"; exit 1; }

[[ -d "$REPO_ROOT" ]] || die "Repo missing: $REPO_ROOT"
[[ -f "$PASSFILE" ]] || die "Passphrase file missing: $PASSFILE"
[[ -x "$REPO_ROOT/scripts/dr_backup_engine.py" || -f "$REPO_ROOT/scripts/dr_backup_engine.py" ]] || die "dr_backup_engine.py missing"
[[ -f "$REPO_ROOT/scripts/dr_cold_copy_control_plane.sh" ]] || die "cold copy script missing"

log "Starting dated backup → $DEST"

export MSSP_DR_BACKUP_PASSPHRASE_FILE="$PASSFILE"
export MSSP_DR_BACKUP_ROOT="$DEST"

# 1) Encrypted stack archive (DB + engine configs) into DEST
log "Step 1/4: encrypted stack backup (dr_backup_engine.py)"
python3 "$REPO_ROOT/scripts/dr_backup_engine.py" --backup-root "$DEST" \
  || die "dr_backup_engine.py failed"

# 2) Full /opt/mssp-control cold copy into DEST/mssp-control
log "Step 2/4: cold-copy control plane tree"
bash "$REPO_ROOT/scripts/dr_cold_copy_control_plane.sh" "$DEST" \
  || die "cold copy failed"

# 3) Encrypted SSH keys sidecar (same passphrase)
log "Step 3/4: pack SSH keys"
if [[ -d "$HOME/.ssh" ]]; then
  export MSSP_DR_OPENSSL_PASS
  MSSP_DR_OPENSSL_PASS="$(tr -d '\r\n' < "$PASSFILE")"
  tar -C "$HOME" -czf - .ssh \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:MSSP_DR_OPENSSL_PASS \
    > "$DEST/ssh_keys_secadmin.tar.gz.enc"
  unset MSSP_DR_OPENSSL_PASS
  (
    cd "$DEST"
    sha256sum ssh_keys_secadmin.tar.gz.enc > ssh_keys_secadmin.tar.gz.enc.sha256
  )
else
  log "WARNING: $HOME/.ssh missing — SSH keys not packed"
fi

# Copy disaster memory / inventory into DEST root if present in cold tree
for f in CURSOR_DISASTER_MEMORY.md MSSP_IP_PROXMOX_INVENTORY.md README_RESTORE.txt; do
  if [[ -f "$DEST/mssp-control/DOCS/$f" ]]; then
    cp -f "$DEST/mssp-control/DOCS/$f" "$DEST/$f" 2>/dev/null || true
  elif [[ -f "$REPO_ROOT/DOCS/$f" ]]; then
    cp -f "$REPO_ROOT/DOCS/$f" "$DEST/$f" 2>/dev/null || true
  fi
done

# Marker
cat > "$DEST/BACKUP_COMPLETE.txt" <<EOF
timestamp_utc=$TS
host=$(hostname)
repo=$REPO_ROOT
git_head=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)
EOF

cat > "$DEST/READ_ME_FIRST_RESTORE.txt" <<EOF
MSSP FULL-STACK RESTORE — READ THIS FIRST
=========================================

This ONE folder is a complete Path A disaster package (timestamp $TS).

Required contents (all must be present):
  1) MSSP_FULL_STACK_BACKUP_*.sql.gz.enc   (+ matching .sha256)
  2) mssp-control/                        (code, .env, .secrets, ansible)
  3) ssh_keys_secadmin.tar.gz.enc         (+ matching .sha256)
  4) MSSP_IP_PROXMOX_INVENTORY.md
  5) CURSOR_DISASTER_MEMORY.md

Tell Cursor exactly:
  Path A: Restore the entire MSSP stack from $DEST

Do NOT mix files from different dated folders.
Do NOT use leftover .old_backups or partial uploads.

If restoring from Google Drive:
  Download $TS.tar.gz from gdrive:MSSP/MSSP_Backups/$TS/
  tar -xzf $TS.tar.gz
  then use the extracted folder as this package.
EOF

# Keep disaster memory current inside every package
if [[ -f "$REPO_ROOT/DOCS/CURSOR_DISASTER_MEMORY.md" ]]; then
  cp -f "$REPO_ROOT/DOCS/CURSOR_DISASTER_MEMORY.md" "$DEST/CURSOR_DISASTER_MEMORY.md"
fi
if [[ -f "$REPO_ROOT/DOCS/MSSP_IP_PROXMOX_INVENTORY.md" ]]; then
  cp -f "$REPO_ROOT/DOCS/MSSP_IP_PROXMOX_INVENTORY.md" "$DEST/MSSP_IP_PROXMOX_INVENTORY.md"
elif [[ -f "$HOME/MSSP_Full_Backup/MSSP_IP_PROXMOX_INVENTORY.md" ]]; then
  cp -f "$HOME/MSSP_Full_Backup/MSSP_IP_PROXMOX_INVENTORY.md" "$DEST/MSSP_IP_PROXMOX_INVENTORY.md"
fi

SIZE="$(du -sh "$DEST" | awk '{print $1}')"
log "Local backup complete: $DEST ($SIZE)"

# Update "latest" pointer (symlink) without deleting old dated folders
ln -sfn "$DEST" "$LOCAL_ROOT/LATEST"

# 4) Google Drive: upload ONE tar.gz into a new dated folder (never overwrite prior stamps).
#    File-by-file copy of mssp-control (~thousands of tiny files) is extremely slow on Drive API.
export PATH="${HOME}/.local/bin:${HOME}/bin:/usr/local/bin:${PATH}"
RCLONE_BIN="${MSSP_DR_RCLONE_BIN:-$(command -v rclone || true)}"
if [[ "$ENABLE_GDRIVE" == "1" ]]; then
  [[ -n "$RCLONE_BIN" && -x "$RCLONE_BIN" ]] || die "rclone not installed (needed for Google Drive)"
  "$RCLONE_BIN" listremotes | grep -qx "${RCLONE_REMOTE}:" \
    || die "rclone remote '${RCLONE_REMOTE}:' not configured — finish Google Drive linking first"

  ARCHIVE="${LOCAL_ROOT}/${TS}.tar.gz"
  log "Step 4/4: pack single archive for Drive → $ARCHIVE"
  tar -C "$LOCAL_ROOT" -czf "$ARCHIVE" "$TS" || die "tar for Drive upload failed"
  ARCHIVE_SIZE="$(du -sh "$ARCHIVE" | awk '{print $1}')"
  log "Archive ready ($ARCHIVE_SIZE); uploading to Google Drive"

  REMOTE_DEST="${RCLONE_REMOTE}:${RCLONE_PATH%/}/$TS"
  "$RCLONE_BIN" mkdir "${RCLONE_REMOTE}:${RCLONE_PATH%/}" 2>/dev/null || true
  "$RCLONE_BIN" mkdir "$REMOTE_DEST" 2>/dev/null || true
  "$RCLONE_BIN" copy "$ARCHIVE" "$REMOTE_DEST/" --retries 5 --low-level-retries 10 \
    || die "rclone upload failed"

  # Keep local dated folder; remove only the temporary Drive transfer archive (optional keep)
  if [[ "${MSSP_DR_KEEP_LOCAL_TAR:-0}" != "1" ]]; then
    rm -f "$ARCHIVE"
  fi
  log "Google Drive upload OK: $REMOTE_DEST/${TS}.tar.gz (local folder kept at $DEST)"
else
  log "Step 4/4: Google Drive skipped (MSSP_DR_ENABLE_GDRIVE!=1). Local-only backup kept at $DEST"
fi

# Retention: keep newest KEEP_LOCAL dated folders (not logs/, not LATEST, not stray *.tar.gz)
log "Applying local retention KEEP_LOCAL=$KEEP_LOCAL"
mapfile -t OLD < <(find "$LOCAL_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort -r | tail -n +$((KEEP_LOCAL + 1)) || true)
for d in "${OLD[@]:-}"; do
  [[ -n "$d" ]] || continue
  log "Prune old local backup: $d"
  rm -rf "$d"
  rm -f "${d}.tar.gz" 2>/dev/null || true
done
# Clean orphan transfer tars whose folder was already pruned
find "$LOCAL_ROOT" -mindepth 1 -maxdepth 1 -type f -name '20*.tar.gz' | while read -r tarf; do
  base="${tarf%.tar.gz}"
  [[ -d "$base" ]] || { log "Prune orphan Drive tar: $tarf"; rm -f "$tarf"; }
done

log "SUCCESS"
echo "LOCAL_PATH=$DEST"
echo "SIZE=$SIZE"
