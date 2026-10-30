#!/usr/bin/env bash
# Validate TIA migrations 117 and 118 on THROWAWAY databases (never the live one).
#
# Usage (local test, needs a disposable Postgres container and the test image):
#   docker network create tia-test-net
#   docker run -d --name tia-test-pg --network tia-test-net -e POSTGRES_USER=mssp_admin \
#       -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=mssp_control postgres:16-alpine
#   docker build -t mssp-backend-test backend-api
#   ./scripts/tia_migration_validate.sh tia-test-pg
#
# Creates and drops databases named tia_mig_*. Refuses to run unless the container
# name starts with "tia-test" so it can never be pointed at the production database.
# Scenarios:
#   fresh          every init file in order (new install)
#   from116        the documented upgrade path from the currently deployed schema
#                  (through 116): 118 alone must refuse, then 117 and 118 succeed
#   from117        the increment 1 schema WITH existing review records: records and
#                  history are preserved, 118 is re-runnable, increment 1 code still works
set -uo pipefail

CONTAINER="${1:-tia-test-pg}"
PGUSER="${PGUSER_TEST:-mssp_admin}"
NETWORK="${TIA_TEST_NETWORK:-tia-test-net}"
IMAGE="${TIA_TEST_IMAGE:-mssp-backend-test}"
INIT_DIR="$(cd "$(dirname "$0")/.." && pwd)/postgres/init"

case "$CONTAINER" in
  tia-test*) ;;
  *) echo "REFUSING: container '$CONTAINER' is not a tia-test* throwaway container" >&2; exit 2 ;;
esac

PASS=0
FAIL=0
ok() { echo "PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
check() { # check <description> <command...>
  local d="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi
}

psql_db() { docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$1" -v ON_ERROR_STOP=1 -qAt "${@:2}"; }
newdb() {
  docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -qc "DROP DATABASE IF EXISTS $1;" >/dev/null 2>&1
  docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -qc "CREATE DATABASE $1;" >/dev/null
}
apply() { # apply <db> <file>
  psql_db "$1" <"$2" >/dev/null 2>"/tmp/tia_mig_err.$$"
}
apply_upto() { # apply every init file whose name sorts <= $2 prefix (exclusive when $3=lt)
  local db="$1" limit="$2" f
  for f in $(ls "$INIT_DIR"/*.sql | sort); do
    local base; base="$(basename "$f")"
    if [[ "$base" < "$limit" ]]; then apply "$db" "$f" || { echo "  init failed at $base: $(head -c 300 /tmp/tia_mig_err.$$)"; return 1; }; fi
  done
}
schema_check() { # python check against the named database, using the real tia_schema code
  docker run --rm --network "$NETWORK" -e POSTGRES_HOST="$CONTAINER" -e POSTGRES_PASSWORD=testpw -e POSTGRES_USER="$PGUSER" \
    -e POSTGRES_DB="$1" -e DB_POOL_MIN_SIZE=1 -e DB_POOL_MAX_SIZE=2 -e REDIS_HOST=127.0.0.1 -e JWT_SECRET=test \
    -v "$(cd "$(dirname "$0")/.." && pwd)/backend-api/app:/app/app:ro" "$IMAGE" \
    python -c "
from app.services import tia_schema
s = tia_schema.check_schema(force=True)
print('OK' if s.ok else 'MISSING ' + ','.join(s.missing))
" 2>/dev/null | tail -1
}

echo "== scenario: fresh install (all init files) =="
newdb tia_mig_fresh
if apply_upto tia_mig_fresh "zzz"; then ok "all init files apply cleanly"; else bad "all init files apply cleanly"; fi
[[ "$(schema_check tia_mig_fresh)" == "OK" ]] && ok "schema check passes on a fresh install" || bad "schema check passes on a fresh install"

echo "== scenario: upgrade from the currently deployed schema (through 116) =="
newdb tia_mig_from116
apply_upto tia_mig_from116 "117" || bad "base schema through 116"
psql_db tia_mig_from116 -c "INSERT INTO tenants (id, name, short_code) VALUES ('dddddddd-0000-0000-0000-000000000001', 'Upgrade tenant', 'UPG1');" >/dev/null
psql_db tia_mig_from116 -c "INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title, event_time, status) VALUES ('dddddddd-0000-0000-0000-0000000000a1', 'dddddddd-0000-0000-0000-000000000001', 'wazuh', 'ext-up-1', 'high', 'pre-existing alert', now(), 'new');" >/dev/null
[[ "$(schema_check tia_mig_from116)" == MISSING* ]] && ok "schema check reports the missing migration before upgrade" || bad "schema check reports the missing migration before upgrade"
if apply tia_mig_from116 "$INIT_DIR/118_tia_result_acceptance.sql"; then bad "118 alone must refuse when 117 is absent"; else ok "118 alone refuses when 117 is absent"; fi
[[ "$(psql_db tia_mig_from116 -c "SELECT count(*) FROM pg_class WHERE relname LIKE 'tia_%' AND relkind = 'r';")" == "0" ]] && ok "a refused 118 leaves no partial tables" || bad "a refused 118 leaves no partial tables"
apply tia_mig_from116 "$INIT_DIR/117_tia_review_items.sql" && ok "117 applies" || bad "117 applies"
apply tia_mig_from116 "$INIT_DIR/118_tia_result_acceptance.sql" && ok "118 applies after 117" || bad "118 applies after 117"
[[ "$(schema_check tia_mig_from116)" == "OK" ]] && ok "schema check passes after 117 + 118" || bad "schema check passes after 117 + 118"
[[ "$(psql_db tia_mig_from116 -c "SELECT count(*) FROM security_alerts WHERE id = 'dddddddd-0000-0000-0000-0000000000a1';")" == "1" ]] && ok "pre-existing alerts are untouched" || bad "pre-existing alerts are untouched"

echo "== scenario: upgrade from the increment 1 schema with existing review records =="
newdb tia_mig_from117
apply_upto tia_mig_from117 "118" || bad "base schema through 117"
psql_db tia_mig_from117 >/dev/null <<'SQL'
INSERT INTO tenants (id, name, short_code) VALUES ('dddddddd-0000-0000-0000-000000000002', 'Inc1 tenant', 'INC1');
INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title, event_time, status)
SELECT ('dddddddd-0000-0000-0000-0000000001' || lpad(g::text, 2, '0'))::uuid, 'dddddddd-0000-0000-0000-000000000002',
       'wazuh', 'ext-inc1-' || g, 'critical', 'inc1 alert ' || g, now(), 'new' FROM generate_series(1, 3) g;
INSERT INTO tia_review_items (tenant_id, alert_id, reason_code, execution_status, error_category, source_severity,
                              assessed_priority, notify_urgency, notification_state, due_at, status, occurrences, first_seen_at)
VALUES
 ('dddddddd-0000-0000-0000-000000000002', 'dddddddd-0000-0000-0000-000000000101', 'investigation_failed', 'failed', 'auth_failure', 'critical', 'P1', 'page', 'paged', now() + interval '10 minutes', 'open', 3, now() - interval '2 hours'),
 ('dddddddd-0000-0000-0000-000000000002', 'dddddddd-0000-0000-0000-000000000102', 'investigation_timed_out', 'timed_out', 'timeout', 'critical', 'P1', 'page', 'no_recipients_configured', now() - interval '5 minutes', 'acknowledged', 1, now() - interval '1 day'),
 ('dddddddd-0000-0000-0000-000000000002', 'dddddddd-0000-0000-0000-000000000103', 'investigation_failed', 'failed', 'malformed_output', 'critical', 'P1', 'queue', 'not_required', now() - interval '1 hour', 'resolved', 2, now() - interval '3 days');
UPDATE tia_review_items SET resolved_at = now() - interval '1 day', resolved_by = 'analyst@example.test' WHERE status = 'resolved';
SQL
BEFORE="$(psql_db tia_mig_from117 -c "SELECT md5(string_agg(concat_ws('|', id, tenant_id, alert_id, reason_code, execution_status, error_category, source_severity, assessed_priority, notify_urgency, notification_state, due_at, status, occurrences, first_seen_at, resolved_at, resolved_by), ';' ORDER BY id)) FROM tia_review_items;")"
[[ "$(schema_check tia_mig_from117)" == MISSING* ]] && ok "schema check reports 118 missing on the increment 1 schema" || bad "schema check reports 118 missing on the increment 1 schema"
apply tia_mig_from117 "$INIT_DIR/118_tia_result_acceptance.sql" && ok "118 applies over existing review records" || bad "118 applies over existing review records"
AFTER="$(psql_db tia_mig_from117 -c "SELECT md5(string_agg(concat_ws('|', id, tenant_id, alert_id, reason_code, execution_status, error_category, source_severity, assessed_priority, notify_urgency, notification_state, due_at, status, occurrences, first_seen_at, resolved_at, resolved_by), ';' ORDER BY id)) FROM tia_review_items;")"
[[ -n "$BEFORE" && "$BEFORE" == "$AFTER" ]] && ok "every existing review record is unchanged" || bad "every existing review record is unchanged"
[[ "$(psql_db tia_mig_from117 -c "SELECT count(*) FROM tia_review_items;")" == "3" ]] && ok "no review record was added or removed" || bad "no review record was added or removed"
[[ "$(psql_db tia_mig_from117 -c "SELECT count(*) FROM tia_review_events WHERE event_type = 'created' AND (detail->>'backfilled')::boolean;")" == "3" ]] && ok "history was backfilled once per existing item" || bad "history was backfilled once per existing item"
[[ "$(psql_db tia_mig_from117 -c "SELECT count(*) FROM tia_review_items WHERE deadline_basis = 'provisional' AND reopened_count = 0 AND analysis_available = false;")" == "3" ]] && ok "new columns take safe defaults (deadlines provisional)" || bad "new columns take safe defaults (deadlines provisional)"
[[ "$(schema_check tia_mig_from117)" == "OK" ]] && ok "schema check passes after 118" || bad "schema check passes after 118"
apply tia_mig_from117 "$INIT_DIR/118_tia_result_acceptance.sql" && ok "118 is re-runnable" || bad "118 is re-runnable"
[[ "$(psql_db tia_mig_from117 -c "SELECT count(*) FROM tia_review_events;")" == "3" ]] && ok "re-running 118 adds no duplicate history" || bad "re-running 118 adds no duplicate history"
AGAIN="$(psql_db tia_mig_from117 -c "SELECT md5(string_agg(concat_ws('|', id, tenant_id, alert_id, reason_code, execution_status, error_category, source_severity, assessed_priority, notify_urgency, notification_state, due_at, status, occurrences, first_seen_at, resolved_at, resolved_by), ';' ORDER BY id)) FROM tia_review_items;")"
[[ "$BEFORE" == "$AGAIN" ]] && ok "re-running 118 leaves records unchanged" || bad "re-running 118 leaves records unchanged"

echo "== rollback safety: increment 1 code keeps working on the upgraded schema (tables retained) =="
if psql_db tia_mig_from117 >/dev/null 2>&1 <<'SQL'
INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title, event_time, status)
VALUES ('dddddddd-0000-0000-0000-000000000104', 'dddddddd-0000-0000-0000-000000000002', 'wazuh', 'ext-inc1-4', 'critical', 'rollback alert', now(), 'new');
INSERT INTO tia_review_items (tenant_id, alert_id, reason_code, execution_status, source_severity, assessed_priority, due_at)
VALUES ('dddddddd-0000-0000-0000-000000000002', 'dddddddd-0000-0000-0000-000000000104', 'investigation_failed', 'failed', 'critical', 'P1', now() + interval '15 minutes');
UPDATE tia_review_items SET status = 'acknowledged', acknowledged_at = now() WHERE alert_id = 'dddddddd-0000-0000-0000-000000000104';
SQL
then ok "increment 1 style writes still succeed after 118"; else bad "increment 1 style writes still succeed after 118"; fi
[[ "$(psql_db tia_mig_from117 -c "SELECT count(*) FROM pg_class WHERE relname IN ('tia_results','tia_notifications','tia_investigation_attempts','tia_review_events') AND relkind = 'r';")" == "4" ]] && ok "additive tables remain present (nothing dropped on rollback)" || bad "additive tables remain present (nothing dropped on rollback)"

echo "== readiness validates structures, not just table names =="
newdb tia_mig_struct
apply_upto tia_mig_struct "zzz" >/dev/null
[[ "$(schema_check tia_mig_struct)" == "OK" ]] && ok "intact schema reports ready" || bad "intact schema reports ready"
psql_db tia_mig_struct -c "DROP TRIGGER trg_tia_results_immutable ON tia_results;" >/dev/null
[[ "$(schema_check tia_mig_struct)" == *"trigger trg_tia_results_immutable"* ]] && ok "a missing immutability trigger is a readiness fault" || bad "a missing immutability trigger is a readiness fault"
psql_db tia_mig_struct -c "ALTER TABLE tia_notifications DROP CONSTRAINT tia_notifications_idempotency_key_key;" >/dev/null
[[ "$(schema_check tia_mig_struct)" == *"unique(tia_notifications.idempotency_key)"* ]] && ok "a missing idempotency uniqueness is a readiness fault" || bad "a missing idempotency uniqueness is a readiness fault"
psql_db tia_mig_struct -c "ALTER TABLE tia_results NO FORCE ROW LEVEL SECURITY;" >/dev/null
[[ "$(schema_check tia_mig_struct)" == *"forced row-level security on tia_results"* ]] && ok "weakened row-level security is a readiness fault" || bad "weakened row-level security is a readiness fault"
psql_db tia_mig_struct -c "DROP INDEX uq_tia_review_items_alert_live;" >/dev/null
[[ "$(schema_check tia_mig_struct)" == *"index uq_tia_review_items_alert_live"* ]] && ok "a missing one-live-item-per-alert index is a readiness fault" || bad "a missing one-live-item-per-alert index is a readiness fault"

echo "== durable job queue (migration 120) =="
jobs_ready() { # jobs_ready <db> : prints True/False from the real tia_jobs.schema_ready()
  docker run --rm --network "$NETWORK" -e POSTGRES_HOST="$CONTAINER" -e POSTGRES_PASSWORD=testpw -e POSTGRES_USER="$PGUSER" \
    -e POSTGRES_DB="$1" -e DB_POOL_MIN_SIZE=1 -e DB_POOL_MAX_SIZE=2 -e REDIS_HOST=127.0.0.1 -e JWT_SECRET=test \
    -v "$(cd "$(dirname "$0")/.." && pwd)/backend-api/app:/app/app:ro" "$IMAGE" \
    python -c "from app.services import tia_jobs; print(tia_jobs.schema_ready())" 2>/dev/null | tail -1
}
newdb tia_mig_jobs
apply_upto tia_mig_jobs "120" || bad "base schema through 119"
[[ "$(jobs_ready tia_mig_jobs)" == "False" ]] && ok "jobs are reported not ready before 120" || bad "jobs are reported not ready before 120"
psql_db tia_mig_jobs >/dev/null <<'SQL'
INSERT INTO tenants (id, name, short_code) VALUES ('dddddddd-0000-0000-0000-000000000003', 'Jobs tenant', 'JOBM');
INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title, event_time, status)
VALUES ('dddddddd-0000-0000-0000-0000000002a1', 'dddddddd-0000-0000-0000-000000000003', 'wazuh', 'ext-jobs-1', 'critical', 'jobs alert', now(), 'new');
SQL
apply tia_mig_jobs "$INIT_DIR/120_tia_jobs.sql" && ok "120 applies over existing alerts" || bad "120 applies over existing alerts"
[[ "$(jobs_ready tia_mig_jobs)" == "True" ]] && ok "jobs are ready after 120" || bad "jobs are ready after 120"
apply tia_mig_jobs "$INIT_DIR/120_tia_jobs.sql" && ok "120 is re-runnable" || bad "120 is re-runnable"
[[ "$(psql_db tia_mig_jobs -c "SELECT count(*) FROM security_alerts;")" == "1" ]] && ok "120 leaves existing alerts untouched" || bad "120 leaves existing alerts untouched"
psql_db tia_mig_jobs -c "INSERT INTO tia_jobs (tenant_id, alert_id, kind, priority) VALUES ('dddddddd-0000-0000-0000-000000000003','dddddddd-0000-0000-0000-0000000002a1','deep_triage',0);" >/dev/null
if psql_db tia_mig_jobs -c "INSERT INTO tia_jobs (tenant_id, alert_id, kind, priority) VALUES ('dddddddd-0000-0000-0000-000000000003','dddddddd-0000-0000-0000-0000000002a1','deep_triage',0);" >/dev/null 2>&1; then bad "two live jobs for one alert are refused"; else ok "two live jobs for one alert are refused"; fi
psql_db tia_mig_jobs -c "DROP INDEX uq_tia_jobs_live;" >/dev/null
[[ "$(jobs_ready tia_mig_jobs)" == "False" ]] && ok "a missing one-live-job-per-alert index makes jobs not ready" || bad "a missing one-live-job-per-alert index makes jobs not ready"
docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -qc "DROP DATABASE IF EXISTS tia_mig_jobs;" >/dev/null 2>&1

echo "== verified playbooks (migration 121) =="
newdb tia_mig_pb
apply_upto tia_mig_pb "121" || bad "base schema through 120"
if psql_db tia_mig_pb -c "SELECT to_regclass('public.tia_playbook_evaluations');" | grep -q "^$"; then ok "playbook tables absent before 121"; else bad "playbook tables absent before 121"; fi
psql_db tia_mig_pb >/dev/null <<'SQL'
INSERT INTO tenants (id, name, short_code) VALUES ('dddddddd-0000-0000-0000-000000000004', 'Playbook tenant', 'PBKM');
INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title, event_time, status)
VALUES ('dddddddd-0000-0000-0000-0000000003a1', 'dddddddd-0000-0000-0000-000000000004', 'wazuh', 'ext-pb-1', 'medium', 'nmap port scan', now(), 'new');
SQL
apply tia_mig_pb "$INIT_DIR/121_tia_playbooks.sql" && ok "121 applies over existing alerts" || bad "121 applies over existing alerts"
apply tia_mig_pb "$INIT_DIR/121_tia_playbooks.sql" && ok "121 is re-runnable" || bad "121 is re-runnable"
[[ "$(psql_db tia_mig_pb -c "SELECT count(*) FROM tia_playbook_enablements;")" == "0" ]] && ok "121 enables nothing: no playbook can close an alert until a human records authorisation" || bad "121 enables nothing"
[[ "$(psql_db tia_mig_pb -c "SELECT status FROM security_alerts WHERE id = 'dddddddd-0000-0000-0000-0000000003a1';")" == "new" ]] && ok "121 leaves existing alerts untouched" || bad "121 leaves existing alerts untouched"
if psql_db tia_mig_pb -c "INSERT INTO tia_playbook_enablements (tenant_id, playbook_id, playbook_version, enabled_by, customer_authorisation) VALUES ('dddddddd-0000-0000-0000-000000000004','authorized_scanner',1,' ','x');" >/dev/null 2>&1; then bad "an enablement without a named enabler is refused"; else ok "an enablement without a named enabler is refused"; fi
if psql_db tia_mig_pb -c "INSERT INTO tia_playbook_enablements (tenant_id, playbook_id, playbook_version, enabled_by, customer_authorisation) VALUES ('dddddddd-0000-0000-0000-000000000004','authorized_scanner',1,'a','');" >/dev/null 2>&1; then bad "an enablement without customer authorisation is refused"; else ok "an enablement without customer authorisation is refused"; fi
psql_db tia_mig_pb -c "INSERT INTO tia_playbook_enablements (tenant_id, playbook_id, playbook_version, enabled_by, customer_authorisation) VALUES ('dddddddd-0000-0000-0000-000000000004','authorized_scanner',1,'a','ref');" >/dev/null
if psql_db tia_mig_pb -c "INSERT INTO tia_playbook_enablements (tenant_id, playbook_id, playbook_version, enabled_by, customer_authorisation) VALUES ('dddddddd-0000-0000-0000-000000000004','authorized_scanner',2,'a','ref');" >/dev/null 2>&1; then bad "only one live enablement per tenant and playbook"; else ok "only one live enablement per tenant and playbook"; fi
if psql_db tia_mig_pb -c "INSERT INTO tia_authorized_activity (tenant_id, kind, source_ip, label, valid_from, valid_to, approved_by, reference) VALUES ('dddddddd-0000-0000-0000-000000000004','scanner','10.0.0.1','x', now(), now() - interval '1 day','a','b');" >/dev/null 2>&1; then bad "an authorisation window must end after it starts"; else ok "an authorisation window must end after it starts"; fi
docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -qc "DROP DATABASE IF EXISTS tia_mig_pb;" >/dev/null 2>&1

for db in tia_mig_fresh tia_mig_from116 tia_mig_from117 tia_mig_struct; do
  docker exec "$CONTAINER" psql -U "$PGUSER" -d postgres -qc "DROP DATABASE IF EXISTS $db;" >/dev/null 2>&1
done
rm -f "/tmp/tia_mig_err.$$"

echo
echo "RESULT: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
