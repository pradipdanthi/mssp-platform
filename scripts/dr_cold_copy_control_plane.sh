#!/usr/bin/env bash
# Cold-copy /opt/mssp-control (full tree including .env/.secrets/.git) into a DR folder.
# Intended for Path A offline/USB backup. Never commit the destination into Git.
set -euo pipefail

SRC="${MSSP_CONTROL_ROOT:-/opt/mssp-control}"
DEST_ROOT="${1:-${MSSP_DR_COLD_ROOT:-/home/secadmin/MSSP_Full_Backup}}"
DEST="${DEST_ROOT%/}/mssp-control"

if [[ ! -d "$SRC" ]]; then
  echo "Source missing: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"
echo "[dr-cold-copy] $SRC → $DEST"

# Prefer rsync; fall back to tar (rsync may be absent on minimal hosts)
if command -v rsync >/dev/null 2>&1; then
  mkdir -p "$DEST"
  rsync -aH --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.venv/' \
    --exclude 'frontend-admin/node_modules/' \
    --exclude 'frontend-customer/node_modules/' \
    --exclude 'frontend-admin/dist/' \
    --exclude 'frontend-customer/dist/' \
    --exclude '.staging_*/' \
    --exclude 'runtime/vuln-free/' \
    "$SRC/" "$DEST/"
else
  rm -rf "$DEST"
  mkdir -p "$DEST"
  tar -C "$SRC" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='frontend-admin/node_modules' \
    --exclude='frontend-customer/node_modules' \
    --exclude='frontend-admin/dist' \
    --exclude='frontend-customer/dist' \
    --exclude='runtime/vuln-free' \
    -cf - . | tar -C "$DEST" -xf -
fi

# Operator README (no secrets)
cat > "${DEST_ROOT%/}/README_RESTORE.txt" <<'EOF'
MSSP Disaster Recovery package
==============================

This folder supports TWO restore paths. Tell Cursor which path and the folder path.

PATH A — Full offline package (fastest after total loss)
  Contains:
    - mssp-control/     full control-plane tree (.env, .secrets, code, ansible, git)
    - MSSP_FULL_STACK_BACKUP_*.sql.gz.enc   encrypted DB + engine configs
    - matching .sha256 + infrastructure_manifest.json
  Prompt example:
    Restore the entire MSSP stack from /home/secadmin/MSSP_Full_Backup (Path A).
    Create VMs on Proxmox, redeploy engines with ansible, restore DB from the .enc archive.

PATH B — Git-only rebuild (when GitHub is safe but local VMs are gone)
  Requires: git clone of mssp-platform + secrets/DB from this USB (or vault).
  Prompt example:
    Rebuild the entire MSSP platform from Git (Path B), using secrets/DB from
    F:\MSSP_Full_Backup. Provision VMs, harden OS, install engines, bring control plane online.

IMPORTANT
  - Keep dr_backup_passphrase (inside mssp-control/.secrets/) offline with this package.
  - Never commit this folder or .env/.secrets to a public remote.
  - Heavy Greenbone feed DBs may re-download after rebuild (hours); product DB comes from .enc.
EOF

# Snapshot sizes
{
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source=$SRC"
  echo "dest=$DEST"
  du -sh "$DEST" "$DEST_ROOT"/MSSP_FULL_STACK_BACKUP_*.sql.gz.enc 2>/dev/null || true
} > "${DEST_ROOT%/}/COLD_COPY_META.txt"

echo "[dr-cold-copy] DONE"
echo "[dr-cold-copy] WinSCP path: $DEST_ROOT"
du -sh "$DEST" "$DEST_ROOT"
ls -la "$DEST_ROOT" | head -30
