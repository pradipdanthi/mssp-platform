"""
External Attack Surface Management (EASM).

Control-plane adapter: registers public domains/IPs, runs lightweight perimeter
discovery (DNS, common-name enumeration, TLS certs, open ports, HTTP exposure),
and stores customer-safe findings.

Heavy scanners (Amass / Nuclei templates) remain on VM 109; this service never
exposes vendor brand names to customer APIs. Discovery source label:
``mssp_external_surface_scanner``.
"""

from __future__ import annotations

import logging
import re
import socket
import ssl
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

DISCOVERY_SOURCE = "mssp_external_surface_scanner"
CUSTOMER_SCANNER_LABEL = "MSSP External Surface Scanner"

# Safe common prefixes — not a full Amass corpus; enough for Phase 2 MVP.
COMMON_SUBDOMAINS = (
    "www",
    "mail",
    "webmail",
    "api",
    "vpn",
    "remote",
    "portal",
    "admin",
    "staging",
    "dev",
    "ftp",
    "ns1",
    "ns2",
    "cdn",
    "app",
    "login",
    "autodiscover",
    "owa",
    "smtp",
    "mx",
)

# Public-facing ports to probe (short timeout).
PROBE_PORTS = (
    (21, "ftp"),
    (22, "ssh"),
    (25, "smtp"),
    (53, "dns"),
    (80, "http"),
    (110, "pop3"),
    (143, "imap"),
    (443, "https"),
    (445, "smb"),
    (993, "imaps"),
    (995, "pop3s"),
    (3306, "mysql"),
    (3389, "rdp"),
    (5432, "postgres"),
    (8080, "http-alt"),
    (8443, "https-alt"),
)

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)
IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_target(raw: str) -> Tuple[str, str]:
    """
    Return (canonical, asset_type) where asset_type is PRIMARY_DOMAIN or PUBLIC_IP.
    Raises ValueError on invalid input.
    """
    text = (raw or "").strip().lower()
    if not text:
        raise ValueError("Domain or IP is required")
    if "://" in text:
        parsed = urlparse(text)
        text = (parsed.hostname or "").strip().lower()
    text = text.rstrip(".")
    if text.startswith("*."):
        text = text[2:]
    if IPV4_RE.match(text):
        return text, "PUBLIC_IP"
    if DOMAIN_RE.match(text):
        return text, "PRIMARY_DOMAIN"
    raise ValueError("Enter a valid public domain or IPv4 address")


def _enable_entitlement(tenant_id: str) -> None:
    execute(
        """
        INSERT INTO tenant_entitlements (tenant_id, external_attack_surface_enabled)
        VALUES (%s::uuid, TRUE)
        ON CONFLICT (tenant_id) DO UPDATE SET
            external_attack_surface_enabled = TRUE,
            updated_at = now();
        """,
        (tenant_id,),
    )


def register_primary_target(
    tenant_id: str,
    domain_or_ip: str,
    *,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    canonical, asset_type = normalize_target(domain_or_ip)
    row = fetch_one_write(
        """
        INSERT INTO tenant_easm_assets (
            tenant_id, domain_or_ip, asset_type, discovery_source, notes, status
        ) VALUES (
            %s::uuid, %s, %s, 'customer_registration', %s, 'ACTIVE'
        )
        ON CONFLICT (tenant_id, domain_or_ip) DO UPDATE SET
            asset_type = EXCLUDED.asset_type,
            status = 'ACTIVE',
            notes = COALESCE(EXCLUDED.notes, tenant_easm_assets.notes),
            last_seen = now(),
            updated_at = now()
        RETURNING
            id::text,
            tenant_id::text,
            domain_or_ip,
            asset_type,
            discovery_source,
            first_seen::text,
            last_seen::text,
            status,
            notes;
        """,
        (tenant_id, canonical, asset_type, (notes or "")[:2000] or None),
    )
    _enable_entitlement(tenant_id)
    return row or {}


def list_assets(tenant_id: str, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    clauses = ["tenant_id = %s::uuid"]
    params: List[Any] = [tenant_id]
    if not include_archived:
        clauses.append("status = 'ACTIVE'")
    where = " AND ".join(clauses)
    return fetch_all(
        f"""
        SELECT
            id::text,
            domain_or_ip,
            asset_type,
            discovery_source,
            first_seen::text,
            last_seen::text,
            status
        FROM tenant_easm_assets
        WHERE {where}
        ORDER BY
            CASE asset_type
                WHEN 'PRIMARY_DOMAIN' THEN 0
                WHEN 'PUBLIC_IP' THEN 1
                ELSE 2
            END,
            domain_or_ip ASC;
        """,
        tuple(params),
    )


def list_findings(
    tenant_id: str,
    *,
    severity: Optional[str] = None,
    finding_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    clauses = ["tenant_id = %s::uuid", "status = 'open'"]
    params: List[Any] = [tenant_id]
    if severity:
        clauses.append("severity = %s")
        params.append(severity.strip().upper())
    if finding_type:
        clauses.append("finding_type = %s")
        params.append(finding_type.strip().upper())
    where = " AND ".join(clauses)
    count_row = fetch_one(
        f"SELECT count(*)::int AS n FROM tenant_easm_findings WHERE {where};",
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
            scan_id::text,
            asset_name,
            finding_type,
            severity,
            title,
            description,
            remediation,
            created_at::text
        FROM tenant_easm_findings
        WHERE {where}
        ORDER BY
            CASE severity
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 4
            END,
            created_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return rows or [], total


def get_summary(tenant_id: str) -> Dict[str, Any]:
    assets = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'ACTIVE')::int AS total_assets,
            count(*) FILTER (WHERE status = 'ACTIVE' AND asset_type = 'PRIMARY_DOMAIN')::int AS primary_domains,
            count(*) FILTER (WHERE status = 'ACTIVE' AND asset_type = 'SUBDOMAIN')::int AS subdomains,
            count(*) FILTER (WHERE status = 'ACTIVE' AND asset_type = 'PUBLIC_IP')::int AS public_ips
        FROM tenant_easm_assets
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    findings = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'open')::int AS open_findings,
            count(*) FILTER (WHERE status = 'open' AND finding_type = 'OPEN_PORT')::int AS open_ports,
            count(*) FILTER (
                WHERE status = 'open'
                  AND finding_type IN ('EXPIRED_SSL', 'EXPIRING_SSL')
            )::int AS ssl_issues,
            count(*) FILTER (
                WHERE status = 'open'
                  AND finding_type IN ('WEB_VULNERABILITY', 'EXPOSED_SERVICE', 'SUBDOMAIN_TAKEOVER')
            )::int AS perimeter_vulns,
            count(*) FILTER (WHERE status = 'open' AND severity IN ('HIGH', 'CRITICAL'))::int AS high_critical
        FROM tenant_easm_findings
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    last_scan = fetch_one(
        """
        SELECT
            id::text,
            target_domain,
            scan_status,
            open_ports_count,
            vulnerabilities_count,
            ssl_status,
            assets_discovered,
            findings_count,
            executed_at::text,
            completed_at::text,
            error_message
        FROM tenant_easm_scans
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (tenant_id,),
    )
    total_assets = int((assets or {}).get("total_assets") or 0)
    return {
        "total_external_assets": total_assets,
        "primary_domains": int((assets or {}).get("primary_domains") or 0),
        "subdomains": int((assets or {}).get("subdomains") or 0),
        "public_ips": int((assets or {}).get("public_ips") or 0),
        "open_public_ports": int((findings or {}).get("open_ports") or 0),
        "expiring_ssl_certificates": int((findings or {}).get("ssl_issues") or 0),
        "perimeter_vulnerabilities": int((findings or {}).get("perimeter_vulns") or 0),
        "open_findings": int((findings or {}).get("open_findings") or 0),
        "high_critical_findings": int((findings or {}).get("high_critical") or 0),
        "last_scan": last_scan or None,
        "has_data": total_assets > 0,
        "scanner_label": CUSTOMER_SCANNER_LABEL,
    }


def tenant_has_easm_data(tenant_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok
        FROM tenant_easm_assets
        WHERE tenant_id = %s::uuid AND status = 'ACTIVE'
        LIMIT 1;
        """,
        (tenant_id,),
    )
    return bool(row)


# ---------------------------------------------------------------------------
# Discovery primitives (stdlib only — no third-party scanner binaries)
# ---------------------------------------------------------------------------


def _resolve_host(hostname: str) -> List[str]:
    ips: List[str] = []
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip and ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        return []
    return ips


def _port_open(ip: str, port: int, timeout: float = 1.2) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ssl_info(hostname: str, port: int = 443) -> Dict[str, Any]:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=3.0) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}
    not_after = cert.get("notAfter") if cert else None
    expires: Optional[datetime] = None
    if not_after:
        try:
            expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            expires = None
    status = "UNKNOWN"
    days_left = None
    if expires:
        days_left = (expires - _utcnow()).days
        if days_left < 0:
            status = "EXPIRED"
        elif days_left <= 30:
            status = "EXPIRING_SOON"
        else:
            status = "VALID"
    return {
        "ok": True,
        "status": status,
        "expires_at": expires.isoformat() if expires else None,
        "days_left": days_left,
        "subject": str(dict(x[0] for x in (cert.get("subject") or ())).get("commonName") or ""),
    }


def _http_probe(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "MSSP-External-Surface-Scanner/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read(4096)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return {
                "ok": True,
                "status_code": int(resp.status),
                "server": headers.get("server", ""),
                "has_hsts": "strict-transport-security" in headers,
                "has_xfo": "x-frame-options" in headers,
                "body_snippet": body[:200].decode("utf-8", errors="ignore"),
            }
    except urllib.error.HTTPError as exc:
        return {"ok": True, "status_code": int(exc.code), "server": "", "has_hsts": False, "has_xfo": False}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}


def _upsert_discovered_asset(
    tenant_id: str,
    value: str,
    asset_type: str,
    *,
    parent_id: Optional[str] = None,
) -> None:
    execute(
        """
        INSERT INTO tenant_easm_assets (
            tenant_id, domain_or_ip, asset_type, discovery_source, parent_asset_id, status
        ) VALUES (
            %s::uuid, %s, %s, %s, %s, 'ACTIVE'
        )
        ON CONFLICT (tenant_id, domain_or_ip) DO UPDATE SET
            last_seen = now(),
            status = 'ACTIVE',
            discovery_source = EXCLUDED.discovery_source,
            updated_at = now();
        """,
        (
            tenant_id,
            value,
            asset_type,
            DISCOVERY_SOURCE,
            parent_id if parent_id else None,
        ),
    )


def _insert_finding(
    *,
    scan_id: str,
    tenant_id: str,
    asset_name: str,
    finding_type: str,
    severity: str,
    title: str,
    description: str,
    remediation: str,
) -> None:
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
            tenant_id,
            asset_name[:255],
            finding_type,
            severity,
            title[:500],
            description[:4000],
            remediation[:4000],
        ),
    )


def _scan_host(
    *,
    scan_id: str,
    tenant_id: str,
    hostname: str,
    ips: List[str],
) -> Tuple[int, int, Optional[str]]:
    """Probe one host; return (open_ports, vulns, ssl_status)."""
    open_ports = 0
    vulns = 0
    ssl_status: Optional[str] = None
    primary_ip = ips[0] if ips else None
    if not primary_ip:
        _insert_finding(
            scan_id=scan_id,
            tenant_id=tenant_id,
            asset_name=hostname,
            finding_type="INFO",
            severity="INFO",
            title=f"No DNS resolution for {hostname}",
            description="The registered name did not resolve to a public IPv4 address during this scan.",
            remediation="Confirm the domain DNS records are published and authoritative.",
        )
        return 0, 0, "NONE"

    for port, service in PROBE_PORTS:
        if not _port_open(primary_ip, port):
            continue
        open_ports += 1
        sev = "INFO"
        ftype = "OPEN_PORT"
        rem = f"Confirm port {port}/{service} must be internet-facing; restrict with a firewall if not required."
        if port in (22, 3389, 445, 3306, 5432, 21):
            sev = "HIGH"
            ftype = "EXPOSED_SERVICE"
            vulns += 1
            rem = (
                f"Port {port} ({service}) is exposed on the public internet. "
                "Restrict to VPN/bastion or disable the service if unused."
            )
        elif port in (8080, 8443):
            sev = "MEDIUM"
            vulns += 1
        _insert_finding(
            scan_id=scan_id,
            tenant_id=tenant_id,
            asset_name=hostname,
            finding_type=ftype,
            severity=sev,
            title=f"Open port {port}/{service} on {hostname}",
            description=f"Reachable from the MSSP External Surface Scanner via {primary_ip}:{port}.",
            remediation=rem,
        )

    # TLS on 443
    if _port_open(primary_ip, 443):
        info = _ssl_info(hostname, 443)
        if info.get("ok"):
            ssl_status = info.get("status") or "UNKNOWN"
            if ssl_status == "EXPIRED":
                vulns += 1
                _insert_finding(
                    scan_id=scan_id,
                    tenant_id=tenant_id,
                    asset_name=hostname,
                    finding_type="EXPIRED_SSL",
                    severity="CRITICAL",
                    title=f"Expired TLS certificate on {hostname}",
                    description=f"Certificate expired (days_left={info.get('days_left')}).",
                    remediation="Renew and redeploy the TLS certificate immediately.",
                )
            elif ssl_status == "EXPIRING_SOON":
                vulns += 1
                _insert_finding(
                    scan_id=scan_id,
                    tenant_id=tenant_id,
                    asset_name=hostname,
                    finding_type="EXPIRING_SSL",
                    severity="MEDIUM",
                    title=f"TLS certificate expiring soon on {hostname}",
                    description=f"Certificate expires in {info.get('days_left')} days ({info.get('expires_at')}).",
                    remediation="Schedule certificate renewal before expiry to avoid outages.",
                )
        else:
            ssl_status = "UNKNOWN"

    # HTTP(S) exposure / missing hardening headers
    for scheme, port in (("https", 443), ("http", 80)):
        if not _port_open(primary_ip, port):
            continue
        probe = _http_probe(f"{scheme}://{hostname}/")
        if not probe.get("ok"):
            continue
        if scheme == "http" and probe.get("status_code"):
            _insert_finding(
                scan_id=scan_id,
                tenant_id=tenant_id,
                asset_name=hostname,
                finding_type="WEB_VULNERABILITY",
                severity="LOW",
                title=f"HTTP service reachable on {hostname}",
                description=f"HTTP responded with status {probe.get('status_code')}. Prefer HTTPS-only.",
                remediation="Redirect HTTP to HTTPS and disable cleartext where possible.",
            )
            vulns += 1
        if scheme == "https" and probe.get("status_code") and not probe.get("has_hsts"):
            _insert_finding(
                scan_id=scan_id,
                tenant_id=tenant_id,
                asset_name=hostname,
                finding_type="WEB_VULNERABILITY",
                severity="LOW",
                title=f"Missing HSTS header on {hostname}",
                description="HTTPS responded without Strict-Transport-Security.",
                remediation="Add Strict-Transport-Security with a suitable max-age.",
            )
            vulns += 1
        break

    return open_ports, vulns, ssl_status


def run_tenant_scan(tenant_id: str, *, target_domain: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute perimeter discovery for one primary domain/IP (or all primaries).
    """
    tid = str(tenant_id)
    if target_domain:
        targets = [
            {
                "id": None,
                "domain_or_ip": normalize_target(target_domain)[0],
                "asset_type": normalize_target(target_domain)[1],
            }
        ]
        # ensure registered
        register_primary_target(tid, target_domain)
        assets = list_assets(tid)
        for a in assets:
            if a["domain_or_ip"] == targets[0]["domain_or_ip"]:
                targets[0]["id"] = a["id"]
                break
    else:
        targets = [
            a
            for a in list_assets(tid)
            if a["asset_type"] in ("PRIMARY_DOMAIN", "PUBLIC_IP")
        ]

    if not targets:
        return {
            "tenant_id": tid,
            "scan_status": "FAILED",
            "message": "No registered primary domains or public IPs to scan",
        }

    # Mark prior open findings for this tenant as resolved before fresh scan
    # (keep history via previous scans; new scan inserts fresh open rows).
    results = []
    for target in targets:
        name = target["domain_or_ip"]
        parent_id = target.get("id")
        scan = fetch_one_write(
            """
            INSERT INTO tenant_easm_scans (
                tenant_id, target_domain, scan_status, executed_at
            ) VALUES (%s::uuid, %s, 'RUNNING', now())
            RETURNING id::text;
            """,
            (tid, name),
        )
        scan_id = (scan or {}).get("id")
        if not scan_id:
            continue

        try:
            # Resolve prior open findings for this asset on older scans → leave them;
            # we only add new findings for this scan_id.
            hosts_to_scan: List[Tuple[str, str, Optional[str]]] = []
            # (hostname, asset_type, parent_id)

            if target["asset_type"] == "PUBLIC_IP":
                hosts_to_scan.append((name, "PUBLIC_IP", parent_id))
                _upsert_discovered_asset(tid, name, "PUBLIC_IP", parent_id=parent_id)
            else:
                hosts_to_scan.append((name, "PRIMARY_DOMAIN", parent_id))
                for label in COMMON_SUBDOMAINS:
                    fqdn = f"{label}.{name}"
                    ips = _resolve_host(fqdn)
                    if ips:
                        _upsert_discovered_asset(
                            tid, fqdn, "SUBDOMAIN", parent_id=parent_id
                        )
                        for ip in ips:
                            _upsert_discovered_asset(
                                tid, ip, "PUBLIC_IP", parent_id=parent_id
                            )
                        hosts_to_scan.append((fqdn, "SUBDOMAIN", parent_id))

            # Also map apex IPs
            if target["asset_type"] == "PRIMARY_DOMAIN":
                for ip in _resolve_host(name):
                    _upsert_discovered_asset(tid, ip, "PUBLIC_IP", parent_id=parent_id)

            total_ports = 0
            total_vulns = 0
            ssl_status: Optional[str] = None
            for host, _, _ in hosts_to_scan:
                ips = _resolve_host(host) if not IPV4_RE.match(host) else [host]
                ports, vulns, ssl_st = _scan_host(
                    scan_id=scan_id,
                    tenant_id=tid,
                    hostname=host,
                    ips=ips,
                )
                total_ports += ports
                total_vulns += vulns
                if ssl_st and (ssl_status is None or ssl_st in ("EXPIRED", "EXPIRING_SOON")):
                    ssl_status = ssl_st
                elif ssl_status is None:
                    ssl_status = ssl_st

            assets_count = fetch_one(
                """
                SELECT count(*)::int AS n FROM tenant_easm_assets
                WHERE tenant_id = %s::uuid AND status = 'ACTIVE';
                """,
                (tid,),
            )
            findings_count = fetch_one(
                """
                SELECT count(*)::int AS n FROM tenant_easm_findings
                WHERE scan_id = %s::uuid;
                """,
                (scan_id,),
            )
            execute(
                """
                UPDATE tenant_easm_scans SET
                    scan_status = 'COMPLETED',
                    open_ports_count = %s,
                    vulnerabilities_count = %s,
                    ssl_status = %s,
                    assets_discovered = %s,
                    findings_count = %s,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid;
                """,
                (
                    total_ports,
                    total_vulns,
                    ssl_status or "NONE",
                    int((assets_count or {}).get("n") or 0),
                    int((findings_count or {}).get("n") or 0),
                    scan_id,
                ),
            )
            _enable_entitlement(tid)
            results.append(
                {
                    "scan_id": scan_id,
                    "target_domain": name,
                    "scan_status": "COMPLETED",
                    "open_ports_count": total_ports,
                    "vulnerabilities_count": total_vulns,
                    "ssl_status": ssl_status or "NONE",
                    "findings_count": int((findings_count or {}).get("n") or 0),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("EASM scan failed for %s", name)
            execute(
                """
                UPDATE tenant_easm_scans SET
                    scan_status = 'FAILED',
                    error_message = %s,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid;
                """,
                (str(exc)[:1000], scan_id),
            )
            results.append(
                {
                    "scan_id": scan_id,
                    "target_domain": name,
                    "scan_status": "FAILED",
                    "error": str(exc)[:300],
                }
            )

    return {
        "tenant_id": tid,
        "scan_status": "COMPLETED"
        if results and all(r.get("scan_status") == "COMPLETED" for r in results)
        else ("PARTIAL" if results else "FAILED"),
        "scans": results,
        "summary": get_summary(tid),
        "message": "Perimeter discovery refreshed",
    }


def start_scan_async(tenant_id: str, *, target_domain: Optional[str] = None) -> None:
    """Fire-and-forget scan in a daemon thread (admin/customer trigger)."""

    def _run() -> None:
        try:
            run_tenant_scan(tenant_id, target_domain=target_domain)
        except Exception:  # noqa: BLE001
            logger.exception("Background EASM scan failed for tenant %s", tenant_id)

    threading.Thread(target=_run, daemon=True, name=f"easm-scan-{tenant_id[:8]}").start()
