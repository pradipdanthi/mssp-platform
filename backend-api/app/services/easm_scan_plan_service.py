"""EASM scan-plan + sync for VM 109 Amass/Nuclei agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write


def build_easm_scan_plan(*, force_all: bool = False) -> Dict[str, Any]:
    """Tenants with EASM entitlement + primary targets due for remote recon."""
    rows = fetch_all(
        """
        SELECT
            t.id::text AS tenant_id,
            t.short_code
        FROM tenants t
        JOIN tenant_entitlements te ON te.tenant_id = t.id
        WHERE t.status = 'active'
          AND te.external_attack_surface_enabled = true;
        """
    )
    tenants_out: List[Dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    for row in rows:
        targets = fetch_all(
            """
            SELECT domain_or_ip, asset_type
            FROM tenant_easm_assets
            WHERE tenant_id = %s::uuid
              AND status = 'ACTIVE'
              AND asset_type IN ('PRIMARY_DOMAIN', 'PUBLIC_IP');
            """,
            (row["tenant_id"],),
        )
        if not targets:
            continue

        refined: List[Dict[str, str]] = []
        for t in targets:
            latest = fetch_one(
                """
                SELECT scan_status, executed_at
                FROM tenant_easm_scans
                WHERE tenant_id = %s::uuid AND target_domain = %s
                ORDER BY COALESCE(executed_at, created_at) DESC
                LIMIT 1;
                """,
                (row["tenant_id"], t["domain_or_ip"]),
            )
            if force_all or not latest:
                refined.append(
                    {"domain": t["domain_or_ip"], "asset_type": t["asset_type"]}
                )
                continue
            if latest.get("scan_status") == "RUNNING":
                continue
            executed = latest.get("executed_at")
            if executed is None:
                refined.append(
                    {"domain": t["domain_or_ip"], "asset_type": t["asset_type"]}
                )
                continue
            if getattr(executed, "tzinfo", None) is None:
                executed = executed.replace(tzinfo=timezone.utc)
            if executed < cutoff:
                refined.append(
                    {"domain": t["domain_or_ip"], "asset_type": t["asset_type"]}
                )

        if refined:
            tenants_out.append(
                {
                    "tenant_id": row["tenant_id"],
                    "short_code": row["short_code"],
                    "targets": refined,
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenants": tenants_out,
    }


def ingest_easm_sync(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Amass/Nuclei agent payload into easm tables."""
    short = (payload.get("tenant_short_code") or "").strip().upper()
    tenant = fetch_one(
        "SELECT id::text FROM tenants WHERE upper(short_code) = %s LIMIT 1;",
        (short,),
    )
    if not tenant and payload.get("tenant_id"):
        tenant = fetch_one(
            "SELECT id::text FROM tenants WHERE id = %s::uuid LIMIT 1;",
            (str(payload["tenant_id"]),),
        )
    if not tenant:
        raise ValueError("Tenant not found")
    tid = tenant["id"]
    domain = (payload.get("target_domain") or "").strip().lower()
    if not domain:
        raise ValueError("target_domain required")

    scan = fetch_one_write(
        """
        INSERT INTO tenant_easm_scans (
            tenant_id, target_domain, scan_status, executed_at
        ) VALUES (%s::uuid, %s, 'RUNNING', now())
        RETURNING id::text;
        """,
        (tid, domain),
    )
    scan_id = (scan or {}).get("id")
    assets_in = payload.get("assets") or []
    findings_in = payload.get("findings") or []
    assets_n = 0
    findings_n = 0
    for a in assets_in:
        value = str(a.get("domain_or_ip") or "").strip().lower()
        if not value:
            continue
        atype = str(a.get("asset_type") or "SUBDOMAIN").upper()
        if atype not in ("PRIMARY_DOMAIN", "SUBDOMAIN", "PUBLIC_IP", "RELATED_HOST"):
            atype = "SUBDOMAIN"
        source = str(a.get("discovery_source") or "amass_passive")[:80]
        execute(
            """
            INSERT INTO tenant_easm_assets (
                tenant_id, domain_or_ip, asset_type, discovery_source, status
            ) VALUES (%s::uuid, %s, %s, %s, 'ACTIVE')
            ON CONFLICT (tenant_id, domain_or_ip) DO UPDATE SET
                last_seen = now(),
                status = 'ACTIVE',
                discovery_source = EXCLUDED.discovery_source,
                updated_at = now();
            """,
            (tid, value, atype, source),
        )
        assets_n += 1

    for f in findings_in:
        sev = str(f.get("severity") or "MEDIUM").upper()
        if sev not in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            sev = "MEDIUM"
        execute(
            """
            INSERT INTO tenant_easm_findings (
                scan_id, tenant_id, asset_name, finding_type, severity,
                title, description, remediation, status
            ) VALUES (
                %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, 'open'
            );
            """,
            (
                scan_id,
                tid,
                str(f.get("asset_name") or domain)[:255],
                (
                    str(f.get("finding_type") or "EXPOSED_SERVICE").upper()
                    if str(f.get("finding_type") or "").upper()
                    in (
                        "OPEN_PORT",
                        "EXPIRED_SSL",
                        "EXPIRING_SSL",
                        "WEB_VULNERABILITY",
                        "SUBDOMAIN_TAKEOVER",
                        "EXPOSED_SERVICE",
                        "INFO",
                    )
                    else "EXPOSED_SERVICE"
                ),
                sev,
                str(f.get("title") or "External finding")[:500],
                str(f.get("description") or "")[:4000],
                str(f.get("remediation") or "")[:4000],
            ),
        )
        findings_n += 1

    execute(
        """
        UPDATE tenant_easm_scans
        SET scan_status = 'COMPLETED',
            assets_discovered = %s,
            findings_count = %s,
            completed_at = now()
        WHERE id = %s::uuid;
        """,
        (assets_n, findings_n, scan_id),
    )
    execute(
        """
        UPDATE tenant_entitlements
        SET external_attack_surface_enabled = true, updated_at = now()
        WHERE tenant_id = %s::uuid;
        """,
        (tid,),
    )
    return {
        "tenant_id": tid,
        "short_code": short,
        "scan_id": scan_id,
        "target_domain": domain,
        "assets_upserted": assets_n,
        "findings_inserted": findings_n,
        "engine": payload.get("engine") or "AMASS_NUCLEI",
    }
