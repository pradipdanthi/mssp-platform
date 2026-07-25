#!/usr/bin/env bash
# KB-070: Start (or reuse) the lab Full-and-fast scan of linux-endpoint 192.168.0.215.
set -euo pipefail

GREENBONE_SSH_HOST="${GREENBONE_SSH_HOST:-greenbone}"
TARGET_HOST="${TARGET_HOST:-192.168.0.215}"
TASK_NAME="${TASK_NAME:-mssp-lab-linux-full-and-fast}"
TARGET_NAME="${TARGET_NAME:-mssp-lab-linux-endpoint}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "$GREENBONE_SSH_HOST" \
  "TARGET_HOST='$TARGET_HOST' TASK_NAME='$TASK_NAME' TARGET_NAME='$TARGET_NAME' bash -s" <<'REMOTE'
set -euo pipefail
COMPOSE="sudo docker compose -f /opt/mssp-greenbone/community/compose.yaml -p greenbone-community-edition"
PASS="$(sudo grep -E '^GREENBONE_ADMIN_PASSWORD=' /opt/mssp-greenbone/admin.secret.env | cut -d= -f2-)"
USER="$(sudo grep -E '^GREENBONE_ADMIN_USER=' /opt/mssp-greenbone/admin.secret.env | cut -d= -f2-)"
USER="${USER:-admin}"
gmp() {
  $COMPOSE run --rm --no-deps --user 1001 --entrypoint gvm-cli gvm-tools \
    --gmp-username "$USER" --gmp-password "$PASS" \
    socket --socketpath /run/gvmd/gvmd.sock --xml "$1" 2>/dev/null
}
PORT_LIST="33d0cd82-57c6-11e1-8ed1-406186ea4fc5"
CONFIG="daba56c8-73ec-11df-a475-002264764cea"
SCANNER="08b69003-5fc2-4037-a479-93b440211c73"

TASK_ID="$(gmp "<get_tasks filter=\"name=${TASK_NAME} rows=1\"/>" | python3 -c "import sys,xml.etree.ElementTree as ET; r=ET.fromstring(sys.stdin.read()); t=r.find('task'); print(t.get('id') if t is not None else '')")"
if [ -z "$TASK_ID" ]; then
  TARGET_ID="$(gmp "<get_targets filter=\"name=${TARGET_NAME} rows=1\"/>" | python3 -c "import sys,xml.etree.ElementTree as ET; r=ET.fromstring(sys.stdin.read()); t=r.find('target'); print(t.get('id') if t is not None else '')")"
  if [ -z "$TARGET_ID" ]; then
    TARGET_ID="$(gmp "<create_target><name>${TARGET_NAME}</name><hosts>${TARGET_HOST}</hosts><port_list id=\"${PORT_LIST}\"/></create_target>" | python3 -c "import sys,xml.etree.ElementTree as ET; print(ET.fromstring(sys.stdin.read()).get('id') or '')")"
  fi
  TASK_ID="$(gmp "<create_task><name>${TASK_NAME}</name><config id=\"${CONFIG}\"/><target id=\"${TARGET_ID}\"/><scanner id=\"${SCANNER}\"/></create_task>" | python3 -c "import sys,xml.etree.ElementTree as ET; print(ET.fromstring(sys.stdin.read()).get('id') or '')")"
fi
echo "TASK_ID=$TASK_ID"
STATUS="$(gmp "<get_tasks task_id=\"${TASK_ID}\"/>" | python3 -c "import sys,xml.etree.ElementTree as ET; r=ET.fromstring(sys.stdin.read()); t=r.find('task'); print((t.findtext('status') if t is not None else '') or '')")"
echo "STATUS=$STATUS"
if [ "$STATUS" = "Running" ] || [ "$STATUS" = "Requested" ] || [ "$STATUS" = "Queued" ]; then
  echo "Scan already in progress."
  exit 0
fi
gmp "<start_task task_id=\"${TASK_ID}\"/>" | head -c 300; echo
echo "Scan start requested."
REMOTE
