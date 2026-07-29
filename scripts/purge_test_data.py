#!/usr/bin/env python3
"""
KB-085: Safely purge lab/test operational data for a clean E2E validation reset.

Retains:
  - All table schemas / migrations
  - Platform staff users: platform_admin, soc_manager, soc_analyst
  - System roles / constraints

Removes / clears:
  - Tenant-scoped operational data (alerts, incidents, EDR, forensics, vulns, …)
  - Customer tenants and customer_* users (DEMO, DEMO2, MelVik, etc.)
  - Audit log rows (fresh trail for the new lab)

Usage (from /opt/mssp-control):
  docker compose exec -T backend-api python /app/../scripts/purge_test_data.py
  # preferred (host, via postgres container):
  python3 scripts/purge_test_data.py --via-docker
  python3 scripts/purge_test_data.py --via-docker --yes
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List, Sequence


PROTECTED_ROLES = ("platform_admin", "soc_manager", "soc_analyst")

# Optional: keep these short_codes if present (normally empty for full flush).
KEEP_TENANT_CODES: Sequence[str] = ()

OPERATIONAL_TABLES = (
    "incident_alerts",
    "incident_comments",
    "incident_timeline",
    "incidents",
    "security_alerts",
    "edr_process_events",
    "edr_forensic_artifacts",
    "edr_action_executions",
    "edr_endpoint_isolation",
    "edr_telemetry_stats",
    "vulnerabilities",
    "customer_recommendations",
    "monthly_reports",
    "notification_events",
    "service_upgrade_requests",
    "appliance_heartbeats",
    "appliances",
    "appliance_activation_tokens",
    "protected_assets",
    "tenant_contacts",
    "tenant_entitlements",
    "tenant_engine_bindings",
    "tenant_agent_install_tokens",
    "tenant_asset_service_coverage",
    "audit_logs",
)

# Wazuh manager agents that must never be removed during lab purge.
WAZUH_PROTECTED_AGENT_IDS = frozenset({"000", "002"})


def _psql_docker(sql: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "mssp-postgres",
            "psql",
            "-U",
            "mssp_admin",
            "-d",
            "mssp_control",
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            sql,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "psql failed")
    return (proc.stdout or "").strip()


def _run_sql_block(sql: str) -> None:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "mssp-postgres",
            "psql",
            "-U",
            "mssp_admin",
            "-d",
            "mssp_control",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "psql failed")


def build_purge_sql(*, keep_codes: Sequence[str]) -> str:
    keep_list = ", ".join(f"'{c.upper()}'" for c in keep_codes) if keep_codes else ""
    keep_clause = f"AND short_code NOT IN ({keep_list})" if keep_list else ""

    lines: List[str] = ["BEGIN;"]
    # Clear operational tables that may lack cascade from tenants in some edge cases.
    for table in OPERATIONAL_TABLES:
        lines.append(f"DELETE FROM {table};")
    # Remove customer users first (tenant CASCADE would also remove them).
    lines.append(
        """
DELETE FROM platform_users
WHERE role IN ('customer_admin', 'customer_viewer')
   OR user_type = 'customer';
""".strip()
    )
    lines.append(
        f"""
DELETE FROM tenants
WHERE 1=1 {keep_clause};
""".strip()
    )
    # Safety: never delete protected platform staff.
    lines.append(
        """
-- Verify protected staff remain
DO $$
DECLARE
  n INT;
BEGIN
  SELECT count(*) INTO n FROM platform_users
  WHERE role IN ('platform_admin', 'soc_manager', 'soc_analyst');
  IF n < 1 THEN
    RAISE EXCEPTION 'Refusing to commit purge: no platform staff users remain';
  END IF;
END $$;
""".strip()
    )
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def _clear_forensic_storage() -> None:
    import shutil

    for forensics_path in ("/var/lib/mssp/forensics",):
        if os.path.isdir(forensics_path):
            shutil.rmtree(forensics_path, ignore_errors=True)
            os.makedirs(forensics_path, exist_ok=True)
            print(f"Cleared forensic files at {forensics_path}")
    # Backend container path (when script runs on host)
    subprocess.run(
        [
            "docker",
            "exec",
            "mssp-backend-api",
            "sh",
            "-c",
            "rm -rf /var/lib/mssp/forensics/* 2>/dev/null; mkdir -p /var/lib/mssp/forensics",
        ],
        check=False,
        capture_output=True,
    )


def _purge_external_engines() -> None:
    """Best-effort cleanup in integrated SOC engines (lab reset)."""
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "mssp-backend-api",
            "python3",
            "-",
        ],
        input=_ENGINE_PURGE_PY,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "engine purge failed")


_ENGINE_PURGE_PY = r'''
import json
import os
import sys

sys.path.insert(0, "/app")

PROTECTED_AGENTS = {"000", "002"}


def purge_wazuh():
    from app.services import wazuh_client

    if not wazuh_client.credentials_configured():
        print("Wazuh: skip (credentials not configured)")
        return
    token = wazuh_client.authenticate()
    listed = wazuh_client._request(
        "GET", "/agents?select=id,name,status&limit=500", token=token
    )
    items = (listed.get("data") or {}).get("affected_items") or []
    removed = 0
    for item in items:
        aid = str(item.get("id") or "").zfill(3) if str(item.get("id") or "").isdigit() else str(item.get("id") or "")
        raw_id = str(item.get("id") or "")
        if raw_id in PROTECTED_AGENTS or aid in PROTECTED_AGENTS:
            continue
        wazuh_client._request(
            "DELETE",
            f"/agents?agents_list={raw_id}&status=all&older_than=0s",
            token=token,
        )
        removed += 1
        print(f"Wazuh: removed agent {raw_id} ({item.get('name')})")
    groups = wazuh_client._request("GET", "/groups?limit=500", token=token)
    for g in (groups.get("data") or {}).get("affected_items") or []:
        name = str(g.get("name") or "")
        if name.startswith("tenant_") and name != "tenant_default":
            try:
                wazuh_client._request(
                    "DELETE",
                    f"/groups?groups_list={name}",
                    token=token,
                )
                print(f"Wazuh: removed group {name}")
            except Exception as exc:
                print(f"Wazuh: group {name} not removed: {exc}")
    print(f"Wazuh: endpoint agents removed={removed}")


def purge_thehive():
    from app.services.thehive_client import _credentials, _request, credentials_configured

    if not credentials_configured():
        print("TheHive: skip (credentials not configured)")
        return
    orgs = [
        os.getenv("THEHIVE_ORG", "MSSP-Lab"),
        os.getenv("THEHIVE_DEFAULT_ORG", "MSSP"),
    ]
    seen = set()
    for org in orgs:
        org = (org or "").strip()
        if not org or org in seen:
            continue
        seen.add(org)
        for list_name, delete_path in (
            ("listAlert", "/api/alert"),
            ("listCase", "/api/case"),
        ):
            try:
                rows = _request(
                    "POST",
                    "/api/v1/query",
                    org=org,
                    body={"query": [{"_name": list_name}]},
                )
            except Exception as exc:
                print(f"TheHive ({org}): {list_name} skipped: {exc}")
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                rid = row.get("_id") or row.get("id")
                if not rid:
                    continue
                try:
                    _request("DELETE", f"{delete_path}/{rid}", org=org)
                    print(f"TheHive ({org}): deleted {list_name} {rid}")
                except Exception as exc:
                    print(f"TheHive ({org}): delete {rid} failed: {exc}")


def purge_redis():
    from app.db.session import redis_client

    try:
        client = redis_client()
        client.flushdb()
        print("Redis: flushed current database (lab cache/queues cleared)")
    except Exception as exc:
        print(f"Redis: flush skipped: {exc}")


if __name__ == "__main__":
    purge_wazuh()
    purge_thehive()
    purge_redis()
    print("ENGINE_PURGE_OK")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge MSSP lab/test tenant data")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument(
        "--via-docker",
        action="store_true",
        default=True,
        help="Run SQL via mssp-postgres docker exec (default)",
    )
    parser.add_argument(
        "--keep-tenant",
        action="append",
        default=[],
        help="short_code to retain (repeatable)",
    )
    parser.add_argument(
        "--engines",
        action="store_true",
        help="Also purge lab data in Wazuh, TheHive, Redis cache, and forensic storage",
    )
    args = parser.parse_args()
    keep = tuple(args.keep_tenant) or tuple(KEEP_TENANT_CODES)

    before_tenants = _psql_docker("SELECT count(*) FROM tenants;")
    before_users = _psql_docker("SELECT count(*) FROM platform_users;")
    before_alerts = _psql_docker("SELECT count(*) FROM security_alerts;")
    print(f"Before: tenants={before_tenants} users={before_users} alerts={before_alerts}")
    print(f"Protected roles retained: {', '.join(PROTECTED_ROLES)}")
    if keep:
        print(f"Keeping tenants: {', '.join(keep)}")
    else:
        print("Deleting ALL customer tenants.")

    if not args.yes:
        reply = input("Type PURGE to continue: ").strip()
        if reply != "PURGE":
            print("Aborted.")
            return 1

    sql = build_purge_sql(keep_codes=keep)
    _run_sql_block(sql)

    _clear_forensic_storage()

    if args.engines:
        _purge_external_engines()

    after_tenants = _psql_docker("SELECT count(*) FROM tenants;")
    after_users = _psql_docker(
        "SELECT count(*) FROM platform_users WHERE role IN "
        "('platform_admin','soc_manager','soc_analyst');"
    )
    after_alerts = _psql_docker("SELECT count(*) FROM security_alerts;")
    after_actions = _psql_docker("SELECT count(*) FROM edr_action_executions;")
    print(f"After: tenants={after_tenants} platform_staff={after_users} "
          f"alerts={after_alerts} edr_actions={after_actions}")
    print("PURGE_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PURGE_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
