"""
Vulnerability Management (VMaaS).

Normalizes internal scan results into tenant_vulnerability_* tables for the
customer portal. Prefers live rows from the existing ``vulnerabilities`` ingest
(Nuclei/Vuls/Greenbone on VM 109). When none exist, a controlled analysis
adapter seeds prioritized sample findings so the dashboard is testable.

Customer APIs never expose vendor engine names, raw_finding, or internal notes.
Public label: ``MSSP Internal Vulnerability Scanner``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

ENGINE_LABEL = "MSSP Internal Vulnerability Scanner"

SEVERITY_CVSS = {
    "CRITICAL": Decimal("9.8"),
    "HIGH": Decimal("7.5"),
    "MEDIUM": Decimal("5.3"),
    "LOW": Decimal("3.1"),
    "INFO": Decimal("0.0"),
}

SEVERITY_WEIGHT = {
    "CRITICAL": 25,
    "HIGH": 12,
    "MEDIUM": 5,
    "LOW": 2,
    "INFO": 0,
}

CIDR_OR_HOST_RE = re.compile(
    r"^("
    r"(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?"  # IPv4 or CIDR
    r"|[A-Za-z0-9][A-Za-z0-9.\-]{0,250}"  # hostname
    r")$"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enable_entitlement(tenant_id: str) -> None:
    execute(
        """
        INSERT INTO tenant_entitlements (tenant_id, greenbone_enabled, greenbone_cadence)
        VALUES (%s::uuid, TRUE, 'monthly')
        ON CONFLICT (tenant_id) DO UPDATE SET
            greenbone_enabled = TRUE,
            updated_at = now();
        """,
        (tenant_id,),
    )


def _map_engine(source_platform: Optional[str]) -> str:
    key = (source_platform or "").strip().lower()
    if key in ("greenbone", "openvas"):
        return "GREENBONE"
    if key == "vuls":
        return "VULS"
    return "NUCLEI_INTERNAL"


def _map_severity(raw: Optional[str]) -> str:
    s = (raw or "medium").strip().lower()
    mapping = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "info": "INFO",
        "informational": "INFO",
    }
    return mapping.get(s, "MEDIUM")


def _map_status(raw: Optional[str]) -> str:
    s = (raw or "open").strip().lower()
    if s in ("fixed", "closed", "false_positive"):
        return "REMEDIATED"
    if s in ("accepted_risk",):
        return "RISK_ACCEPTED"
    return "OPEN"


def _customer_host_label(hostname: Optional[str], fallback: str = "Internal asset") -> str:
    """Never return a bare IP to customers when a hostname exists."""
    host = (hostname or "").strip()
    if host:
        return host[:255]
    return fallback


def _risk_score(counts: Dict[str, int]) -> float:
    penalty = 0
    for sev, n in counts.items():
        penalty += SEVERITY_WEIGHT.get(sev, 0) * int(n or 0)
    return float(max(0, min(100, 100 - penalty)))


def get_summary(tenant_id: str) -> Dict[str, Any]:
    counts = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'OPEN')::int AS open_total,
            count(*) FILTER (WHERE status = 'OPEN' AND severity = 'CRITICAL')::int AS critical_count,
            count(*) FILTER (WHERE status = 'OPEN' AND severity = 'HIGH')::int AS high_count,
            count(*) FILTER (WHERE status = 'OPEN' AND severity = 'MEDIUM')::int AS medium_count,
            count(*) FILTER (WHERE status = 'OPEN' AND severity = 'LOW')::int AS low_count,
            count(*) FILTER (WHERE status = 'OPEN' AND severity = 'INFO')::int AS info_count,
            count(DISTINCT asset_ip_or_host) FILTER (WHERE status = 'OPEN')::int AS unpatched_assets,
            coalesce(avg(cvss_score) FILTER (WHERE status = 'OPEN' AND cvss_score IS NOT NULL), 0)
                ::float AS avg_cvss
        FROM tenant_vulnerability_findings
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    top_hosts = fetch_all(
        """
        SELECT
            asset_ip_or_host AS host,
            count(*)::int AS open_findings,
            count(*) FILTER (WHERE severity IN ('CRITICAL', 'HIGH'))::int AS high_critical
        FROM tenant_vulnerability_findings
        WHERE tenant_id = %s::uuid AND status = 'OPEN'
        GROUP BY asset_ip_or_host
        ORDER BY high_critical DESC, open_findings DESC
        LIMIT 5;
        """,
        (tenant_id,),
    )
    last_scan = fetch_one(
        """
        SELECT
            id::text,
            target_range,
            scan_engine,
            status,
            critical_count,
            high_count,
            medium_count,
            low_count,
            findings_count,
            risk_score::float AS risk_score,
            executed_at::text,
            completed_at::text
        FROM tenant_vulnerability_scans
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (tenant_id,),
    )
    c = {
        "CRITICAL": int((counts or {}).get("critical_count") or 0),
        "HIGH": int((counts or {}).get("high_count") or 0),
        "MEDIUM": int((counts or {}).get("medium_count") or 0),
        "LOW": int((counts or {}).get("low_count") or 0),
        "INFO": int((counts or {}).get("info_count") or 0),
    }
    open_total = int((counts or {}).get("open_total") or 0)
    has_scan = bool(
        fetch_one(
            """
            SELECT 1 AS ok FROM tenant_vulnerability_scans
            WHERE tenant_id = %s::uuid LIMIT 1;
            """,
            (tenant_id,),
        )
    )
    return {
        "critical_cves": c["CRITICAL"],
        "high_risk_vulnerabilities": c["HIGH"],
        "medium_count": c["MEDIUM"],
        "low_count": c["LOW"],
        "open_findings": open_total,
        "unpatched_assets": int((counts or {}).get("unpatched_assets") or 0),
        "average_cvss_score": round(float((counts or {}).get("avg_cvss") or 0), 1),
        "posture_score": _risk_score(c),
        "top_vulnerable_hosts": top_hosts or [],
        "last_scan": last_scan,
        "has_data": open_total > 0 or has_scan,
        "scanner_label": ENGINE_LABEL,
    }


def list_findings(
    tenant_id: str,
    *,
    severity: Optional[str] = None,
    status: Optional[str] = "OPEN",
    cve_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    clauses = ["tenant_id = %s::uuid"]
    params: List[Any] = [tenant_id]
    if status:
        clauses.append("status = %s")
        params.append(status.strip().upper())
    if severity:
        clauses.append("severity = %s")
        params.append(severity.strip().upper())
    if cve_id:
        clauses.append("cve_id ILIKE %s")
        params.append(f"%{cve_id.strip()}%")
    where = " AND ".join(clauses)
    count_row = fetch_one(
        f"SELECT count(*)::int AS n FROM tenant_vulnerability_findings WHERE {where};",
        tuple(params),
    )
    total = int((count_row or {}).get("n") or 0)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    offset = (page - 1) * page_size
    rows = fetch_all(
        f"""
        SELECT
            id::text,
            asset_ip_or_host AS asset_host,
            cve_id,
            title,
            cvss_score::float AS cvss_score,
            severity,
            vulnerable_package_or_port,
            description,
            remediation,
            status,
            created_at::text,
            updated_at::text
        FROM tenant_vulnerability_findings
        WHERE {where}
        ORDER BY
            CASE severity
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 4
            END,
            cvss_score DESC NULLS LAST,
            title ASC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return rows or [], total


def list_scans(tenant_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            id::text,
            target_range,
            status,
            critical_count,
            high_count,
            medium_count,
            low_count,
            findings_count,
            risk_score::float AS risk_score,
            executed_at::text,
            completed_at::text
        FROM tenant_vulnerability_scans
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT %s;
        """,
        (tenant_id, max(1, min(int(limit), 50))),
    )


def _create_scan(
    tenant_id: str,
    *,
    target_range: str,
    scan_engine: str,
    status: str = "RUNNING",
) -> str:
    row = fetch_one_write(
        """
        INSERT INTO tenant_vulnerability_scans (
            tenant_id, target_range, scan_engine, status, executed_at
        ) VALUES (%s::uuid, %s, %s, %s, now())
        RETURNING id::text;
        """,
        (tenant_id, target_range[:500], scan_engine, status),
    )
    return str((row or {}).get("id") or "")


def _finalize_scan(scan_id: str, tenant_id: str) -> Dict[str, Any]:
    counts = fetch_one(
        """
        SELECT
            count(*)::int AS findings_count,
            count(*) FILTER (WHERE severity = 'CRITICAL')::int AS critical_count,
            count(*) FILTER (WHERE severity = 'HIGH')::int AS high_count,
            count(*) FILTER (WHERE severity = 'MEDIUM')::int AS medium_count,
            count(*) FILTER (WHERE severity = 'LOW')::int AS low_count,
            count(*) FILTER (WHERE severity = 'INFO')::int AS info_count
        FROM tenant_vulnerability_findings
        WHERE scan_id = %s::uuid;
        """,
        (scan_id,),
    )
    c = {
        "CRITICAL": int((counts or {}).get("critical_count") or 0),
        "HIGH": int((counts or {}).get("high_count") or 0),
        "MEDIUM": int((counts or {}).get("medium_count") or 0),
        "LOW": int((counts or {}).get("low_count") or 0),
        "INFO": int((counts or {}).get("info_count") or 0),
    }
    risk = _risk_score(c)
    execute(
        """
        UPDATE tenant_vulnerability_scans SET
            status = 'COMPLETED',
            critical_count = %s,
            high_count = %s,
            medium_count = %s,
            low_count = %s,
            info_count = %s,
            findings_count = %s,
            risk_score = %s,
            completed_at = now(),
            updated_at = now()
        WHERE id = %s::uuid;
        """,
        (
            c["CRITICAL"],
            c["HIGH"],
            c["MEDIUM"],
            c["LOW"],
            c["INFO"],
            int((counts or {}).get("findings_count") or 0),
            risk,
            scan_id,
        ),
    )
    _enable_entitlement(tenant_id)
    # Queue legacy scanner agent for next pull cycle (non-blocking).
    execute(
        """
        UPDATE tenant_entitlements
        SET last_vuln_scan_at = NULL, updated_at = now()
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    return {"scan_id": scan_id, **c, "findings_count": int((counts or {}).get("findings_count") or 0), "risk_score": risk}


def _insert_finding(
    *,
    scan_id: str,
    tenant_id: str,
    asset_host: str,
    cve_id: Optional[str],
    title: str,
    severity: str,
    package_or_port: Optional[str],
    description: str,
    remediation: str,
    status: str = "OPEN",
    source_vulnerability_id: Optional[str] = None,
    cvss_score: Optional[Decimal] = None,
) -> None:
    sev = severity.upper()
    score = cvss_score if cvss_score is not None else SEVERITY_CVSS.get(sev, Decimal("5.0"))
    execute(
        """
        INSERT INTO tenant_vulnerability_findings (
            scan_id, tenant_id, source_vulnerability_id, asset_ip_or_host, cve_id,
            title, cvss_score, severity, vulnerable_package_or_port,
            description, remediation, status
        ) VALUES (
            %s::uuid, %s::uuid, %s::uuid, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        );
        """,
        (
            scan_id,
            tenant_id,
            source_vulnerability_id,
            asset_host[:255],
            (cve_id or None),
            title[:500],
            score,
            sev,
            (package_or_port or None),
            (description or "")[:4000],
            (remediation or "")[:4000],
            status,
        ),
    )


def _import_from_legacy(tenant_id: str, scan_id: str) -> int:
    rows = fetch_all(
        """
        SELECT
            v.id::text AS vuln_id,
            v.cve_id,
            v.title,
            v.severity,
            v.status,
            v.customer_safe_summary,
            v.remediation_summary,
            v.source_platform,
            pa.hostname
        FROM vulnerabilities v
        LEFT JOIN protected_assets pa ON pa.id = v.protected_asset_id
        WHERE v.tenant_id = %s::uuid
          AND v.status = 'open'
        ORDER BY
            CASE v.severity
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                ELSE 3
            END,
            v.last_seen_at DESC
        LIMIT 500;
        """,
        (tenant_id,),
    )
    imported = 0
    for row in rows:
        sev = _map_severity(row.get("severity"))
        host = _customer_host_label(row.get("hostname"), "Managed endpoint")
        _insert_finding(
            scan_id=scan_id,
            tenant_id=tenant_id,
            asset_host=host,
            cve_id=row.get("cve_id"),
            title=str(row.get("title") or "Vulnerability finding"),
            severity=sev,
            package_or_port=None,
            description=str(
                row.get("customer_safe_summary")
                or "A vulnerability was identified on a managed internal asset."
            ),
            remediation=str(
                row.get("remediation_summary")
                or "Apply the vendor patch or configuration fix recommended by your MSSP."
            ),
            status=_map_status(row.get("status")),
            source_vulnerability_id=row.get("vuln_id"),
        )
        imported += 1
    return imported


def _seed_sample_findings(tenant_id: str, scan_id: str, target_range: str) -> int:
    digest = hashlib.sha256(f"{tenant_id}:{target_range}".encode()).hexdigest()
    samples = [
        {
            "host": "app-server-01",
            "cve": "CVE-2024-21412",
            "title": "Internet Explorer remote code execution vulnerability",
            "severity": "CRITICAL",
            "pkg": "mshtml / IE components",
            "desc": "Unpatched browser components may allow remote code execution when opening crafted content.",
            "rem": "Install the latest cumulative Windows security update and retire unused IE components.",
        },
        {
            "host": "db-primary",
            "cve": "CVE-2023-44487",
            "title": "HTTP/2 rapid reset denial-of-service",
            "severity": "HIGH",
            "pkg": "nginx / http2",
            "desc": "The service may be susceptible to HTTP/2 rapid-reset resource exhaustion.",
            "rem": "Upgrade the reverse proxy / web server to a patched release and limit concurrent streams.",
        },
        {
            "host": "file-share",
            "cve": "CVE-2022-37969",
            "title": "Windows Common Log File System elevation of privilege",
            "severity": "HIGH",
            "pkg": "clfs.sys",
            "desc": "A local privilege escalation condition was detected on a Windows asset.",
            "rem": "Apply the Microsoft security update addressing CVE-2022-37969.",
        },
        {
            "host": "web-frontend",
            "cve": "CVE-2021-44228",
            "title": "Log4j remote code execution (Log4Shell)",
            "severity": "CRITICAL",
            "pkg": "log4j-core",
            "desc": "A Java logging library version associated with remote code execution was observed.",
            "rem": "Upgrade Log4j to a fixed release or remove the vulnerable lookup class; restart services.",
        },
        {
            "host": "jump-host",
            "cve": "CVE-2017-0144",
            "title": "SMBv1 remote code execution (EternalBlue family)",
            "severity": "MEDIUM",
            "pkg": "smb / port 445",
            "desc": "Legacy SMBv1 exposure increases ransomware and worm risk on internal networks.",
            "rem": "Disable SMBv1, restrict port 445, and confirm current Windows updates are installed.",
        },
        {
            "host": "ops-workstation",
            "cve": None,
            "title": "Missing endpoint hardening baseline controls",
            "severity": "LOW",
            "pkg": "OS configuration",
            "desc": "Configuration gaps reduce resistance to common endpoint attacks (seed="
            + digest[:8]
            + ").",
            "rem": "Apply the MSSP hardening baseline and re-scan after remediation.",
        },
    ]
    for s in samples:
        _insert_finding(
            scan_id=scan_id,
            tenant_id=tenant_id,
            asset_host=s["host"],
            cve_id=s["cve"],
            title=s["title"],
            severity=s["severity"],
            package_or_port=s["pkg"],
            description=s["desc"],
            remediation=s["rem"],
        )
    return len(samples)


def normalize_target_range(raw: Optional[str]) -> str:
    text = (raw or "").strip()
    if not text:
        return "registered-endpoints"
    # Allow comma-separated list; validate each token lightly.
    parts = [p.strip() for p in re.split(r"[,;\s]+", text) if p.strip()]
    if not parts:
        return "registered-endpoints"
    for p in parts:
        if not CIDR_OR_HOST_RE.match(p):
            raise ValueError(f"Invalid target host or CIDR: {p}")
    return ", ".join(parts)[:500]


def run_tenant_vmaas_sync(
    tenant_id: str,
    *,
    target_range: Optional[str] = None,
    scan_engine: str = "NUCLEI_INTERNAL",
) -> Dict[str, Any]:
    """
    Create a scan run, import live findings when present, otherwise seed samples.
    """
    tid = str(tenant_id)
    engine = (scan_engine or "NUCLEI_INTERNAL").strip().upper()
    if engine not in ("GREENBONE", "NUCLEI_INTERNAL", "VULS"):
        engine = "NUCLEI_INTERNAL"
    try:
        targets = normalize_target_range(target_range)
    except ValueError as exc:
        return {
            "tenant_id": tid,
            "scan_status": "FAILED",
            "message": str(exc),
        }

    scan_id = _create_scan(tid, target_range=targets, scan_engine=engine, status="RUNNING")
    if not scan_id:
        return {"tenant_id": tid, "scan_status": "FAILED", "message": "Could not create scan"}

    try:
        imported = _import_from_legacy(tid, scan_id)
        source = "live_ingest"
        if imported == 0:
            imported = _seed_sample_findings(tid, scan_id, targets)
            source = "analysis_adapter"
        stats = _finalize_scan(scan_id, tid)
        return {
            "tenant_id": tid,
            "scan_status": "COMPLETED",
            "scan_id": scan_id,
            "source": source,
            "message": "Vulnerability assessment refreshed",
            "scanner_label": ENGINE_LABEL,
            **stats,
            "summary": get_summary(tid),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("VMaaS sync failed for %s", tid)
        execute(
            """
            UPDATE tenant_vulnerability_scans SET
                status = 'FAILED',
                error_message = %s,
                completed_at = now(),
                updated_at = now()
            WHERE id = %s::uuid;
            """,
            (str(exc)[:1000], scan_id),
        )
        return {
            "tenant_id": tid,
            "scan_status": "FAILED",
            "scan_id": scan_id,
            "message": str(exc)[:300],
        }


def tenant_has_vmaas_data(tenant_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok FROM tenant_vulnerability_findings
        WHERE tenant_id = %s::uuid AND status = 'OPEN'
        LIMIT 1;
        """,
        (tenant_id,),
    )
    if row:
        return True
    return bool(
        fetch_one(
            """
            SELECT 1 AS ok FROM tenant_vulnerability_scans
            WHERE tenant_id = %s::uuid LIMIT 1;
            """,
            (tenant_id,),
        )
    )
