"""KB-069: persist normalized vulnerability findings; promote to recommendations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.db.session import db_transaction
from app.schemas.vulnerabilities import VulnFindingIngest, VulnSyncRequest


class TenantNotFoundError(Exception):
    pass


class AssetTenantMismatchError(Exception):
    pass


def _should_create_recommendation(finding: VulnFindingIngest) -> bool:
    if finding.create_recommendation is not None:
        return finding.create_recommendation
    return finding.severity in ("high", "critical")


def _priority_for_severity(severity: str) -> str:
    if severity == "critical":
        return "critical"
    if severity == "high":
        return "high"
    if severity == "medium":
        return "medium"
    return "low"


def _plain_recommendation_title(finding: VulnFindingIngest) -> str:
    cve = (finding.cve_id or "").strip()
    base = finding.title.strip()
    if cve and cve.upper() not in base.upper():
        return f"Fix {cve}: {base}"[:500]
    return f"Address vulnerability: {base}"[:500]


def _plain_recommendation_description(finding: VulnFindingIngest) -> str:
    parts: List[str] = []
    if finding.customer_safe_summary:
        parts.append(finding.customer_safe_summary.strip())
    else:
        parts.append(
            "Our vulnerability scan found an issue that should be reviewed and remediated."
        )
    if finding.remediation_summary:
        parts.append("Recommended action:\n" + finding.remediation_summary.strip())
    if finding.cve_id:
        parts.append(f"Reference: {finding.cve_id.strip()}")
    parts.append(
        "Do not apply untrusted remediation scripts. Contact your SOC if you need help."
    )
    return "\n\n".join(parts)[:20000]


def _resolve_asset_id(
    cur: Any,
    *,
    tenant_id: str,
    finding: VulnFindingIngest,
) -> Optional[str]:
    if finding.protected_asset_id is not None:
        cur.execute(
            """
            SELECT id::text
            FROM protected_assets
            WHERE id = %s::uuid AND tenant_id = %s::uuid;
            """,
            (str(finding.protected_asset_id), tenant_id),
        )
        row = cur.fetchone()
        if not row:
            raise AssetTenantMismatchError(
                f"protected_asset_id {finding.protected_asset_id} not found for tenant"
            )
        return row["id"] if isinstance(row, dict) else row[0]

    hostname = (finding.asset_hostname or "").strip()
    if not hostname:
        return None
    cur.execute(
        """
        SELECT id::text
        FROM protected_assets
        WHERE tenant_id = %s::uuid
          AND lower(hostname) = lower(%s)
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (tenant_id, hostname),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row["id"] if isinstance(row, dict) else row[0]


def _upsert_finding(
    cur: Any,
    *,
    tenant_id: str,
    source_platform: str,
    finding: VulnFindingIngest,
    asset_id: Optional[str],
) -> Tuple[str, str]:
    cur.execute(
        """
        SELECT id::text, recommendation_id::text
        FROM vulnerabilities
        WHERE tenant_id = %s::uuid
          AND source_platform = %s
          AND external_finding_id = %s
        LIMIT 1;
        """,
        (tenant_id, source_platform, finding.external_finding_id),
    )
    existing = cur.fetchone()
    if existing:
        vuln_id = existing["id"] if isinstance(existing, dict) else existing[0]
        cur.execute(
            """
            UPDATE vulnerabilities SET
                protected_asset_id = COALESCE(%s::uuid, protected_asset_id),
                cve_id = COALESCE(%s, cve_id),
                nvt_oid = COALESCE(%s, nvt_oid),
                title = %s,
                severity = %s,
                status = 'open',
                customer_safe_summary = COALESCE(%s, customer_safe_summary),
                remediation_summary = COALESCE(%s, remediation_summary),
                internal_notes = COALESCE(%s, internal_notes),
                last_seen_at = now(),
                updated_at = now()
            WHERE id = %s::uuid
            RETURNING id::text;
            """,
            (
                asset_id,
                finding.cve_id,
                finding.nvt_oid,
                finding.title.strip(),
                finding.severity,
                finding.customer_safe_summary,
                finding.remediation_summary,
                finding.internal_notes,
                vuln_id,
            ),
        )
        return vuln_id, "updated"

    cur.execute(
        """
        INSERT INTO vulnerabilities (
            tenant_id, protected_asset_id, source_platform, external_finding_id,
            cve_id, nvt_oid, title, severity, status,
            customer_safe_summary, remediation_summary, internal_notes,
            first_seen_at, last_seen_at
        )
        VALUES (
            %s::uuid, %s::uuid, %s, %s,
            %s, %s, %s, %s, 'open',
            %s, %s, %s,
            now(), now()
        )
        RETURNING id::text;
        """,
        (
            tenant_id,
            asset_id,
            source_platform,
            finding.external_finding_id,
            finding.cve_id,
            finding.nvt_oid,
            finding.title.strip(),
            finding.severity,
            finding.customer_safe_summary,
            finding.remediation_summary,
            finding.internal_notes,
        ),
    )
    row = cur.fetchone()
    vuln_id = row["id"] if isinstance(row, dict) else row[0]
    return vuln_id, "created"


def _ensure_recommendation(
    cur: Any,
    *,
    tenant_id: str,
    vuln_id: str,
    finding: VulnFindingIngest,
    existing_recommendation_id: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    if existing_recommendation_id:
        return existing_recommendation_id, "existing"
    if not _should_create_recommendation(finding):
        return None, "skipped"

    title = _plain_recommendation_title(finding)
    description = _plain_recommendation_description(finding)
    priority = _priority_for_severity(finding.severity)
    cur.execute(
        """
        INSERT INTO customer_recommendations (
            tenant_id, related_vulnerability_id,
            title, description, priority, category, status,
            customer_visible
        )
        VALUES (
            %s::uuid, %s::uuid,
            %s, %s, %s, 'vulnerability', 'open',
            %s
        )
        RETURNING id::text;
        """,
        (
            tenant_id,
            vuln_id,
            title,
            description,
            priority,
            finding.recommendation_customer_visible,
        ),
    )
    row = cur.fetchone()
    rec_id = row["id"] if isinstance(row, dict) else row[0]
    cur.execute(
        """
        UPDATE vulnerabilities
        SET recommendation_id = %s::uuid, updated_at = now()
        WHERE id = %s::uuid;
        """,
        (rec_id, vuln_id),
    )
    return rec_id, "created"


def sync_vulnerabilities(payload: VulnSyncRequest) -> Dict[str, Any]:
    with db_transaction() as cur:
        cur.execute(
            "SELECT id::text, short_code FROM tenants WHERE short_code = %s;",
            (payload.tenant_short_code.strip().upper(),),
        )
        tenant = cur.fetchone()
        if not tenant:
            raise TenantNotFoundError(payload.tenant_short_code)
        tenant_id = tenant["id"] if isinstance(tenant, dict) else tenant[0]
        short_code = tenant["short_code"] if isinstance(tenant, dict) else tenant[1]

        results: List[Dict[str, Any]] = []
        for finding in payload.findings:
            asset_id = _resolve_asset_id(cur, tenant_id=tenant_id, finding=finding)
            vuln_id, action = _upsert_finding(
                cur,
                tenant_id=tenant_id,
                source_platform=payload.source_platform,
                finding=finding,
                asset_id=asset_id,
            )
            cur.execute(
                "SELECT recommendation_id::text FROM vulnerabilities WHERE id = %s::uuid;",
                (vuln_id,),
            )
            link = cur.fetchone()
            existing_rec = None
            if link:
                existing_rec = link["recommendation_id"] if isinstance(link, dict) else link[0]
            rec_id, rec_action = _ensure_recommendation(
                cur,
                tenant_id=tenant_id,
                vuln_id=vuln_id,
                finding=finding,
                existing_recommendation_id=existing_rec,
            )
            results.append(
                {
                    "external_finding_id": finding.external_finding_id,
                    "vulnerability_id": vuln_id,
                    "action": action,
                    "recommendation_id": rec_id,
                    "recommendation_action": rec_action,
                }
            )

        return {
            "tenant_id": tenant_id,
            "short_code": short_code,
            "results": results,
        }


def promote_vulnerability_to_recommendation(
    *,
    vulnerability_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    customer_visible: bool = False,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    with db_transaction() as cur:
        cur.execute(
            """
            SELECT
                id::text,
                tenant_id::text,
                title,
                severity,
                cve_id,
                customer_safe_summary,
                remediation_summary,
                recommendation_id::text
            FROM vulnerabilities
            WHERE id = %s::uuid;
            """,
            (vulnerability_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        data = dict(row) if not isinstance(row, dict) else row
        if data.get("recommendation_id"):
            return {
                "vulnerability_id": data["id"],
                "recommendation_id": data["recommendation_id"],
                "created": False,
                "customer_visible": customer_visible,
            }

        finding_like = VulnFindingIngest(
            external_finding_id="promote",
            title=data["title"],
            severity=data["severity"],
            cve_id=data.get("cve_id"),
            customer_safe_summary=data.get("customer_safe_summary"),
            remediation_summary=data.get("remediation_summary"),
            recommendation_customer_visible=customer_visible,
            create_recommendation=True,
        )
        rec_title = title.strip() if title else _plain_recommendation_title(finding_like)
        rec_desc = (
            description.strip()
            if description
            else _plain_recommendation_description(finding_like)
        )
        rec_priority = priority or _priority_for_severity(data["severity"])
        cur.execute(
            """
            INSERT INTO customer_recommendations (
                tenant_id, related_vulnerability_id,
                title, description, priority, category, status,
                customer_visible
            )
            VALUES (
                %s::uuid, %s::uuid,
                %s, %s, %s, 'vulnerability', 'open',
                %s
            )
            RETURNING id::text;
            """,
            (
                data["tenant_id"],
                data["id"],
                rec_title,
                rec_desc,
                rec_priority,
                customer_visible,
            ),
        )
        created = cur.fetchone()
        rec_id = created["id"] if isinstance(created, dict) else created[0]
        cur.execute(
            """
            UPDATE vulnerabilities
            SET recommendation_id = %s::uuid, updated_at = now()
            WHERE id = %s::uuid;
            """,
            (rec_id, data["id"]),
        )
        return {
            "vulnerability_id": data["id"],
            "recommendation_id": rec_id,
            "created": True,
            "customer_visible": customer_visible,
        }
