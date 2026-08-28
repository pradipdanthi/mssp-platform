"""Shared SQL facet filters for admin/customer alert list endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional


def _like_pattern(raw: str) -> str:
    """Support simple wildcards: * → % ; otherwise wrap with % for contains."""
    s = (raw or "").strip()
    if not s:
        return "%"
    if "*" in s or "?" in s:
        return s.replace("*", "%").replace("?", "_")
    return f"%{s}%"


def append_alert_time_filter(
    where: List[str],
    params: list,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> None:
    """
    Time window on COALESCE(event_time, created_at).

    ``since`` may be a relative token (15m, 1h, 24h, 7d) or ISO-8601 timestamp.
    ``until`` is ISO-8601 only.
    """
    now = datetime.now(timezone.utc)
    since_raw = (since or "").strip().lower()
    until_raw = (until or "").strip()

    since_dt: Optional[datetime] = None
    if since_raw in ("15m", "15min"):
        since_dt = now - timedelta(minutes=15)
    elif since_raw in ("1h", "60m"):
        since_dt = now - timedelta(hours=1)
    elif since_raw in ("24h", "1d"):
        since_dt = now - timedelta(hours=24)
    elif since_raw in ("7d", "7days"):
        since_dt = now - timedelta(days=7)
    elif since_raw:
        try:
            since_dt = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
        except ValueError:
            since_dt = None

    if since_dt is not None:
        where.append("COALESCE(sa.event_time, sa.created_at) >= %s")
        params.append(since_dt)

    if until_raw:
        try:
            until_dt = datetime.fromisoformat(until_raw.replace("Z", "+00:00"))
            where.append("COALESCE(sa.event_time, sa.created_at) <= %s")
            params.append(until_dt)
        except ValueError:
            pass


def append_alert_facet_filters(
    where: List[str],
    params: list,
    *,
    rule_id: Optional[str] = None,
    hostname: Optional[str] = None,
    process_name: Optional[str] = None,
    path: Optional[str] = None,
    user: Optional[str] = None,
    hash_value: Optional[str] = None,
    cmdline: Optional[str] = None,
) -> None:
    """
    Faceted filters over destination_host + common Wazuh raw_event JSON paths.
    Path/process/cmdline support simple * wildcards.
    """
    rid = (rule_id or "").strip()
    if rid:
        where.append(
            "("
            "COALESCE(sa.raw_event->'rule'->>'id', '') = %s OR "
            "COALESCE(sa.raw_event->>'rule_id', '') = %s OR "
            "COALESCE(sa.external_alert_id, '') = %s"
            ")"
        )
        params.extend([rid, rid, rid])

    host = (hostname or "").strip()
    if host:
        where.append(
            "("
            "COALESCE(sa.destination_host, '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'agent'->>'name', '') ILIKE %s"
            ")"
        )
        like_host = _like_pattern(host)
        params.extend([like_host, like_host])

    proc = (process_name or "").strip()
    if proc:
        where.append(
            "("
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'Image', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'image', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->>'process_name', '') ILIKE %s"
            ")"
        )
        like_proc = _like_pattern(proc)
        params.extend([like_proc, like_proc, like_proc])

    pth = (path or "").strip()
    if pth:
        where.append(
            "("
            "COALESCE(sa.raw_event->'syscheck'->>'path', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'TargetFilename', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'FilePath', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->>'path', '') ILIKE %s"
            ")"
        )
        like_path = _like_pattern(pth)
        params.extend([like_path, like_path, like_path, like_path])

    usr = (user or "").strip()
    if usr:
        where.append(
            "("
            "COALESCE(sa.source_user, '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'User', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->>'user', '') ILIKE %s"
            ")"
        )
        like_user = _like_pattern(usr)
        params.extend([like_user, like_user, like_user])

    hv = (hash_value or "").strip()
    if hv:
        where.append(
            "("
            "COALESCE(sa.raw_event->'syscheck'->>'sha256_after', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'syscheck'->>'md5_after', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'Hashes', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->>'sha256', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->>'md5', '') ILIKE %s"
            ")"
        )
        like_hash = f"%{hv}%"
        params.extend([like_hash] * 5)

    cmd = (cmdline or "").strip()
    if cmd:
        where.append(
            "("
            "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'CommandLine', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->>'command', '') ILIKE %s OR "
            "COALESCE(sa.raw_event->'data'->>'cmd', '') ILIKE %s"
            ")"
        )
        like_cmd = _like_pattern(cmd)
        params.extend([like_cmd, like_cmd, like_cmd])


def append_rich_alert_q_filter(
    where: List[str],
    params: list,
    q: Optional[str],
    *,
    include_tenant_fields: bool = True,
) -> None:
    """Richer free-text q across title/description/rule/host/process/path/user/cmdline/hash."""
    q_clean = (q or "").strip()
    if not q_clean:
        return
    like = f"%{q_clean}%"
    clauses = [
        "sa.alert_title ILIKE %s",
        "COALESCE(sa.alert_description, '') ILIKE %s",
        "COALESCE(sa.destination_host, '') ILIKE %s",
        "COALESCE(sa.ai_plain_summary, '') ILIKE %s",
        "COALESCE(sa.external_alert_id, '') ILIKE %s",
        "COALESCE(sa.source_user, '') ILIKE %s",
        "COALESCE(sa.raw_event->'rule'->>'id', '') ILIKE %s",
        "COALESCE(sa.raw_event->'agent'->>'name', '') ILIKE %s",
        "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'Image', '') ILIKE %s",
        "COALESCE(sa.raw_event->'syscheck'->>'path', '') ILIKE %s",
        "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'TargetFilename', '') ILIKE %s",
        "COALESCE(sa.raw_event->'data'->'win'->'eventdata'->>'CommandLine', '') ILIKE %s",
        "COALESCE(sa.raw_event->'syscheck'->>'sha256_after', '') ILIKE %s",
    ]
    params.extend([like] * len(clauses))
    if include_tenant_fields:
        clauses.extend(["t.name ILIKE %s", "t.short_code ILIKE %s"])
        params.extend([like, like])
    where.append("(" + " OR ".join(clauses) + ")")
