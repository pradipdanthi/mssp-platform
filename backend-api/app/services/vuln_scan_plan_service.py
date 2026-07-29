"""KB-079: Automated vuln scan plan from entitlements + protected assets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import db_transaction, fetch_all


def _cadence_interval(cadence: str) -> Optional[timedelta]:
    c = (cadence or "").strip().lower()
    if c == "weekly":
        return timedelta(days=7)
    if c == "monthly":
        return timedelta(days=30)
    if c == "off":
        return None
    return timedelta(days=30)


def _is_due(last_scan: Optional[datetime], cadence: str, *, force: bool = False) -> bool:
    if force:
        return True
    interval = _cadence_interval(cadence)
    if interval is None:
        return False
    if last_scan is None:
        return True
    if last_scan.tzinfo is None:
        last_scan = last_scan.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_scan >= interval


def _target_from_asset(row: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Return (scan_target, asset_hostname hint)."""
    hostname = (row.get("hostname") or "").strip()
    ip = row.get("ip_address")
    ip_str = str(ip).strip() if ip else ""
    if ip_str:
        return ip_str, hostname or None
    if hostname:
        return hostname, hostname
    return None


def build_scan_plan(*, force_all: bool = False) -> Dict[str, Any]:
    """
    Tenants with vulnerability management entitled + due cadence.
    Targets come from active asset coverage when present; otherwise all
    active protected_assets (legacy tenants with no coverage rows).
    """
    rows = fetch_all(
        """
        SELECT
            t.id::text AS tenant_id,
            t.short_code,
            te.greenbone_enabled,
            te.greenbone_cadence,
            te.last_vuln_scan_at
        FROM tenants t
        JOIN tenant_entitlements te ON te.tenant_id = t.id
        WHERE t.status = 'active'
          AND te.greenbone_enabled = true
          AND te.greenbone_cadence <> 'off';
        """
    )
    tenants_out: List[Dict[str, Any]] = []
    for row in rows:
        cadence = row.get("greenbone_cadence") or "monthly"
        last = row.get("last_vuln_scan_at")
        if not _is_due(last, cadence, force=force_all):
            continue

        covered = fetch_all(
            """
            SELECT pa.hostname, pa.ip_address::text AS ip_address
            FROM tenant_asset_service_coverage c
            JOIN protected_assets pa ON pa.id = c.asset_id
            WHERE c.tenant_id = %s::uuid
              AND c.service_key = 'vulnerability_management'
              AND c.status = 'active'
              AND pa.status = 'active';
            """,
            (row["tenant_id"],),
        )
        if covered:
            assets = covered
        else:
            # Legacy: entitled with no scoped coverage → all active assets.
            assets = fetch_all(
                """
                SELECT hostname, ip_address::text AS ip_address
                FROM protected_assets
                WHERE tenant_id = %s::uuid
                  AND status = 'active';
                """,
                (row["tenant_id"],),
            )

        targets: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for asset in assets:
            parsed = _target_from_asset(asset)
            if not parsed:
                continue
            target, hint = parsed
            if target in seen:
                continue
            seen.add(target)
            targets.append(
                {
                    "target": target,
                    "asset_hostname": hint,
                }
            )
        if not targets:
            continue
        tenants_out.append(
            {
                "tenant_short_code": row["short_code"],
                "cadence": cadence,
                "targets": targets,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenants": tenants_out,
    }


def mark_tenant_scanned(short_code: str) -> bool:
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE tenant_entitlements te
            SET last_vuln_scan_at = now(), updated_at = now()
            FROM tenants t
            WHERE t.id = te.tenant_id
              AND upper(t.short_code) = upper(%s);
            """,
            (short_code.strip(),),
        )
        return cur.rowcount > 0
