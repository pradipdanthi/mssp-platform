#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

STACK_DIR="${STACK_DIR:-/home/secadmin/mssp-stack}"
REPO_DIR="${REPO_DIR:-$(pwd)}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
COMMIT_MSG="${1:-chore: export MSSP platform ${RUN_ID}}"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

for bin in git docker rsync find cp awk sed; do
  require "$bin"
done

if [ ! -d "$STACK_DIR" ]; then
  echo "STACK_DIR not found: $STACK_DIR" >&2
  exit 1
fi

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "REPO_DIR is not a git repository: $REPO_DIR" >&2
  exit 1
fi

cd "$REPO_DIR"

mkdir -p \
  docker configs deployment docs exports reports automation detections tests scripts \
  knowledge-base/{playbooks,attack-library,false-positives,linux-investigation,windows-investigation}

LOG_FILE="reports/export-${RUN_ID}.log"
: > "$LOG_FILE"

log() {
  printf '[%s] %s\n' "$(date +'%F %T')" "$*" | tee -a "$LOG_FILE"
}

copy_if_exists() {
  local src="$1"
  local dst="$2"

  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    log "Copied: $src -> $dst"
  fi
}

copy_first_match() {
  local name="$1"
  local dst="$2"
  local match=""

  match="$(find "$STACK_DIR" -type f \( -name "$name" -o -name "${name%.yml}.yaml" -o -name "${name%.yaml}.yml" \) -print -quit || true)"

  if [ -n "$match" ]; then
    mkdir -p "$dst"
    cp -a "$match" "$dst/"
    log "Copied: $match -> $dst/"
  fi
}

sanitize_env_file() {
  local src="$1"
  local dst="$2"

  mkdir -p "$(dirname "$dst")"
  : > "$dst"

  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ""|\#*)
        printf '%s\n' "$line" >> "$dst"
        ;;
      *=*)
        local key="${line%%=*}"

        if [[ "$key" =~ (PASS|PASSWORD|SECRET|TOKEN|KEY|API|PRIVATE|CERT|COOKIE|AUTH|HASH|SHARED) ]]; then
          printf '%s=__REDACTED__\n' "$key" >> "$dst"
        else
          printf '%s\n' "$line" >> "$dst"
        fi
        ;;
      *)
        printf '%s\n' "$line" >> "$dst"
        ;;
    esac
  done < "$src"

  log "Created sanitized env template: $dst"
}

log "Starting MSSP platform export"
log "STACK_DIR=$STACK_DIR"
log "REPO_DIR=$REPO_DIR"

mkdir -p "exports/source-snapshot/$RUN_ID"
mkdir -p "exports/inventory/$RUN_ID"
mkdir -p "deployment/env"

# Copy the compose files and common top-level project files.
for f in \
  docker-compose.yml \
  docker-compose.yaml \
  compose.yml \
  compose.yaml \
  docker-compose.override.yml \
  compose.override.yml \
  Dockerfile \
  .dockerignore
do
  copy_if_exists "$STACK_DIR/$f" "$REPO_DIR/docker/$f"
done

# Copy a sanitized environment template if present.
if [ -f "$STACK_DIR/.env" ]; then
  sanitize_env_file "$STACK_DIR/.env" "$REPO_DIR/deployment/env/.env.example"
fi

# Snapshot safe config-like files for archival/reference.
rsync -a --prune-empty-dirs \
  --include='*/' \
  --include='*.yml' \
  --include='*.yaml' \
  --include='*.conf' \
  --include='*.ini' \
  --include='*.xml' \
  --include='*.json' \
  --include='*.properties' \
  --include='*.toml' \
  --include='*.sh' \
  --include='*.md' \
  --include='*.service' \
  --include='*.socket' \
  --include='Dockerfile' \
  --include='.dockerignore' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='*.key' \
  --exclude='*.pem' \
  --exclude='*.p12' \
  --exclude='*.pfx' \
  --exclude='*.crt' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='*.log' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='log/' \
  --exclude='backups/' \
  --exclude='volumes/' \
  --exclude='volume/' \
  --exclude='registry/' \
  --exclude='cache/' \
  --exclude='tmp/' \
  --exclude='.git/' \
  "$STACK_DIR"/ "$REPO_DIR/exports/source-snapshot/$RUN_ID/"

# Capture inventories.
find "$STACK_DIR" -maxdepth 3 -type d | sort > "$REPO_DIR/exports/inventory/$RUN_ID/directories.txt"
find "$STACK_DIR" -maxdepth 3 -type f | sort > "$REPO_DIR/exports/inventory/$RUN_ID/files.txt"

docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' \
  > "$REPO_DIR/exports/inventory/$RUN_ID/docker-ps.txt" || true

docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}' \
  > "$REPO_DIR/exports/inventory/$RUN_ID/docker-images.txt" || true

docker network ls > "$REPO_DIR/exports/inventory/$RUN_ID/docker-networks.txt" || true
docker volume ls > "$REPO_DIR/exports/inventory/$RUN_ID/docker-volumes.txt" || true

if [ -f "$STACK_DIR/docker-compose.yml" ]; then
  docker compose -f "$STACK_DIR/docker-compose.yml" config \
    > "$REPO_DIR/exports/inventory/$RUN_ID/docker-compose-rendered.yml" 2>/dev/null || true
fi

# Copy the key component config files into organized folders as well.
copy_first_match "ossec.conf" "configs/wazuh"
copy_first_match "local_rules.xml" "configs/wazuh"
copy_first_match "decoders.xml" "configs/wazuh"
copy_first_match "client.keys" "configs/wazuh"
copy_first_match "agent.conf" "configs/wazuh"

copy_first_match "filebeat.yml" "configs/filebeat"
copy_first_match "filebeat.yaml" "configs/filebeat"

copy_first_match "opensearch.yml" "configs/opensearch"
copy_first_match "opensearch.yaml" "configs/opensearch"

copy_first_match "nginx.conf" "configs/nginx"
copy_first_match "default.conf" "configs/nginx"

copy_first_match "thehive.conf" "configs/thehive"
copy_first_match "application.conf" "configs/thehive"

copy_first_match "shuffle.yml" "configs/shuffle"
copy_first_match "shuffle.conf" "configs/shuffle"

copy_first_match "tenzir.yml" "configs/tenzir"
copy_first_match "tenzir.yaml" "configs/tenzir"

# Make a simple manifest for future deployment work.
cat > "deployment/export-manifest-${RUN_ID}.yml" <<EOF
export_run: "${RUN_ID}"
stack_dir: "${STACK_DIR}"
repo_dir: "${REPO_DIR}"
snapshot_dir: "exports/source-snapshot/${RUN_ID}"
inventory_dir: "exports/inventory/${RUN_ID}"
notes:
  - "Secrets in .env are redacted into deployment/env/.env.example"
  - "Databases, Docker volumes, and runtime logs are intentionally excluded"
  - "This repository is the source of truth for future VPS deployment"
EOF

log "Staging files in Git"
git add -A docker configs deployment docs exports reports automation detections tests scripts knowledge-base

if git diff --cached --quiet; then
  log "No changes detected; nothing to commit."
  exit 0
fi

log "Committing changes"
git commit -m "$COMMIT_MSG"

log "Pushing to GitHub"
git push origin main
log "Export complete"
