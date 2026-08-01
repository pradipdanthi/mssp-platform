#!/usr/bin/env bash
# Install MSSP dated backup as a systemd user timer (preferred) or crontab.
# Does NOT configure Google Drive — see DOCS/DR_GOOGLE_DRIVE_BACKUP_SETUP.md
set -euo pipefail

REPO_ROOT="${MSSP_CONTROL_ROOT:-/opt/mssp-control}"
SCRIPT="$REPO_ROOT/scripts/dr_scheduled_backup.sh"
CONFIG_DIR="${HOME}/.config/mssp-dr"
CONFIG="$CONFIG_DIR/backup.env"
UNIT_DIR="${HOME}/.config/systemd/user"
# Default: daily 02:15 local time (OnCalendar)
ON_CALENDAR="${MSSP_DR_ON_CALENDAR:-*-*-* 02:15:00}"
CRON_EXPR="${MSSP_DR_CRON_EXPR:-15 2 * * *}"

chmod +x "$SCRIPT" "$REPO_ROOT/scripts/dr_cold_copy_control_plane.sh" || true
mkdir -p "$CONFIG_DIR" "$HOME/MSSP_Backups/logs" "$UNIT_DIR"

if [[ ! -f "$CONFIG" ]]; then
  cat > "$CONFIG" <<'EOF'
# MSSP scheduled backup settings (not for Git)
MSSP_CONTROL_ROOT=/opt/mssp-control
MSSP_DR_LOCAL_ROOT=/home/secadmin/MSSP_Backups
MSSP_DR_KEEP_LOCAL=7
MSSP_DR_BACKUP_PASSPHRASE_FILE=/opt/mssp-control/.secrets/dr_backup_passphrase

# Google Drive via rclone (set to 1 after rclone remote is ready)
MSSP_DR_ENABLE_GDRIVE=0
MSSP_DR_RCLONE_REMOTE=gdrive
MSSP_DR_RCLONE_PATH=MSSP_Backups
EOF
  chmod 600 "$CONFIG"
  echo "Created $CONFIG (edit ENABLE_GDRIVE=1 after rclone setup)"
fi

# --- systemd user timer (preferred; cron package often missing) ---
cat > "$UNIT_DIR/mssp-dr-backup.service" <<EOF
[Unit]
Description=MSSP dated full DR backup (local + optional Google Drive)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
Environment=PATH=%h/.local/bin:%h/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=-%h/.config/mssp-dr/backup.env
ExecStart=$SCRIPT
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
EOF

cat > "$UNIT_DIR/mssp-dr-backup.timer" <<EOF
[Unit]
Description=Daily MSSP DR backup timer

[Timer]
OnCalendar=$ON_CALENDAR
Persistent=true
RandomizedDelaySec=5m

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now mssp-dr-backup.timer
echo "systemd user timer installed:"
systemctl --user list-timers --all | grep -E 'mssp-dr-backup|NEXT' || systemctl --user status mssp-dr-backup.timer --no-pager || true

echo
echo "IMPORTANT: so backups run when you are logged out, run once (needs your sudo password):"
echo "  sudo loginctl enable-linger $USER"
echo

# Optional crontab if available
if command -v crontab >/dev/null 2>&1; then
  TMP=$(mktemp)
  crontab -l 2>/dev/null | grep -v 'dr_scheduled_backup.sh' > "$TMP" || true
  echo "$CRON_EXPR $SCRIPT >> $HOME/MSSP_Backups/logs/cron.log 2>&1" >> "$TMP"
  crontab "$TMP"
  rm -f "$TMP"
  echo "Also installed crontab line:"
  crontab -l | grep dr_scheduled_backup || true
else
  echo "crontab not installed — using systemd timer only (OK)."
fi

echo
echo "Config: $CONFIG"
echo "Local backups: $HOME/MSSP_Backups/<timestamp>/"
echo "Next: complete Google Drive setup in DOCS/DR_GOOGLE_DRIVE_BACKUP_SETUP.md"
echo "Then set MSSP_DR_ENABLE_GDRIVE=1 in $CONFIG"
echo "Test now: $SCRIPT"
echo "Manual run via systemd: systemctl --user start mssp-dr-backup.service"
