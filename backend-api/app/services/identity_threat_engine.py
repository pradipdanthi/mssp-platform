"""Phase 6: Okta / Active Directory identity telemetry threat detection."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

from app.db.session import db_transaction

logger = logging.getLogger(__name__)

MFA_FATIGUE_WINDOW = timedelta(minutes=5)
MFA_FATIGUE_FAILURE_THRESHOLD = 3
IMPOSSIBLE_TRAVEL_WINDOW = timedelta(minutes=30)
IMPOSSIBLE_TRAVEL_MIN_DISTANCE_KM = 500.0

OKTA_MFA_FAILURE_EVENTS = frozenset(
    {
        "user.authentication.auth_via_mfa",
        "user.mfa.factor.verify",
        "user.mfa.factor.challenge",
    }
)
OKTA_LOGIN_SUCCESS_EVENTS = frozenset(
    {
        "user.session.start",
        "user.authentication.sso",
        "user.authentication.auth_via_mfa",
    }
)

# In-process sliding window per (tenant_id, source, user_principal).
_EVENT_STORE: Dict[Tuple[str, str, str], Deque[Dict[str, Any]]] = defaultdict(deque)
_STORE_MAXLEN = 256


@dataclass
class IdentityDetection:
    detection_type: str
    source_tool: str
    severity: str
    subject_user: str
    target_ip: Optional[str]
    event_ids: List[str] = field(default_factory=list)
    risk_indicators: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not value:
        return _utcnow()
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return _utcnow()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def clear_event_store() -> None:
    """Reset in-process detection windows (tests)."""
    _EVENT_STORE.clear()


def _store_key(tenant_id: str, source: str, user: str) -> Tuple[str, str, str]:
    return (tenant_id, source, (user or "").strip().lower())


def _append_event(
    tenant_id: str,
    source: str,
    user: str,
    *,
    event_time: datetime,
    event_id: str,
    ip_address: Optional[str],
    outcome: Optional[str],
    location: Optional[Dict[str, Any]],
    raw: Dict[str, Any],
) -> None:
    key = _store_key(tenant_id, source, user)
    bucket = _EVENT_STORE[key]
    bucket.append(
        {
            "event_time": event_time,
            "event_id": event_id,
            "ip_address": ip_address,
            "outcome": (outcome or "").upper(),
            "location": location or {},
            "raw": raw,
        }
    )
    while len(bucket) > _STORE_MAXLEN:
        bucket.popleft()


def _recent_events(
    tenant_id: str,
    source: str,
    user: str,
    *,
    window: timedelta,
    before: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    cutoff = (before or _utcnow()) - window
    key = _store_key(tenant_id, source, user)
    return [e for e in _EVENT_STORE.get(key, ()) if e["event_time"] >= cutoff]


def _okta_outcome(event: Dict[str, Any]) -> str:
    outcome = event.get("outcome")
    if isinstance(outcome, dict):
        return str(outcome.get("result") or "").upper()
    return str(event.get("result") or "").upper()


def _okta_user(event: Dict[str, Any]) -> str:
    actor = event.get("actor")
    if isinstance(actor, dict):
        for key in ("alternateId", "displayName", "id"):
            val = actor.get(key)
            if val:
                return str(val)
    return str(event.get("user") or event.get("userPrincipalName") or "unknown")


def _okta_ip(event: Dict[str, Any]) -> Optional[str]:
    client = event.get("client")
    if isinstance(client, dict) and client.get("ipAddress"):
        return str(client["ipAddress"])
    request = event.get("request")
    if isinstance(request, dict) and request.get("ip"):
        return str(request["ip"])
    return None


def _okta_location(event: Dict[str, Any]) -> Dict[str, Any]:
    geo = event.get("geographicalContext") or event.get("client", {}).get("geographicalContext")
    if isinstance(geo, dict):
        return {
            "country": geo.get("country"),
            "city": geo.get("city"),
            "state": geo.get("state"),
        }
    return {}


def _ad_event_id(event: Dict[str, Any]) -> Optional[int]:
    for key in ("EventID", "event_id", "eventId", "Id"):
        if key in event:
            try:
                return int(event[key])
            except (TypeError, ValueError):
                continue
    system = event.get("System") or event.get("system")
    if isinstance(system, dict):
        for key in ("EventID", "EventId"):
            if key in system:
                try:
                    return int(system[key])
                except (TypeError, ValueError):
                    continue
    return None


def _ad_field(event: Dict[str, Any], *names: str) -> Optional[str]:
    for name in names:
        if name in event and event[name] not in (None, ""):
            return str(event[name])
    event_data = event.get("EventData") or event.get("event_data") or event.get("data")
    if isinstance(event_data, dict):
        for name in names:
            if name in event_data and event_data[name] not in (None, ""):
                return str(event_data[name])
    if isinstance(event_data, list):
        for item in event_data:
            if not isinstance(item, dict):
                continue
            key = item.get("Name") or item.get("name")
            if key in names:
                val = item.get("Value") or item.get("value")
                if val not in (None, ""):
                    return str(val)
    return None


def _ad_user(event: Dict[str, Any]) -> str:
    return (
        _ad_field(event, "TargetUserName", "target_user_name", "SubjectUserName", "AccountName")
        or "unknown"
    )


def _ad_ip(event: Dict[str, Any]) -> Optional[str]:
    return _ad_field(event, "IpAddress", "ip_address", "ClientAddress", "SourceNetworkAddress")


def _is_machine_account(name: str) -> bool:
    account = (name or "").strip()
    if not account:
        return False
    if account.endswith("$"):
        return True
    return account.lower().endswith("$")


def _ip_subnet(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.split("%")[0].strip())
        if isinstance(addr, ipaddress.IPv4Address):
            net = ipaddress.ip_network(f"{addr}/24", strict=False)
            return str(net.network_address)
        net = ipaddress.ip_network(f"{addr}/64", strict=False)
        return str(net.network_address)
    except ValueError:
        return ip


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _location_coords(location: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat = location.get("lat") or location.get("latitude")
    lon = location.get("lon") or location.get("longitude")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None
    return None


def detect_mfa_fatigue(
    tenant_id: str,
    user: str,
    *,
    current_outcome: str,
    current_event_id: str,
    current_time: Optional[datetime] = None,
) -> Optional[IdentityDetection]:
    """>3 MFA failures/denials within 5 minutes followed by success."""
    now = current_time or _utcnow()
    outcome = (current_outcome or "").upper()
    if outcome not in ("SUCCESS", "ALLOW"):
        return None

    recent = _recent_events(tenant_id, "okta", user, window=MFA_FATIGUE_WINDOW, before=now)
    failures = [
        e
        for e in recent
        if e["outcome"] in ("FAILURE", "DENY", "DENIED")
        and e["event_id"] in OKTA_MFA_FAILURE_EVENTS
    ]
    if len(failures) <= MFA_FATIGUE_FAILURE_THRESHOLD:
        return None

    failure_ids = [e["event_id"] for e in failures]
    return IdentityDetection(
        detection_type="mfa_fatigue",
        source_tool="okta",
        severity="high",
        subject_user=user,
        target_ip=failures[-1].get("ip_address"),
        event_ids=failure_ids + [current_event_id],
        risk_indicators=[
            f"{len(failures)} MFA failures within 5 minutes",
            "successful authentication after repeated MFA denials",
        ],
        details={
            "failure_count": len(failures),
            "window_minutes": int(MFA_FATIGUE_WINDOW.total_seconds() // 60),
            "last_failure_ips": [e.get("ip_address") for e in failures[-3:]],
        },
    )


def detect_impossible_travel(
    tenant_id: str,
    source: str,
    user: str,
    *,
    current_ip: Optional[str],
    current_location: Dict[str, Any],
    current_time: Optional[datetime] = None,
) -> Optional[IdentityDetection]:
    """Two distinct subnets/locations within impossible travel window."""
    now = current_time or _utcnow()
    current_subnet = _ip_subnet(current_ip)
    recent = _recent_events(tenant_id, source, user, window=IMPOSSIBLE_TRAVEL_WINDOW, before=now)
    if not recent:
        return None

    prior = recent[-1]
    prior_ip = prior.get("ip_address")
    prior_subnet = _ip_subnet(prior_ip)
    prior_loc = prior.get("location") or {}
    prior_time = prior["event_time"]
    delta = now - prior_time
    if delta > IMPOSSIBLE_TRAVEL_WINDOW or delta <= timedelta(0):
        return None

    distinct_subnet = bool(
        current_subnet and prior_subnet and current_subnet != prior_subnet
    )
    distinct_location = bool(
        current_location.get("country")
        and prior_loc.get("country")
        and current_location.get("country") != prior_loc.get("country")
    )
    if not distinct_subnet and not distinct_location:
        return None

    coords_a = _location_coords(prior_loc)
    coords_b = _location_coords(current_location)
    if coords_a and coords_b:
        distance_km = _haversine_km(coords_a[0], coords_a[1], coords_b[0], coords_b[1])
        if distance_km < IMPOSSIBLE_TRAVEL_MIN_DISTANCE_KM:
            return None

    minutes_apart = max(1, int(delta.total_seconds() // 60))
    return IdentityDetection(
        detection_type="impossible_travel",
        source_tool="okta" if source == "okta" else "active_directory",
        severity="critical",
        subject_user=user,
        target_ip=current_ip,
        event_ids=[prior.get("event_id", ""), "login"],
        risk_indicators=[
            f"logins from distinct locations {minutes_apart} minutes apart",
            f"prior_ip={prior_ip} current_ip={current_ip}",
        ],
        details={
            "prior_ip": prior_ip,
            "current_ip": current_ip,
            "prior_location": prior_loc,
            "current_location": current_location,
            "minutes_apart": minutes_apart,
        },
    )


def detect_kerberoasting(event: Dict[str, Any]) -> Optional[IdentityDetection]:
    """Event ID 4769 with RC4 (0x17) for non-machine account SPN."""
    event_id = _ad_event_id(event)
    if event_id != 4769:
        return None

    enc_type = (
        _ad_field(event, "TicketEncryptionType", "ticket_encryption_type", "EncryptionType")
        or ""
    ).lower()
    if enc_type not in ("0x17", "23", "rc4-hmac"):
        return None

    target_user = _ad_field(event, "TargetUserName", "target_user_name") or ""
    service_name = _ad_field(event, "ServiceName", "service_name") or ""
    if _is_machine_account(target_user) or _is_machine_account(service_name.split("/")[-1]):
        return None

    subject = _ad_user(event)
    return IdentityDetection(
        detection_type="kerberoasting",
        source_tool="active_directory",
        severity="critical",
        subject_user=subject,
        target_ip=_ad_ip(event),
        event_ids=["4769"],
        risk_indicators=[
            "Kerberos TGS request with RC4 (0x17) encryption",
            f"target_service={service_name}",
        ],
        details={
            "event_id": 4769,
            "encryption_type": enc_type,
            "service_name": service_name,
            "target_user_name": target_user,
        },
    )


def _external_alert_id(detection: IdentityDetection, tenant_id: str) -> str:
    digest = hashlib.sha256(
        f"{tenant_id}:{detection.detection_type}:{detection.subject_user}:"
        f"{':'.join(detection.event_ids)}".encode()
    ).hexdigest()[:24]
    return f"identity:{detection.source_tool}:{detection.detection_type}:{digest}"


def emit_identity_alert(
    tenant_id: str,
    detection: IdentityDetection,
    *,
    event_time: Optional[datetime] = None,
    cur=None,
) -> Optional[str]:
    """Persist normalized alert to security_alerts; returns alert id."""
    title_map = {
        "mfa_fatigue": "MFA fatigue attack detected",
        "impossible_travel": "Impossible travel login detected",
        "kerberoasting": "Kerberoasting activity detected",
    }
    description_map = {
        "mfa_fatigue": (
            f"User {detection.subject_user} had repeated MFA denials followed by a "
            "successful authentication."
        ),
        "impossible_travel": (
            f"User {detection.subject_user} authenticated from geographically distant "
            "locations within an implausible time window."
        ),
        "kerberoasting": (
            f"Suspicious Kerberos TGS (4769) with RC4 encryption targeting "
            f"{detection.details.get('service_name') or 'a service principal'}."
        ),
    }
    details = {
        "subject_user": detection.subject_user,
        "target_ip": detection.target_ip,
        "event_ids": detection.event_ids,
        "risk_indicators": detection.risk_indicators,
        "detection_type": detection.detection_type,
        **detection.details,
    }
    external_id = _external_alert_id(detection, tenant_id)
    params = (
        tenant_id,
        detection.source_tool,
        external_id,
        detection.severity,
        title_map.get(detection.detection_type, "Identity threat detected"),
        description_map.get(detection.detection_type, ""),
        event_time or _utcnow(),
        detection.target_ip,
        detection.subject_user,
        json.dumps(details),
    )
    if cur is not None:
        return _insert_alert_with_cur(cur, tenant_id, detection.source_tool, external_id, params)
    with db_transaction() as txn_cur:
        return _insert_alert_with_cur(
            txn_cur, tenant_id, detection.source_tool, external_id, params
        )


def _insert_alert_with_cur(
    cur,
    tenant_id: str,
    source_tool: str,
    external_id: str,
    params: tuple,
) -> Optional[str]:
    lock_key = f"{tenant_id}:{source_tool}:{external_id}"
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));", (lock_key,))
    cur.execute(
        """
        SELECT id::text FROM security_alerts
        WHERE tenant_id = %s::uuid AND source_tool = %s AND external_alert_id = %s
        LIMIT 1;
        """,
        (tenant_id, source_tool, external_id),
    )
    existing = cur.fetchone()
    if existing:
        return existing["id"]
    cur.execute(
        """
        INSERT INTO security_alerts (
            tenant_id, source_tool, external_alert_id,
            severity, alert_title, alert_description, event_time,
            source_ip, source_user, raw_event, customer_visible, status
        )
        VALUES (
            %s::uuid, %s, %s,
            %s, %s, %s, %s,
            %s::inet, %s, %s::jsonb, true, 'new'
        )
        RETURNING id::text;
        """,
        params,
    )
    row = cur.fetchone()
    return row["id"] if row else None


def process_okta_event(tenant_id: str, event: Dict[str, Any], *, cur=None) -> List[str]:
    """Ingest one Okta System Log event; return created alert ids."""
    if not isinstance(event, dict):
        return []
    event_type = str(event.get("eventType") or event.get("event_type") or "")
    user = _okta_user(event)
    event_time = _parse_ts(event.get("published") or event.get("timestamp"))
    outcome = _okta_outcome(event)
    ip_address = _okta_ip(event)
    location = _okta_location(event)
    event_uuid = str(event.get("uuid") or event.get("id") or event_type)

    _append_event(
        tenant_id,
        "okta",
        user,
        event_time=event_time,
        event_id=event_type,
        ip_address=ip_address,
        outcome=outcome,
        location=location,
        raw=event,
    )

    detections: List[IdentityDetection] = []
    if event_type in OKTA_MFA_FAILURE_EVENTS and outcome in ("SUCCESS", "ALLOW"):
        det = detect_mfa_fatigue(
            tenant_id,
            user,
            current_outcome=outcome,
            current_event_id=event_type,
            current_time=event_time,
        )
        if det:
            detections.append(det)
    if event_type in OKTA_LOGIN_SUCCESS_EVENTS and outcome in ("SUCCESS", "ALLOW", ""):
        det = detect_impossible_travel(
            tenant_id,
            "okta",
            user,
            current_ip=ip_address,
            current_location=location,
            current_time=event_time,
        )
        if det:
            detections.append(det)

    alert_ids: List[str] = []
    for det in detections:
        alert_id = emit_identity_alert(tenant_id, det, event_time=event_time, cur=cur)
        if alert_id:
            alert_ids.append(alert_id)
            logger.info(
                "identity alert emitted tenant=%s type=%s user=%s alert=%s",
                tenant_id,
                det.detection_type,
                user,
                alert_id,
            )
    return alert_ids


def process_ad_event(tenant_id: str, event: Dict[str, Any], *, cur=None) -> List[str]:
    """Ingest one Windows security event; return created alert ids."""
    if not isinstance(event, dict):
        return []
    event_id = _ad_event_id(event)
    user = _ad_user(event)
    event_time = _parse_ts(
        _ad_field(event, "TimeCreated", "time_created", "@timestamp") or event.get("timestamp")
    )
    ip_address = _ad_ip(event)

    if event_id in (4624, 4625):
        outcome = "SUCCESS" if event_id == 4624 else "FAILURE"
        _append_event(
            tenant_id,
            "active_directory",
            user,
            event_time=event_time,
            event_id=str(event_id),
            ip_address=ip_address,
            outcome=outcome,
            location={},
            raw=event,
        )
        if event_id == 4624:
            det = detect_impossible_travel(
                tenant_id,
                "active_directory",
                user,
                current_ip=ip_address,
                current_location={},
                current_time=event_time,
            )
            if det:
                alert_id = emit_identity_alert(tenant_id, det, event_time=event_time, cur=cur)
                return [alert_id] if alert_id else []

    kerb = detect_kerberoasting(event)
    if kerb:
        alert_id = emit_identity_alert(tenant_id, kerb, event_time=event_time, cur=cur)
        return [alert_id] if alert_id else []
    return []


def configured_identity_api_key() -> str:
    direct = (os.getenv("IDENTITY_TELEMETRY_API_KEY") or "").strip()
    if direct:
        return direct
    key_file = (os.getenv("IDENTITY_TELEMETRY_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            with open(key_file, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""
    for path in (
        "/run/secrets/identity_telemetry_api_key",
        "/opt/mssp-control/.secrets/identity_telemetry_api_key",
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                value = fh.read().strip()
                if value:
                    return value
        except OSError:
            continue
    return ""
