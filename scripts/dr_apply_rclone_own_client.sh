#!/usr/bin/env bash
# Apply a dedicated Google OAuth client_id/secret to the local rclone `gdrive` remote.
# Reads /opt/mssp-control/.secrets/rclone_google_oauth.env (never commit that file):
#   RCLONE_DRIVE_CLIENT_ID=....apps.googleusercontent.com
#   RCLONE_DRIVE_CLIENT_SECRET=...
#
# After writing client_id/secret into rclone.conf, runs `rclone config reconnect gdrive:`
# (needs a one-time browser login on this host, or RCLONE_CONFIG_PASS / headless auth).
set -euo pipefail

SECRET_ENV="${MSSP_RCLONE_OAUTH_ENV:-/opt/mssp-control/.secrets/rclone_google_oauth.env}"
REMOTE="${MSSP_DR_RCLONE_REMOTE:-gdrive}"

[[ -f "$SECRET_ENV" ]] || {
  echo "Missing $SECRET_ENV" >&2
  echo "Create it with RCLONE_DRIVE_CLIENT_ID and RCLONE_DRIVE_CLIENT_SECRET from Google Cloud Console" >&2
  echo "(Desktop OAuth client, Drive API enabled). See docs/DR_GOOGLE_DRIVE_BACKUP_SETUP.md" >&2
  exit 1
}

# shellcheck disable=SC1090
source "$SECRET_ENV"
[[ -n "${RCLONE_DRIVE_CLIENT_ID:-}" && -n "${RCLONE_DRIVE_CLIENT_SECRET:-}" ]] || {
  echo "RCLONE_DRIVE_CLIENT_ID / RCLONE_DRIVE_CLIENT_SECRET must be set in $SECRET_ENV" >&2
  exit 1
}

rclone config update "$REMOTE" client_id "$RCLONE_DRIVE_CLIENT_ID" client_secret "$RCLONE_DRIVE_CLIENT_SECRET"
echo "Updated $REMOTE client_id. Reconnecting (browser may open)…"
rclone config reconnect "$REMOTE:"
rclone about "$REMOTE:"
echo "OK — $REMOTE no longer uses rclone shared client_id"
