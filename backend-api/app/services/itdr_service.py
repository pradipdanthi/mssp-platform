"""
Cloud & Identity Threat Protection (ITDR).

Registers SaaS identity tenants (M365/Entra first), evaluates high-risk identity
rules, and stores customer-safe threat events.

Customer APIs never expose source_ip, raw_details, or third-party engine brands.
Public label: ``MSSP Cloud Identity Protection Engine``.

Phase 3 sync uses a controlled analysis adapter (deterministic rule evaluation +
synthetic sample events when live Graph credentials are not configured). Live
Microsoft Graph / Wazuh M365 module adapters can replace the sample path later
without changing the customer API shape.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from psycopg.types.json import Json

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

ENGINE_LABEL = "MSSP Cloud Identity Protection Engine"
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)


def _allow_lab_sample_seed() -> bool:
    """Synthetic ITDR rows are lab-only. Production fail-closes on empty Graph."""
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    if app_env == "production":
        return False
    flag = (os.getenv("ITDR_ALLOW_SAMPLE_ADAPTER") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    return app_env == "lab"

EVENT_COPY = {
    "IMPOSSIBLE_TRAVEL": {
        "title": "Impossible travel login detected",
        "summary": "The same account authenticated from distant locations faster than air travel allows.",
        "remediation": "Reset the account password, revoke active sessions, and confirm MFA methods with the user.",
        "severity": "CRITICAL",
    },
    "MFA_BYPASS_ATTEMPT": {
        "title": "MFA fatigue or bypass attempt",
        "summary": "Repeated MFA prompts or unusual MFA method changes were observed for this account.",
        "remediation": "Contact the user, review MFA registration, and temporarily block risky sign-ins.",
        "severity": "HIGH",
    },
    "ROGUE_ADMIN_ASSIGNED": {
        "title": "Unexpected privileged role assignment",
        "summary": "A high-privilege directory role was assigned outside the normal change process.",
        "remediation": "Verify the change with IT, remove unauthorized roles, and review privileged access logs.",
        "severity": "CRITICAL",
    },
    "EXTERNAL_MAIL_FORWARDING": {
        "title": "External mailbox auto-forwarding rule",
        "summary": "A mailbox rule was created that forwards mail to an external address.",
        "remediation": "Disable the forwarding rule, inspect mailbox rules, and confirm with the mailbox owner.",
        "severity": "HIGH",
    },
    "SUSPICIOUS_LOGIN": {
        "title": "Suspicious cloud sign-in",
        "summary": "Sign-in risk signals indicate an unusual login for this identity.",
        "remediation": "Review the sign-in in your identity console and require re-authentication if unexpected.",
        "severity": "MEDIUM",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_tenant_domain(raw: str) -> str:
    text = (raw or "").strip().lower().rstrip(".")
    if text.startswith("@"):
        text = text[1:]
    if "://" in text:
        text = text.split("://", 1)[1].split("/", 1)[0]
    if not text or not DOMAIN_RE.match(text):
        raise ValueError("Enter a valid Microsoft 365 / Entra tenant domain (e.g. contoso.com)")
    return text


def _enable_entitlement(tenant_id: str) -> None:
    execute(
        """
        INSERT INTO tenant_entitlements (tenant_id, cloud_identity_protection_enabled)
        VALUES (%s::uuid, TRUE)
        ON CONFLICT (tenant_id) DO UPDATE SET
            cloud_identity_protection_enabled = TRUE,
            updated_at = now();
        """,
        (tenant_id,),
    )


def connect_provider(
    tenant_id: str,
    *,
    provider: str = "M365_ENTRA",
    tenant_domain: str,
    display_name: Optional[str] = None,
    monitored_seat_count: int = 25,
) -> Dict[str, Any]:
    provider = (provider or "M365_ENTRA").strip().upper()
    if provider not in ("M365_ENTRA", "AWS_IAM", "GCP_IAM"):
        raise ValueError("Unsupported identity provider")
    domain = normalize_tenant_domain(tenant_domain)
    seats = max(1, min(int(monitored_seat_count or 25), 100000))
    row = fetch_one_write(
        """
        INSERT INTO tenant_cloud_identity_configs (
            tenant_id, provider, tenant_domain, display_name, status, monitored_seat_count
        ) VALUES (
            %s::uuid, %s, %s, %s, 'CONNECTED', %s
        )
        ON CONFLICT (tenant_id, provider, tenant_domain) DO UPDATE SET
            display_name = COALESCE(EXCLUDED.display_name, tenant_cloud_identity_configs.display_name),
            status = 'CONNECTED',
            monitored_seat_count = EXCLUDED.monitored_seat_count,
            updated_at = now()
        RETURNING
            id::text,
            tenant_id::text,
            provider,
            tenant_domain,
            display_name,
            status,
            monitored_seat_count,
            last_synced_at::text,
            created_at::text;
        """,
        (tenant_id, provider, domain, (display_name or "")[:200] or None, seats),
    )
    _enable_entitlement(tenant_id)
    return row or {}


def list_configs(tenant_id: str) -> List[Dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            id::text,
            provider,
            tenant_domain,
            display_name,
            status,
            monitored_seat_count,
            last_synced_at::text,
            created_at::text
        FROM tenant_cloud_identity_configs
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC;
        """,
        (tenant_id,),
    )


def get_summary(tenant_id: str) -> Dict[str, Any]:
    cfg = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'CONNECTED')::int AS connected_configs,
            coalesce(sum(monitored_seat_count) FILTER (WHERE status = 'CONNECTED'), 0)::int AS monitored_seats
        FROM tenant_cloud_identity_configs
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    ev = fetch_one(
        """
        SELECT
            count(*) FILTER (WHERE status = 'open')::int AS open_threats,
            count(*) FILTER (WHERE status = 'open' AND event_type = 'SUSPICIOUS_LOGIN')::int AS suspicious_logins,
            count(*) FILTER (
                WHERE status = 'open' AND event_type = 'EXTERNAL_MAIL_FORWARDING'
            )::int AS risky_mail_rules,
            count(*) FILTER (
                WHERE status = 'open' AND event_type = 'IMPOSSIBLE_TRAVEL'
            )::int AS impossible_travel,
            count(*) FILTER (
                WHERE status = 'open' AND event_type = 'MFA_BYPASS_ATTEMPT'
            )::int AS mfa_bypass,
            count(*) FILTER (
                WHERE status = 'open' AND event_type = 'ROGUE_ADMIN_ASSIGNED'
            )::int AS rogue_admin,
            count(*) FILTER (
                WHERE status = 'open' AND severity IN ('HIGH', 'CRITICAL')
            )::int AS high_critical
        FROM tenant_cloud_identity_events
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    last_sync = fetch_one(
        """
        SELECT max(last_synced_at)::text AS last_synced_at
        FROM tenant_cloud_identity_configs
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    seats = int((cfg or {}).get("monitored_seats") or 0)
    open_threats = int((ev or {}).get("open_threats") or 0)
    # Simple posture: start at 100, subtract weighted open threats (floor 0).
    posture = 100
    posture -= int((ev or {}).get("impossible_travel") or 0) * 15
    posture -= int((ev or {}).get("rogue_admin") or 0) * 20
    posture -= int((ev or {}).get("mfa_bypass") or 0) * 10
    posture -= int((ev or {}).get("risky_mail_rules") or 0) * 8
    posture -= int((ev or {}).get("suspicious_logins") or 0) * 4
    posture = max(0, min(100, posture))
    connected = int((cfg or {}).get("connected_configs") or 0)
    return {
        "monitored_cloud_seats": seats,
        "connected_providers": connected,
        "identity_threat_alerts": open_threats,
        "suspicious_logins": int((ev or {}).get("suspicious_logins") or 0),
        "risky_mail_rules": int((ev or {}).get("risky_mail_rules") or 0),
        "impossible_travel": int((ev or {}).get("impossible_travel") or 0),
        "mfa_bypass_attempts": int((ev or {}).get("mfa_bypass") or 0),
        "rogue_admin_assignments": int((ev or {}).get("rogue_admin") or 0),
        "high_critical_findings": int((ev or {}).get("high_critical") or 0),
        "identity_posture_score": posture,
        "last_synced_at": (last_sync or {}).get("last_synced_at"),
        "has_data": connected > 0,
        "engine_label": ENGINE_LABEL,
    }


def list_events(
    tenant_id: str,
    *,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
    user: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    clauses = ["tenant_id = %s::uuid", "status = 'open'"]
    params: List[Any] = [tenant_id]
    if severity:
        clauses.append("severity = %s")
        params.append(severity.strip().upper())
    if event_type:
        clauses.append("event_type = %s")
        params.append(event_type.strip().upper())
    if user:
        clauses.append("user_principal_name ILIKE %s")
        params.append(f"%{user.strip()}%")
    where = " AND ".join(clauses)
    count_row = fetch_one(
        f"SELECT count(*)::int AS n FROM tenant_cloud_identity_events WHERE {where};",
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
            user_principal_name,
            event_type,
            severity,
            location_country,
            location_city,
            title,
            summary,
            remediation,
            detected_at::text
        FROM tenant_cloud_identity_events
        WHERE {where}
        ORDER BY
            CASE severity
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                ELSE 3
            END,
            detected_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return rows or [], total


def _insert_event(
    *,
    tenant_id: str,
    config_id: str,
    upn: str,
    event_type: str,
    location_country: str,
    location_city: str,
    source_ip: str,
    detected_at: datetime,
    raw: Dict[str, Any],
) -> None:
    copy = EVENT_COPY[event_type]
    execute(
        """
        INSERT INTO tenant_cloud_identity_events (
            tenant_id, config_id, user_principal_name, event_type, severity,
            source_ip, location_country, location_city, title, summary, remediation,
            raw_details, status, detected_at
        ) VALUES (
            %s::uuid, %s::uuid, %s, %s, %s,
            %s::inet, %s, %s, %s, %s, %s,
            %s::jsonb, 'open', %s
        );
        """,
        (
            tenant_id,
            config_id,
            upn[:320],
            event_type,
            copy["severity"],
            source_ip,
            location_country[:64],
            location_city[:64],
            copy["title"],
            copy["summary"],
            copy["remediation"],
            Json(raw),
            detected_at,
        ),
    )


def _seed_events_for_config(tenant_id: str, cfg: Dict[str, Any]) -> int:
    """
    Controlled identity-rule analysis adapter.

    Lab-only. Production must fail closed when Microsoft Graph returns no events.
    """
    if not _allow_lab_sample_seed():
        return 0
    config_id = cfg["id"]
    domain = cfg["tenant_domain"]
    execute(
        """
        DELETE FROM tenant_cloud_identity_events
        WHERE tenant_id = %s::uuid AND config_id = %s::uuid AND status = 'open';
        """,
        (tenant_id, config_id),
    )
    digest = hashlib.sha256(f"{tenant_id}:{domain}".encode()).hexdigest()
    users = [
        f"admin@{domain}",
        f"finance@{domain}",
        f"ops.lead@{domain}",
        f"contractor@{domain}",
    ]
    now = _utcnow()
    samples = [
        {
            "event_type": "IMPOSSIBLE_TRAVEL",
            "upn": users[0],
            "country": "United States",
            "city": "New York",
            "ip": "203.0.113.10",
            "hours_ago": 2,
            "raw": {
                "rule": "impossible_travel",
                "from_country": "India",
                "to_country": "United States",
                "delta_minutes": 45,
                "seed": digest[:8],
            },
        },
        {
            "event_type": "MFA_BYPASS_ATTEMPT",
            "upn": users[1],
            "country": "Germany",
            "city": "Frankfurt",
            "ip": "198.51.100.24",
            "hours_ago": 5,
            "raw": {"rule": "mfa_fatigue", "prompt_count": 18, "seed": digest[8:16]},
        },
        {
            "event_type": "ROGUE_ADMIN_ASSIGNED",
            "upn": users[3],
            "country": "United Kingdom",
            "city": "London",
            "ip": "203.0.113.55",
            "hours_ago": 8,
            "raw": {
                "rule": "privileged_role_assigned",
                "role": "Global Administrator",
                "seed": digest[16:24],
            },
        },
        {
            "event_type": "EXTERNAL_MAIL_FORWARDING",
            "upn": users[2],
            "country": "India",
            "city": "Mumbai",
            "ip": "203.0.113.90",
            "hours_ago": 12,
            "raw": {
                "rule": "external_forwarding",
                "forward_to": "external-mailbox@example.net",
                "seed": digest[24:32],
            },
        },
        {
            "event_type": "SUSPICIOUS_LOGIN",
            "upn": users[1],
            "country": "Singapore",
            "city": "Singapore",
            "ip": "198.51.100.77",
            "hours_ago": 20,
            "raw": {"rule": "risky_signin", "risk_level": "medium", "seed": digest[32:40]},
        },
    ]
    for sample in samples:
        _insert_event(
            tenant_id=tenant_id,
            config_id=config_id,
            upn=sample["upn"],
            event_type=sample["event_type"],
            location_country=sample["country"],
            location_city=sample["city"],
            source_ip=sample["ip"],
            detected_at=now - timedelta(hours=int(sample["hours_ago"])),
            raw=sample["raw"],
        )
    return len(samples)


def _import_graph_events_for_config(tenant_id: str, cfg: Dict[str, Any]) -> int:
    """Pull live Microsoft Graph sign-ins / directory audits into ITDR events."""
    from app.services import itdr_graph_client as graph

    if not graph.configured():
        return 0
    config_id = cfg["id"]
    domain = cfg["tenant_domain"]
    try:
        sign_ins = graph.fetch_sign_ins(top=40)
        audits = graph.fetch_directory_audits(top=40)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Graph fetch failed for %s: %s", domain, exc)
        return 0
    events = graph.normalize_graph_events(domain=domain, sign_ins=sign_ins, audits=audits)
    if not events:
        return 0
    execute(
        """
        DELETE FROM tenant_cloud_identity_events
        WHERE tenant_id = %s::uuid AND config_id = %s::uuid AND status = 'open';
        """,
        (tenant_id, config_id),
    )
    now = _utcnow()
    for sample in events[:25]:
        _insert_event(
            tenant_id=tenant_id,
            config_id=config_id,
            upn=sample["upn"],
            event_type=sample["event_type"],
            location_country=sample["country"],
            location_city=sample["city"],
            source_ip=sample["ip"],
            detected_at=now - timedelta(hours=int(sample.get("hours_ago") or 1)),
            raw=sample.get("raw") or {},
        )
    return min(len(events), 25)


def sync_tenant_itdr(tenant_id: str) -> Dict[str, Any]:
    """Sync identity analysis for all connected configs under a tenant."""
    tid = str(tenant_id)
    configs = [
        c
        for c in list_configs(tid)
        if c.get("status") == "CONNECTED"
    ]
    if not configs:
        return {
            "tenant_id": tid,
            "sync_status": "empty",
            "message": "No connected cloud identity providers",
            "events_created": 0,
            "summary": get_summary(tid),
        }

    total_events = 0
    sources: List[str] = []
    for cfg in configs:
        try:
            live = _import_graph_events_for_config(tid, cfg)
            if live > 0:
                total_events += live
                sources.append("microsoft_graph")
            elif _allow_lab_sample_seed():
                total_events += _seed_events_for_config(tid, cfg)
                sources.append("analysis_adapter")
            else:
                sources.append("live_empty")
            execute(
                """
                UPDATE tenant_cloud_identity_configs
                SET last_synced_at = now(), updated_at = now()
                WHERE id = %s::uuid;
                """,
                (cfg["id"],),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ITDR sync failed for config %s", cfg.get("id"))
            return {
                "tenant_id": tid,
                "sync_status": "error",
                "message": str(exc)[:300],
                "events_created": total_events,
                "summary": get_summary(tid),
            }

    _enable_entitlement(tid)
    source = "+".join(sorted(set(sources))) if sources else "none"
    if total_events == 0:
        return {
            "tenant_id": tid,
            "sync_status": "empty",
            "message": "Identity provider returned no events",
            "events_created": 0,
            "configs_synced": len(configs),
            "source": source,
            "summary": get_summary(tid),
            "engine_label": ENGINE_LABEL,
        }
    return {
        "tenant_id": tid,
        "sync_status": "ok",
        "message": "Cloud identity analysis refreshed",
        "events_created": total_events,
        "configs_synced": len(configs),
        "source": source,
        "summary": get_summary(tid),
        "engine_label": ENGINE_LABEL,
    }


def tenant_has_itdr_data(tenant_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok
        FROM tenant_cloud_identity_configs
        WHERE tenant_id = %s::uuid AND status = 'CONNECTED'
        LIMIT 1;
        """,
        (tenant_id,),
    )
    return bool(row)
