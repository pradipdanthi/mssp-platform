#!/usr/bin/env bash
# Lab engine cleanup: Wazuh alert indices, TheHive graph reset, Greenbone tasks/targets, Suricata eve.
# Does NOT touch MSSP PostgreSQL — run purge_test_data.py first for control-plane data.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

THEHIVE_FULL_RESET="${THEHIVE_FULL_RESET:-1}"

echo "==> Wazuh: delete wazuh-alerts-* indices on VM 101 (keeps state/monitoring indices)"
ssh -o BatchMode=yes wazuh-stack 'sudo bash -s' <<'REMOTE'
set -euo pipefail
PASSFILE=$(mktemp)
sudo tar -xOf /root/wazuh-install/wazuh-install-files.tar wazuh-install-files/wazuh-passwords.txt > "$PASSFILE"
ADMIN_USER=$(grep -m1 "indexer_username:" "$PASSFILE" | sed "s/.*'\([^']*\)'.*/\1/")
ADMIN_PASS=$(grep -m1 "indexer_password:" "$PASSFILE" | sed "s/.*'\([^']*\)'.*/\1/")
rm -f "$PASSFILE"
INDICES=$(curl -sk -u "${ADMIN_USER}:${ADMIN_PASS}" "https://127.0.0.1:9200/_cat/indices?h=index" | grep -E '^wazuh-alerts' || true)
for idx in $INDICES; do
  curl -sk -u "${ADMIN_USER}:${ADMIN_PASS}" -X DELETE "https://127.0.0.1:9200/${idx}" >/dev/null
  echo "  deleted $idx"
done
echo "WAZUH_ALERT_INDICES_OK"
REMOTE

echo "==> Suricata: truncate eve.json on VM 106"
ssh -o BatchMode=yes suricata-sensor 'sudo bash -s' <<'REMOTE'
set -euo pipefail
EVE=/var/log/suricata/eve.json
[ -f "$EVE" ] || { echo "no eve.json"; exit 0; }
: > "$EVE"
systemctl reload suricata 2>/dev/null || systemctl restart suricata 2>/dev/null || true
echo "SURICATA_EVE_OK bytes=$(stat -c%s "$EVE")"
REMOTE

echo "==> Greenbone: delete tasks/targets/reports in gvmd DB on VM 109"
ssh -o BatchMode=yes greenbone 'sudo docker exec greenbone-community-edition-pg-gvm-1 psql -U gvmd -d gvmd -v ON_ERROR_STOP=1 -c "
DELETE FROM report_host_details;
DELETE FROM report_hosts;
DELETE FROM report_counts;
DELETE FROM results_trash;
DELETE FROM results;
DELETE FROM reports;
DELETE FROM task_alerts;
DELETE FROM task_files;
DELETE FROM task_preferences;
DELETE FROM permissions_get_tasks;
DELETE FROM tasks;
DELETE FROM targets_login_data;
DELETE FROM targets;
"'
echo "GREENBONE_SCAN_DATA_OK"

if [ "$THEHIVE_FULL_RESET" = "1" ]; then
  echo "==> TheHive: full volume reset on VM 102 (fresh graph; re-create org/users in UI)"
  ssh -o BatchMode=yes thehive 'sudo bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/mssp-case-soar/thehive
docker compose down
for v in $(docker volume ls --format '{{.Name}}' | grep -E '^thehive_'); do
  docker volume rm "$v" || true
done
docker compose up -d
for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9000/api/status 2>/dev/null || echo 0)
  [ "$code" = "200" ] && break
  sleep 5
done
curl -s -o /dev/null -w "THEHIVE_HTTP=%{http_code}\n" http://127.0.0.1:9000/api/status
REMOTE
else
  echo "==> TheHive: skip full reset (set THEHIVE_FULL_RESET=0 to skip next time)"
fi

echo "ENGINE_LAB_PURGE_OK"
