"""TIA conversation state, bound pending actions, and verified dashboard commands.

What this layer guarantees
  * A conversation belongs to ONE operator, ONE browser session and ONE tenant scope
    (or the platform scope). Changing tenant starts a different conversation and
    cancels what was pending in the old one, so nothing crosses customers.
  * "Yes" is resolved by the server against a stored pending action bound to its type,
    its exact target, the tenant, the session and an expiry. The model never sees or
    decides it, and a bare "yes" cannot authorise anything else.
  * Opening a case is a command with a lifecycle: issued -> acknowledged | failed |
    expired. TIA says "I've asked your dashboard" when it issues the command and says
    "it is open" only after the dashboard reports the loaded alert id and the server
    has compared it with the target.
  * A repeated ``client_turn_id`` returns the stored response and never re-executes.
  * Disruptive requests (isolate, disable, block, contain) are refused here and pointed
    at the approval workflow. A spoken or typed "yes" is not approval.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.db.session import db_transaction, fetch_one
from app.services import tia_tools as tools
from app.services.tia_tools import Scope, ToolError

logger = logging.getLogger(__name__)

SCHEMA_COMPONENT = "tia_conversation"
SCHEMA_VERSION_REQUIRED = 119
_REQUIRED_TABLES = ("tia_conversations", "tia_conversation_turns", "tia_pending_actions", "tia_ui_commands", "tia_turn_timings")


class ConversationNotReady(RuntimeError):
    pass


class TurnInProgress(RuntimeError):
    pass


def _pending_ttl() -> int:
    return max(30, int(os.getenv("TIA_PENDING_TTL_SECONDS", "180") or 180))


def _command_ttl() -> int:
    return max(10, int(os.getenv("TIA_UI_COMMAND_TTL_SECONDS", "90") or 90))


_schema_cache: Tuple[float, Optional[str]] = (0.0, None)


def schema_fault() -> Optional[str]:
    """None when migration 119 is in place, otherwise a short reason. Cached 30 s."""
    global _schema_cache
    now = time.monotonic()
    if now - _schema_cache[0] < 30 and _schema_cache[0] > 0:
        return _schema_cache[1]
    fault: Optional[str] = None
    try:
        for table in _REQUIRED_TABLES:
            if not fetch_one("SELECT to_regclass(%s) IS NOT NULL AS present;", (f"public.{table}",)).get("present"):
                fault = f"missing table {table}"
                break
        if fault is None:
            ver = fetch_one("SELECT version FROM tia_schema_version WHERE component = %s;", (SCHEMA_COMPONENT,))
            if not ver or int(ver["version"]) < SCHEMA_VERSION_REQUIRED:
                fault = f"tia_conversation schema below {SCHEMA_VERSION_REQUIRED}"
    except Exception as exc:  # noqa: BLE001
        fault = f"database check failed: {type(exc).__name__}"
    _schema_cache = (now, fault)
    return fault


def reset_schema_cache() -> None:
    global _schema_cache
    _schema_cache = (0.0, None)


def require_schema() -> None:
    fault = schema_fault()
    if fault:
        raise ConversationNotReady(fault)


# --------------------------------------------------------------------------
# conversation + turn bookkeeping
# --------------------------------------------------------------------------


def _scope_params(scope: Scope) -> Tuple[Any, ...]:
    return (scope.operator_email, scope.session_id, scope.tenant_id)


def get_conversation(scope: Scope, view_alert_id: Optional[str] = None) -> Dict[str, Any]:
    """Find or create the conversation for (operator, session, tenant scope).

    Anything still pending for this operator+session in a DIFFERENT tenant scope is
    cancelled first, so a tenant switch can never be confirmed afterwards.
    """
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE tia_pending_actions SET status = 'cancelled', resolution = 'scope_changed', resolved_at = now()
            WHERE operator_email = %s AND session_id = %s AND status = 'pending'
              AND tenant_id IS DISTINCT FROM %s::uuid;
            """,
            _scope_params(scope),
        )
        cur.execute(
            """
            UPDATE tia_ui_commands SET status = 'expired', failure_reason = 'scope_changed'
            WHERE operator_email = %s AND session_id = %s AND status = 'issued'
              AND tenant_id IS DISTINCT FROM %s::uuid;
            """,
            _scope_params(scope),
        )
        cur.execute(
            """
            UPDATE tia_conversations SET selected_alert_id = NULL, updated_at = now()
            WHERE operator_email = %s AND session_id = %s
              AND tenant_id IS DISTINCT FROM %s::uuid
              AND selected_alert_id IS NOT NULL;
            """,
            _scope_params(scope),
        )
        cur.execute(
            """
            SELECT id::text AS id, selected_alert_id::text AS selected_alert_id, referenced_alert_ids, last_listing, turn_count
            FROM tia_conversations
            WHERE operator_email = %s AND session_id = %s AND tenant_id IS NOT DISTINCT FROM %s::uuid
              AND expires_at > now()
            ORDER BY updated_at DESC LIMIT 1;
            """,
            _scope_params(scope),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO tia_conversations (operator_email, operator_id, session_id, tenant_id)
                VALUES (%s, %s::uuid, %s, %s::uuid)
                RETURNING id::text AS id, selected_alert_id::text AS selected_alert_id, referenced_alert_ids, last_listing, turn_count;
                """,
                (scope.operator_email, scope.operator_id, scope.session_id, scope.tenant_id),
            )
            row = cur.fetchone()
    conv = dict(row)
    conv["referenced_alert_ids"] = list(conv.get("referenced_alert_ids") or [])
    listing = conv.get("last_listing") or {}
    if isinstance(listing, str):
        listing = json.loads(listing)
    conv["last_listing"] = listing if isinstance(listing, dict) else {}
    conv["pinned_alert_id"] = tools.valid_uuid(conv["last_listing"].get("pinned_alert_id"))
    # "Selected" is the conversation's focus and survives navigation; "on screen" is only what
    # the dashboard reports this turn. Offering to open a case depends on the second.
    conv["on_screen_alert_id"] = None
    if view_alert_id and tools.get_alert_row(scope, view_alert_id):
        # The dashboard is authoritative about what is on screen, but only inside the scope.
        conv["selected_alert_id"] = conv["on_screen_alert_id"] = tools.valid_uuid(view_alert_id)
        _set_selected(conv["id"], conv["selected_alert_id"])
    return conv


def _set_selected(conversation_id: str, alert_id: Optional[str]) -> None:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_conversations SET selected_alert_id = %s::uuid, updated_at = now(), "
            "expires_at = now() + interval '8 hours' WHERE id = %s::uuid;",
            (alert_id, conversation_id),
        )


def _listing_meta(conversation_id: str) -> Dict[str, Any]:
    row = fetch_one("SELECT last_listing FROM tia_conversations WHERE id = %s::uuid;", (conversation_id,))
    raw = (row or {}).get("last_listing") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw if isinstance(raw, dict) else {}


def _pin_alert(conversation_id: str, alert_id: Optional[str], *, topic: Optional[str] = None) -> None:
    """Remember the case across topic changes. Listing may clear selection; the pin stays."""
    meta = _listing_meta(conversation_id)
    if alert_id:
        meta["pinned_alert_id"] = alert_id
    if topic:
        stack = list(meta.get("topic_stack") or [])
        if not stack or stack[-1] != topic:
            stack.append(topic)
        meta["topic_stack"] = stack[-8:]
        meta["topic"] = topic
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_conversations SET last_listing = %s::jsonb, updated_at = now() WHERE id = %s::uuid;",
            (json.dumps(meta), conversation_id),
        )


def _set_listing(conversation_id: str, alert_ids: List[str], summary: Dict[str, Any]) -> None:
    prev = _listing_meta(conversation_id)
    merged = {**prev, **summary, "n": len(alert_ids), "source": summary.get("source", "listing")}
    if prev.get("pinned_alert_id") and "pinned_alert_id" not in summary:
        merged["pinned_alert_id"] = prev["pinned_alert_id"]
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_conversations SET referenced_alert_ids = %s::jsonb, last_listing = %s::jsonb, "
            "selected_alert_id = NULL, updated_at = now() WHERE id = %s::uuid;",
            (json.dumps(alert_ids), json.dumps(merged), conversation_id),
        )


def remember_listing(scope: Scope) -> List[Dict[str, Any]]:
    """Store the same list_alerts order the operator just heard (welcome or 'what's critical').

    Welcome used to speak snapshot titles without writing ids, so 'the first one' had nothing
    to resolve. This is scoped to the authenticated operator, browser session and tenant.
    """
    require_schema()
    conv = get_conversation(scope)
    rows = tools.list_alerts(scope, limit=5)
    ids = [r["id"] for r in rows]
    pin = conv.get("selected_alert_id") or conv.get("pinned_alert_id")
    extra: Dict[str, Any] = {"n": len(rows), "source": "listing"}
    if pin:
        extra["pinned_alert_id"] = pin
    _set_listing(conv["id"], ids, extra)
    _cancel_live_pending(conv["id"], "listing_changed")
    conv["referenced_alert_ids"] = ids
    conv["selected_alert_id"] = None
    conv["pinned_alert_id"] = pin
    return rows


def begin_turn(conv_id: str, client_turn_id: Optional[str], text: str, request_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Record the operator's turn. Returns ('new'|'replay', stored_response).

    A repeated client_turn_id returns the stored response. If the first attempt is still
    running (no response yet) TurnInProgress is raised; if it died long ago it is re-run.
    """
    with db_transaction() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (conv_id,))
        if client_turn_id:
            cur.execute(
                "SELECT id::text AS id, response, EXTRACT(EPOCH FROM (now() - created_at)) AS age "
                "FROM tia_conversation_turns WHERE conversation_id = %s::uuid AND client_turn_id = %s AND role = 'operator';",
                (conv_id, client_turn_id),
            )
            prior = cur.fetchone()
            if prior:
                if prior["response"] is not None:
                    return "replay", prior["response"]
                if float(prior["age"]) < 60:
                    raise TurnInProgress(client_turn_id)
                cur.execute("UPDATE tia_conversation_turns SET created_at = now() WHERE id = %s::uuid;", (prior["id"],))
                return "new", None
        cur.execute(
            "SELECT coalesce(max(turn_no), 0) + 1 AS n FROM tia_conversation_turns WHERE conversation_id = %s::uuid;",
            (conv_id,),
        )
        turn_no = int(cur.fetchone()["n"])
        cur.execute(
            "INSERT INTO tia_conversation_turns (conversation_id, turn_no, client_turn_id, request_id, role, text) "
            "VALUES (%s::uuid, %s, %s, %s, 'operator', %s);",
            (conv_id, turn_no, client_turn_id, request_id, text[:4000]),
        )
        cur.execute(
            "UPDATE tia_conversations SET turn_count = turn_count + 1, updated_at = now(), "
            "expires_at = now() + interval '8 hours' WHERE id = %s::uuid;",
            (conv_id,),
        )
    return "new", None


def finish_turn(conv_id: str, client_turn_id: Optional[str], request_id: str, response: Dict[str, Any]) -> None:
    text = str(response.get("answer") or "")[:4000]
    with db_transaction() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (conv_id,))
        cur.execute(
            "SELECT coalesce(max(turn_no), 0) + 1 AS n FROM tia_conversation_turns WHERE conversation_id = %s::uuid;",
            (conv_id,),
        )
        turn_no = int(cur.fetchone()["n"])
        cur.execute(
            "INSERT INTO tia_conversation_turns (conversation_id, turn_no, request_id, role, text, tool_name, tool_ok, response) "
            "VALUES (%s::uuid, %s, %s, 'tia', %s, %s, %s, %s::jsonb);",
            (conv_id, turn_no, request_id, text, response.get("tool"), response.get("tool_ok"), json.dumps(response, default=str)),
        )
        if client_turn_id:
            cur.execute(
                "UPDATE tia_conversation_turns SET response = %s::jsonb "
                "WHERE conversation_id = %s::uuid AND client_turn_id = %s AND role = 'operator';",
                (json.dumps(response, default=str), conv_id, client_turn_id),
            )
        else:
            cur.execute(
                "UPDATE tia_conversation_turns SET response = %s::jsonb WHERE conversation_id = %s::uuid "
                "AND role = 'operator' AND request_id = %s;",
                (json.dumps(response, default=str), conv_id, request_id),
            )


# --------------------------------------------------------------------------
# pending actions
# --------------------------------------------------------------------------


def _create_pending(conv_id: str, scope: Scope, action_type: str, target: Dict[str, Any], summary: str, risk: str) -> Dict[str, Any]:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_pending_actions SET status = 'cancelled', resolution = 'superseded', resolved_at = now() "
            "WHERE conversation_id = %s::uuid AND status = 'pending';",
            (conv_id,),
        )
        cur.execute(
            """
            INSERT INTO tia_pending_actions
                (conversation_id, operator_email, session_id, tenant_id, action_type, target, summary, risk_class, expires_at)
            VALUES (%s::uuid, %s, %s, %s::uuid, %s, %s::jsonb, %s, %s, now() + make_interval(secs => %s))
            RETURNING id::text AS id, action_type, summary, (expires_at AT TIME ZONE 'utc')::text AS expires_at;
            """,
            (conv_id, scope.operator_email, scope.session_id, scope.tenant_id, action_type, json.dumps(target), summary, risk, _pending_ttl()),
        )
        return dict(cur.fetchone())


def _live_pending(conv_id: str) -> Optional[Dict[str, Any]]:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_pending_actions SET status = 'expired', resolution = 'timeout', resolved_at = now() "
            "WHERE conversation_id = %s::uuid AND status = 'pending' AND expires_at <= now();",
            (conv_id,),
        )
        cur.execute(
            "SELECT id::text AS id, action_type, target, summary, risk_class, tenant_id::text AS tenant_id, "
            "session_id, operator_email FROM tia_pending_actions "
            "WHERE conversation_id = %s::uuid AND status = 'pending' ORDER BY created_at DESC LIMIT 1;",
            (conv_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _cancel_live_pending(conv_id: str, reason: str) -> None:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_pending_actions SET status = 'cancelled', resolution = %s, resolved_at = now() "
            "WHERE conversation_id = %s::uuid AND status = 'pending';",
            (reason, conv_id),
        )


def _recently_expired_pending(conv_id: str) -> Optional[Dict[str, Any]]:
    row = fetch_one(
        "SELECT summary FROM tia_pending_actions WHERE conversation_id = %s::uuid AND status = 'expired' "
        "AND resolved_at > now() - interval '10 minutes' ORDER BY resolved_at DESC LIMIT 1;",
        (conv_id,),
    )
    return row or None


def _resolve_pending(pending_id: str, status: str, resolution: str) -> bool:
    """Atomically move pending -> status. False means someone else already resolved it."""
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_pending_actions SET status = %s, resolution = %s, resolved_at = now() "
            "WHERE id = %s::uuid AND status = 'pending' RETURNING id;",
            (status, resolution, pending_id),
        )
        return cur.fetchone() is not None


# --------------------------------------------------------------------------
# dashboard commands
# --------------------------------------------------------------------------


def _issue_open_case(conv_id: str, scope: Scope, target: Dict[str, Any], pending_id: Optional[str]) -> Dict[str, Any]:
    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO tia_ui_commands
                (conversation_id, pending_action_id, operator_email, session_id, tenant_id, command_type, payload, deliver_by)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s::uuid, 'open_case', %s::jsonb, now() + make_interval(secs => %s))
            RETURNING id::text AS id, command_type AS type, payload, status,
                      (deliver_by AT TIME ZONE 'utc')::text AS deliver_by;
            """,
            (conv_id, pending_id, scope.operator_email, scope.session_id, scope.tenant_id, json.dumps(target), _command_ttl()),
        )
        return dict(cur.fetchone())


def _expire_stale_commands(scope: Scope) -> None:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_ui_commands SET status = 'expired', failure_reason = 'dashboard_did_not_confirm' "
            "WHERE operator_email = %s AND session_id = %s AND status = 'issued' AND deliver_by <= now();",
            (scope.operator_email, scope.session_id),
        )


def _unreported_expired_commands(scope: Scope) -> List[str]:
    """Tell the operator once about commands the dashboard never confirmed (no silent timeout)."""
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_ui_commands SET ack_payload = coalesce(ack_payload, '{}'::jsonb) || '{\"reported\": true}'::jsonb "
            "WHERE operator_email = %s AND session_id = %s AND status = 'expired' "
            "AND coalesce(ack_payload ->> 'reported', 'false') <> 'true' AND failure_reason = 'dashboard_did_not_confirm' "
            "RETURNING payload;",
            (scope.operator_email, scope.session_id),
        )
        rows = cur.fetchall()
    return [
        f"Your dashboard never confirmed opening {str((r['payload'] or {}).get('title') or 'the alert')}, so I can't say it is on screen."
        for r in rows
    ]


def pending_commands(scope: Scope) -> List[Dict[str, Any]]:
    """Commands still waiting for this session's dashboard (reconnect recovery)."""
    require_schema()
    _expire_stale_commands(scope)
    with db_transaction() as cur:
        cur.execute(
            "SELECT id::text AS id, command_type AS type, payload, status, (deliver_by AT TIME ZONE 'utc')::text AS deliver_by "
            "FROM tia_ui_commands WHERE operator_email = %s AND session_id = %s AND status = 'issued' "
            "ORDER BY issued_at;",
            (scope.operator_email, scope.session_id),
        )
        return [dict(r) for r in cur.fetchall()]


def command_status(scope: Scope, command_id: str) -> Optional[Dict[str, Any]]:
    require_schema()
    _expire_stale_commands(scope)
    cid = tools.valid_uuid(command_id)
    if not cid:
        return None
    row = fetch_one(
        "SELECT id::text AS id, command_type AS type, payload, status, failure_reason, "
        "(acknowledged_at AT TIME ZONE 'utc')::text AS acknowledged_at, ack_payload "
        "FROM tia_ui_commands WHERE id = %s::uuid AND operator_email = %s AND session_id = %s;",
        (cid, scope.operator_email, scope.session_id),
    )
    return row or None


def acknowledge_command(scope: Scope, command_id: str, *, loaded_alert_id: Optional[str], failure: Optional[str] = None) -> Dict[str, Any]:
    """The dashboard reports the outcome. Success is believed only if the loaded id matches."""
    require_schema()
    cid = tools.valid_uuid(command_id)
    cmd = None
    if cid:
        cmd = fetch_one(
            "SELECT id::text AS id, conversation_id::text AS conversation_id, status, payload, tenant_id::text AS tenant_id, "
            "deliver_by <= now() AS late, ack_payload, failure_reason FROM tia_ui_commands "
            "WHERE id = %s::uuid AND operator_email = %s AND session_id = %s;",
            (cid, scope.operator_email, scope.session_id),
        )
    if not cmd:
        raise ToolError("not_found", "No such dashboard command for this session")
    target_id = str((cmd["payload"] or {}).get("alert_id"))
    title = str((cmd["payload"] or {}).get("title") or "the alert")

    if cmd["status"] == "acknowledged":  # idempotent: same confirmation again
        return {"status": "acknowledged", "verified": True, "duplicate": True, **_confirmation(cmd["payload"])}
    if cmd["status"] == "failed":
        return {"status": "failed", "verified": False, "duplicate": True, "text": "The dashboard did not open that alert."}

    if cmd["status"] == "expired" and cmd.get("failure_reason") == "scope_changed":
        text = "That request was for a different customer scope that you've since left, so I ignored the page load."
        return {"status": "expired", "verified": False, "reason": "scope_changed", "text": text, "spoken": text}

    if failure:
        _finalize_command(cmd["id"], "failed", failure[:120], None)
        text = f"Your dashboard couldn't open {title}. I can't confirm it is on screen."
        _record_tia_turn(cmd["conversation_id"], text, "open_case", False)
        return {"status": "failed", "verified": False, "text": text, "spoken": text}

    # The scope may have changed while the page loaded: re-check the target at ack time.
    scoped = Scope(scope.operator_email, scope.operator_id, scope.role, scope.session_id, cmd["tenant_id"])
    if tools.valid_uuid(loaded_alert_id) != target_id or not tools.get_alert_row(scoped, target_id):
        _finalize_command(cmd["id"], "failed", "wrong_target", {"loaded_alert_id": str(loaded_alert_id)[:64]})
        text = "Your dashboard loaded a different page than the one I asked for, so I can't confirm it."
        _record_tia_turn(cmd["conversation_id"], text, "open_case", False)
        return {"status": "failed", "verified": False, "reason": "wrong_target", "text": text, "spoken": text}

    _finalize_command(cmd["id"], "acknowledged", None, {"loaded_alert_id": target_id, "late": bool(cmd["late"])})
    _set_selected(cmd["conversation_id"], target_id)
    conf = _confirmation(cmd["payload"])
    _record_tia_turn(cmd["conversation_id"], conf["text"], "open_case", True)
    return {"status": "acknowledged", "verified": True, "late": bool(cmd["late"]), "selected_alert_id": target_id, **conf}


def _confirmation(payload: Dict[str, Any]) -> Dict[str, str]:
    title = str(payload.get("title") or "The alert")
    sev = str(payload.get("severity") or "")
    code = str(payload.get("short_code") or "")
    text = f"Confirmed: {title} is open on your screen" + (f" ({sev}, {code})." if sev and code else ".")
    return {"text": text, "spoken": f"{title} is open."}


def _finalize_command(command_id: str, status: str, failure_reason: Optional[str], ack: Optional[Dict[str, Any]]) -> None:
    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_ui_commands SET status = %s, failure_reason = %s, ack_payload = %s::jsonb, "
            "acknowledged_at = CASE WHEN %s = 'acknowledged' THEN now() ELSE acknowledged_at END "
            "WHERE id = %s::uuid AND status IN ('issued', 'expired');",
            (status, failure_reason, json.dumps(ack) if ack is not None else None, status, command_id),
        )


def _record_tia_turn(conv_id: str, text: str, tool: Optional[str], ok: bool) -> None:
    with db_transaction() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (conv_id,))
        cur.execute(
            "SELECT coalesce(max(turn_no), 0) + 1 AS n FROM tia_conversation_turns WHERE conversation_id = %s::uuid;", (conv_id,)
        )
        n = int(cur.fetchone()["n"])
        cur.execute(
            "INSERT INTO tia_conversation_turns (conversation_id, turn_no, request_id, role, text, tool_name, tool_ok) "
            "VALUES (%s::uuid, %s, 'dashboard-ack', 'tia', %s, %s, %s);",
            (conv_id, n, text[:4000], tool, ok),
        )


# --------------------------------------------------------------------------
# language understanding (deterministic; the model is only a fallback for open questions)
# --------------------------------------------------------------------------

_BARE_CONFIRM = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|sure|ok|okay|please|go ahead|do it|confirm|correct|right)"
    r"(?:[,.\s]+(?:yes|yeah|yep|yup|sure|ok|okay|please|go ahead|do it|confirm|correct|right))*"
    r"[,.\s]*$",
    re.I,
)
_AFFIRMATIVE = frozenset("yes yeah yep yup sure ok okay confirm correct ahead".split())
_DECLINE = re.compile(
    r"^\s*(no|nope|nah|cancel|never ?mind|don'?t|do not|stop(?:\s+it)?|leave(?:\s+it)?|not now|quiet|enough)\b",
    re.I,
)
_ORDINALS = {
    "first": 1, "1st": 1, "top": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
}
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
# "the first one" / "the first alert" — not the trailing word in "what's critical first".
_ITEM_ORDINAL = re.compile(
    r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s+(?:one|alert|case)\b"
    r"|\bthe\s+(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\b",
    re.I,
)
_DISRUPTIVE = re.compile(
    r"\b(isolate|quarantine|disable\s+(?:the\s+)?(?:account|user)|block\s+(?:the\s+)?(?:ip|address|host|domain|user)|"
    r"kill\s+(?:the\s+)?process|contain\s+(?:the\s+)?(?:host|machine|endpoint|device|it)|shut\s*down|wipe|"
    r"reset\s+(?:the\s+)?password|close\s+(?:the\s+|this\s+|that\s+|it)|mark\s+(?:it|this|that)\s+(?:as\s+)?(?:a\s+)?false\s+positive|"
    r"resolve\s+(?:the\s+|this\s+|that\s+|it))",
    re.I,
)
_UUID_FIND = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def is_bare_confirmation(text: str) -> bool:
    """A short yes/ok/please with no open/describe/list verb. 'yes, please open it' is not this."""
    return bool(_BARE_CONFIRM.match((text or "").strip()))


def has_affirmative(text: str) -> bool:
    """True when the words contain a real 'yes' (not just 'open it', which is an instruction)."""
    return any(w in _AFFIRMATIVE for w in re.findall(r"[a-z']+", text.lower()))


def is_decline(text: str) -> bool:
    return bool(_DECLINE.match((text or "").strip()))


def is_yes_open(text: str) -> bool:
    """'yes, please open it' — confirm the pending/focused case, not a bare yes and not 'open the second'."""
    return has_affirmative(text) and bool(_RE_OPEN.search(text)) and not _ordinal_refs(text)


def _ordinal_refs(text: str) -> List[int]:
    """Item picks ('the first one'). Ignores 'first' in 'what's critical first'."""
    found: List[int] = []
    for m in _ITEM_ORDINAL.finditer(text or ""):
        word = (m.group(1) or m.group(2) or "").lower()
        if word in _ORDINALS:
            found.append(_ORDINALS[word])
    low = (text or "").lower()
    for m in re.finditer(r"\b(?:number|no\.?|#)\s*(\d)\b", low):
        found.append(int(m.group(1)))
    for m in re.finditer(r"\b(one|two|three|four|five)\b(?=\s+(?:alert|one|case)\b)", low):
        found.append(_NUMBER_WORDS[m.group(1)])
    return sorted(set(found))


_REFERS_BACK = re.compile(r"\b(it|that|this|that one|this one|the alert|the case|the selected|the current)\b", re.I)


class Ambiguous(Exception):
    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


def resolve_reference(text: str, conv: Dict[str, Any], pending: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return an alert id the operator means, None if the text names none, or raise Ambiguous."""
    m = _UUID_FIND.search(text)
    if m:
        return tools.valid_uuid(m.group(0))
    refs = _ordinal_refs(text)
    listing: List[str] = conv.get("referenced_alert_ids") or []
    if refs:
        if len(refs) > 1:
            raise Ambiguous("Which one do you mean? Name a single one, for example the first.")
        if not listing:
            raise Ambiguous("I haven't listed any alerts yet. Ask me what's critical first.")
        if refs[0] > len(listing):
            raise Ambiguous(f"I only listed {len(listing)}. Which one do you want?")
        return listing[refs[0] - 1]
    if _REFERS_BACK.search(text):
        if pending and pending.get("action_type") == "open_case":
            return str((pending.get("target") or {}).get("alert_id") or "") or None
        if conv.get("selected_alert_id"):
            return conv["selected_alert_id"]
        if len(listing) == 1:
            return listing[0]
        if listing:
            raise Ambiguous("Which alert? Say the first, second, and so on.")
        raise Ambiguous("I'm not sure which alert you mean. Ask me what's critical and pick one.")
    return None


_RE_COUNT = re.compile(r"\bhow many\b|\bnumber of\b|\bcount\b", re.I)
_RE_LIST = re.compile(
    r"(what'?s|what is|what are|which|show|list|give me|any|got)\b.*\b(critical|high|urgent|open|top|latest|new)\b|"
    r"\b(critical|urgent)\s+(alerts?|cases?|ones?)\b|\bwhat'?s\s+(critical|urgent)\b|"
    r"^\s*(?:ok|okay|alright|so)[,.]?\s*(?:what'?s|what is)?\s*(critical|urgent)\b|"
    r"^\s*(critical|urgent)s?\s*[?.!]?\s*$",
    re.I,
)
_RE_OPEN = re.compile(r"\b(open|pull up|go to|take me to|navigate to|bring up|load)\b", re.I)
_RE_DESCRIBE = re.compile(
    r"\b(describe|tell me about|what about|read|summari[sz]e|walk me through|brief me on)\b",
    re.I,
)
_RE_OPEN_QUESTION = re.compile(
    r"\b(why|how come|usually|typically|should we|what do you think|recommend|in general|kind of malware)\b",
    re.I,
)
_RE_NEXT = re.compile(r"\bnext\b.*\b(alert|one|case)\b|\bnext (alert|one|case)\b", re.I)
_RE_EVIDENCE = re.compile(
    r"\b(evidence|why|explain|what happened|what do we (?:know|have)|what does the (?:record|alert) (?:show|say)|"
    r"details|more detail|what's in|what is in|show me the evidence|"
    r"what process|which process|parent process|what ran on (?:this |the )?host)\b",
    re.I,
)
_RE_CURRENT = re.compile(r"\b(what am i looking at|which alert is this|current (?:alert|case)|selected (?:alert|case))\b", re.I)
_RE_CAPS = re.compile(r"\b(what can you do|what are you able|your capabilities|help me|how can you help)\b", re.I)


# --------------------------------------------------------------------------
# composing answers from tool results
# --------------------------------------------------------------------------


def _short_alert(a: Dict[str, Any]) -> str:
    where = f" on {a['host']}" if a.get("host") else ""
    return f"{a['title']}{where} ({a['short_code']})"


def _investigation_sentence(inv: Dict[str, Any]) -> str:
    if not inv.get("available"):
        return "I can't read the investigation records right now."
    item, res = inv.get("review_item"), inv.get("latest_result")
    parts: List[str] = []
    if res:
        if res["execution_status"] == "succeeded":
            conf = f", confidence {res['confidence']:.0f}%" if res.get("confidence") is not None else ""
            verdict = str(res.get("verdict") or "no verdict")
            note = " (a model's benign view is unverified and closes nothing)" if verdict.upper().startswith("BENIGN") else ""
            parts.append(f"TIA's last investigation finished with {verdict}{conf}{note}.")
        else:
            parts.append(f"TIA's last attempt did not complete ({res['execution_status'].replace('_', ' ')}); that is not a verdict.")
    else:
        parts.append("No TIA investigation has completed on it yet.")
    if item:
        owner = f", assigned to {item['assigned_to']}" if item.get("assigned_to") else ", unassigned"
        parts.append(f"It is in the review queue ({item['assessed_priority']}, {_due_phrase(item.get('due_at'))}{owner}).")
    return " ".join(parts)


def _due_phrase(due: Any) -> str:
    """Relative and speakable: 'due in 12 minutes', not a microsecond timestamp."""
    if not due:
        return "no due time"
    try:
        when = due if isinstance(due, datetime) else datetime.fromisoformat(str(due).replace(" ", "T"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except ValueError:
        return f"due {str(due)[:16]}"
    minutes = round((when - datetime.now(timezone.utc)).total_seconds() / 60)
    if abs(minutes) < 1:
        return "due now"
    span = f"{abs(minutes)} minute{'s' if abs(minutes) != 1 else ''}" if abs(minutes) < 120 else f"{round(abs(minutes) / 60)} hours"
    return f"due in {span}" if minutes > 0 else f"overdue by {span}"


def _scope_block(scope: Scope, tenant: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {"kind": "tenant" if scope.tenant_id else "platform", "tenant": tenant}


# --------------------------------------------------------------------------
# the turn
# --------------------------------------------------------------------------

Fallback = Callable[[str, Optional[str], Scope], Dict[str, Any]]


def handle_turn(
    scope: Scope,
    *,
    text: str,
    client_turn_id: Optional[str],
    view_alert_id: Optional[str],
    request_id: str,
    tenant: Optional[Dict[str, Any]] = None,
    fallback: Optional[Fallback] = None,
    trace: Any = None,
) -> Dict[str, Any]:
    require_schema()
    text = (text or "").strip()
    if len(text) < 2:
        raise ToolError("empty", "I didn't catch that.")
    conv = get_conversation(scope, view_alert_id)
    state, stored = begin_turn(conv["id"], client_turn_id, text, request_id)
    if state == "replay" and stored is not None:
        return {**stored, "replayed": True}
    _expire_stale_commands(scope)
    notices = _unreported_expired_commands(scope)

    try:
        response = _dispatch(scope, conv, text, tenant, fallback, trace)
    except ToolError as exc:
        response = {"answer": exc.message, "spoken_answer": exc.message, "intent": "error", "tool": None, "tool_ok": False, "error": exc.code}
    response.setdefault("tool_ok", True)
    if notices:
        response["notices"] = notices
    response.update(
        {
            "conversation_id": conv["id"],
            "turn_id": client_turn_id,
            "request_id": request_id,
            "scope": _scope_block(scope, tenant),
            "replayed": False,
        }
    )
    fresh = fetch_one("SELECT selected_alert_id::text AS s FROM tia_conversations WHERE id = %s::uuid;", (conv["id"],))
    response["selected_alert_id"] = (fresh or {}).get("s")
    finish_turn(conv["id"], client_turn_id, request_id, response)
    return response


_ENGINE_NAMES = {
    "wazuh": "wazuh", "thehive": "thehive", "the hive": "thehive", "shuffle": "shuffle", "suricata": "suricata", "zeek": "zeek",
    "misp": "misp", "greenbone": "greenbone", "velociraptor": "velociraptor", "secure edge": "secure_edge",
    "soc agent": "soc_agent", "control plane": "control_plane", "appliances": "appliances",
}
_RE_HEALTH = re.compile(
    r"\b(engines?|infrastructure|infra|stack|services|systems?|backend|"
    r"wazuh|the ?hive|shuffle|suricata|zeek|misp|greenbone|velociraptor|secure edge|soc agent|control plane|appliances?)\b"
    r".{0,60}\b(health|healthy|status|up|down|online|offline|running|working|degraded|reachable|ok|okay|fine|alive|broken)\b"
    r"|\b(health|status)\b.{0,30}\b(of )?(the )?(engines?|infrastructure|infra|stack|platform)\b",
    re.I,
)
_RE_INVESTIGATE = re.compile(
    r"\b(investigate|look deeper|dig (?:deeper|into)|start (?:a )?(?:deep )?investigation|run (?:a )?(?:deep )?investigation)\b",
    re.I,
)
_RE_INV_STATUS = re.compile(r"\b(investigation status|how's the investigation|has the investigation (?:finished|completed|run))\b", re.I)
_RE_BEHAVIOUR_RESEARCH = re.compile(
    r"\b(look ?up this (?:alert|behaviour|behavior|binary)|research this (?:alert|behaviour|behavior)|lolbas|living[- ]off[- ]the[- ]land)\b",
    re.I,
)


_RE_CVE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
_RE_TECH = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
_RE_RESEARCH = re.compile(r"\b(look ?up|research|what is|what's|tell me about|explain|find)\b", re.I)
_RE_CRITICALITY = re.compile(
    r"\bwhy\b.{0,50}\bcritical\b|"
    r"\bcould this be\b.{0,40}\b(normal|benign|authori[sz]ed|expected|legit|false positive)\b|"
    r"\bis this\b.{0,30}\b(really |actually )?(malicious|an incident|a true positive|critical)\b|"
    r"\brule label\b",
    re.I,
)
_RE_INGEST = re.compile(
    r"\bevents?\b.{0,40}\b(arriv|coming|ingest|showing up|flowing|landing)\b|"
    r"\b(actually|still)\s+(ingesting|receiving|seeing)\b|"
    r"\b(telemetry|ingest(ion)?|fresh(ness)?|stale events?)\b|"
    r"\breachable\b.{0,40}\b(events?|arriv|ingest)",
    re.I,
)
_RE_VM = re.compile(
    r"\bwhich vm\b|\bwhat vm\b|\bon which vm\b|\bwhich (machine|server) runs\b|"
    r"\bwhat (vm|machine|server)\s+runs\b|"
    r"\bwhere does\b.{0,40}\brun\b|"
    r"\bwhat depends (on )?(it|that|this)\b|"
    r"\bdependenc",
    re.I,
)
_RE_INVENTORY = re.compile(
    r"\b(inventory|topology|what (do we|have we) deploy|which (components|engines) (do we|are)|"
    r"platform (map|layout)|vm layout)\b",
    re.I,
)
_RE_DELAY = re.compile(
    r"\bwhy\b.{0,40}\b(delay|delayed|taking (so )?long|stuck|queued|waiting)\b|"
    r"\b(investigation|job|worker).{0,30}\b(slow|stuck|delay|overdue|not (running|finished))\b",
    re.I,
)
_RE_KNOWN = re.compile(
    r"\bwhat do we know\b|\bwhat remains (unverified|unknown|unchecked)\b|"
    r"\bknown vs\b|\bverified vs(?:ersus)?\b|\bwhat'?s verified\b|"
    r"\bwhat (is|isn't|is not) (verified|confirmed|checked)\b",
    re.I,
)
_RE_CUSTOMERS = re.compile(
    r"\b(which|how many|list|show)\b.{0,30}\b(customers?|tenants?)\b|"
    r"\bcustomers?\s+(in scope|we have|are onboarded)\b",
    re.I,
)
_RE_PORTALS = re.compile(
    r"\b(admin portal|customer portal|soc console|port 3000|port 3001|:3000|:3001|:3443)\b",
    re.I,
)
_RE_RETURN_CASE = re.compile(
    r"\bback to (the )?(alert|case|it|that)\b|"
    r"\b(the |that )?(open|current|selected|pinned) (alert|case)\b|"
    r"\breturn(ing)? to (the )?(alert|case)\b",
    re.I,
)
_RE_EXPAND = re.compile(r"\b(tell me more|go deeper|expand|more detail|say more|full answer)\b", re.I)
_RE_CHITCHAT = re.compile(
    r"^\s*(thanks|thank you|got it|cool|okay thanks|cheers|good (morning|afternoon|evening|night)|"
    r"how are you|you good|nice one|understood)\b",
    re.I,
)
_RE_QUESTION = re.compile(
    r"\?|\b(why|how|which|where|who|when|could|would|should|is|are|does|do|did|can|what)\b",
    re.I,
)


def _reply(answer: str, spoken: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    return {"answer": answer, "spoken_answer": spoken or answer, "provider": "tia-tools", **extra}


def _from_knowledge(report: Dict[str, Any], *, intent: str, tool: str) -> Dict[str, Any]:
    extra = {k: report.get(k) for k in ("observed", "documented", "hypotheses", "unknowns", "conflicts", "checked_at", "component", "layers") if report.get(k) is not None}
    extra["intent"] = intent
    extra["tool"] = tool
    extra["tool_ok"] = True
    return _reply(report["answer"], report.get("spoken_answer"), **extra)


def _case_target(conv: Dict[str, Any], text: str, pending: Optional[Dict[str, Any]]) -> Optional[str]:
    try:
        ref = resolve_reference(text, conv, pending)
    except Ambiguous:
        ref = None
    return ref or conv.get("selected_alert_id") or conv.get("pinned_alert_id") or conv.get("on_screen_alert_id")


def _needs_case(conv: Dict[str, Any]) -> Dict[str, Any]:
    return _reply(
        "Which alert? I can use the open case, the first one from the list, or a title.",
        "Which alert do you mean?",
        intent="needs_case", tool=None, tool_ok=False, clarification=True,
    )


def _expand_last(conv_id: str) -> Dict[str, Any]:
    row = fetch_one(
        "SELECT response FROM tia_conversation_turns WHERE conversation_id = %s::uuid AND role = 'tia' "
        "ORDER BY turn_no DESC LIMIT 1;",
        (conv_id,),
    )
    resp = (row or {}).get("response") or {}
    if isinstance(resp, str):
        resp = json.loads(resp)
    answer = str((resp or {}).get("answer") or "").strip()
    if not answer:
        return _reply("I don't have a previous answer to expand. Ask the question again.", intent="expand", tool=None, tool_ok=False)
    spoken = str(resp.get("spoken_answer") or "")
    return _reply(answer, spoken or answer[:400], intent="expand", tool=resp.get("tool"), tool_ok=True)


def _knowledge_dispatch(scope: Scope, conv: Dict[str, Any], text: str, pending: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Natural ops questions answered from authorised tools. None = not this family."""
    from app.services import tia_knowledge as kn

    low = text.lower()
    # Host/process evidence stays on the case record; do not steal it as a VM lookup.
    if _RE_EVIDENCE.search(text) and not (_RE_CRITICALITY.search(text) or _RE_KNOWN.search(text) or _RE_DELAY.search(text)):
        return None
    if _RE_CHITCHAT.match(text):
        return _reply("Anytime. I'm still on the case we were looking at." if conv.get("selected_alert_id") or conv.get("pinned_alert_id") else "Anytime. Ask what's critical, or name a component.", intent="chitchat", tool=None)
    if _RE_EXPAND.search(text):
        return _expand_last(conv["id"])
    if _RE_RETURN_CASE.search(text) and not _RE_CRITICALITY.search(text):
        target = conv.get("pinned_alert_id") or conv.get("selected_alert_id") or conv.get("on_screen_alert_id")
        if not target:
            return _needs_case(conv)
        _set_selected(conv["id"], target)
        conv["selected_alert_id"] = target
        _pin_alert(conv["id"], target, topic="case")
        return _describe(scope, conv, target, None, intent="return_case", offer_open=False)
    if _RE_CRITICALITY.search(text):
        target = _case_target(conv, text, pending)
        if not target:
            return _needs_case(conv)
        _pin_alert(conv["id"], target, topic="case")
        return _from_knowledge(tools.assess_criticality(scope, target), intent="criticality", tool="assess_criticality")
    if _RE_KNOWN.search(text):
        target = _case_target(conv, text, pending)
        if not target:
            return _needs_case(conv)
        return _from_knowledge(tools.known_unknowns(scope, target), intent="known_unknowns", tool="known_unknowns")
    if _RE_DELAY.search(text):
        target = _case_target(conv, text, pending)
        if not target:
            return _needs_case(conv)
        return _from_knowledge(tools.investigation_delay(scope, target), intent="investigation_delay", tool="investigation_delay")
    if _RE_INGEST.search(text):
        engine = next((eid for name, eid in _ENGINE_NAMES.items() if name in low), "wazuh")
        _pin_alert(conv["id"], conv.get("selected_alert_id") or conv.get("pinned_alert_id"), topic=f"engine:{engine}")
        return _from_knowledge(tools.ingest_status(scope, engine), intent="ingest_status", tool="ingest_status")
    if _RE_CUSTOMERS.search(text):
        _pin_alert(conv["id"], conv.get("selected_alert_id") or conv.get("pinned_alert_id"), topic="customers")
        return _from_knowledge(tools.customers_overview(scope), intent="customers", tool="customers_overview")
    if _RE_PORTALS.search(text) and not _RE_VM.search(text):
        _pin_alert(conv["id"], conv.get("selected_alert_id") or conv.get("pinned_alert_id"), topic="portals")
        return _from_knowledge(tools.portal_status(scope), intent="portals", tool="portal_status")
    if _RE_INVENTORY.search(text):
        _pin_alert(conv["id"], conv.get("selected_alert_id") or conv.get("pinned_alert_id"), topic="inventory")
        return _from_knowledge(tools.platform_inventory(scope), intent="inventory", tool="platform_inventory")
    if _RE_VM.search(text) or (kn.resolve_component(text) and re.search(r"\b(run|vm|host|where|depend)\b", low)):
        cid = kn.resolve_component(text)
        topic = str((conv.get("last_listing") or {}).get("topic") or "")
        # Current topic wins over the open case's source engine when the operator just switched to a component.
        if not cid and topic.startswith("component:"):
            cid = topic.split(":", 1)[1]
        if not cid and ("this" in low or "it" in low):
            cid = kn.resolve_component(
                text,
                source_tool=(tools.get_alert_row(scope, conv.get("selected_alert_id") or conv.get("pinned_alert_id")) or {}).get("source_tool"),
            )
        if not cid:
            return _reply(
                "Which component? Wazuh, TheHive, Shuffle, Suricata, the control plane, a portal, or another catalogue name.",
                "Which component should I look up?",
                intent="component_ambiguous", tool="component_lookup", tool_ok=False, clarification=True,
            )
        _pin_alert(conv["id"], conv.get("selected_alert_id") or conv.get("pinned_alert_id"), topic=f"component:{cid}")
        try:
            return _from_knowledge(tools.component_lookup(scope, cid), intent="component", tool="component_lookup")
        except ToolError as err:
            return _reply(err.message, intent="component", tool="component_lookup", tool_ok=False, error=err.code)
    return None


def _looks_like_question(text: str) -> bool:
    if _RE_QUESTION.search(text) and len(text) >= 8:
        return True
    return len(text.split()) >= 5


def _grounded_fallback(
    scope: Scope,
    conv: Dict[str, Any],
    text: str,
    fallback: Optional[Fallback],
) -> Dict[str, Any]:
    """Model only after tools gathered evidence. Never a generic dashboard snapshot."""
    evidence: Dict[str, Any] = {
        "selected_alert_id": conv.get("selected_alert_id"),
        "pinned_alert_id": conv.get("pinned_alert_id"),
        "topic": (conv.get("last_listing") or {}).get("topic"),
        "scope": "tenant" if scope.tenant_id else "platform",
    }
    target = conv.get("selected_alert_id") or conv.get("pinned_alert_id")
    if target:
        try:
            evidence["case"] = tools.known_unknowns(scope, target)
        except ToolError:
            evidence["case"] = None
    if fallback is None:
        return _reply(
            "I don't have a model for that, and I won't guess. I can list alerts, open a case, check engine ingest, look up which VM runs a component, or queue an investigation.",
            "I don't have a model answer for that. Ask me something I can read from the platform.",
            intent="model_unavailable", tool=None, tool_ok=False, error="model_unavailable",
        )
    try:
        try:
            out = fallback(text, conv.get("selected_alert_id"), scope, evidence)  # type: ignore[misc]
        except TypeError:
            out = fallback(text, conv.get("selected_alert_id"), scope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TIA model fallback failed: %s", type(exc).__name__)
        if evidence.get("case"):
            report = evidence["case"]
            return _reply(
                "The model did not answer. What I already have from the record:\n" + str(report.get("answer") or ""),
                "The model did not answer. I can only speak to the stored record.",
                intent="model_unavailable", tool="known_unknowns", tool_ok=True, error="model_unavailable",
            )
        return _reply(
            "I couldn't get a model answer for that just now. Anything I can read directly (counts, lists, an alert's record, engine ingest, inventory) still works.",
            intent="model_unavailable", tool=None, tool_ok=False, error="model_unavailable",
        )
    if out.get("provider") == "tia-live":
        return _reply(
            "I won't recap the whole dashboard for that. Ask about the open case, an engine, a VM, or a customer.",
            "That isn't a dashboard recap. What do you want to know?",
            intent="unrecognised", tool=None, tool_ok=False,
        )
    out.setdefault("intent", "model_fallback")
    out.setdefault("tool", None)
    return out


def _is_list_request(text: str) -> bool:
    return bool(_RE_LIST.search(text))


def _confirm_nothing_or_expired(conv: Dict[str, Any]) -> Dict[str, Any]:
    stale = _recently_expired_pending(conv["id"])
    if stale:
        return _reply(
            "That offer expired before you answered, so I did nothing. Tell me which alert to open.",
            intent="confirm_expired", tool=None, tool_ok=False,
        )
    return _reply(
        "There's nothing waiting on a yes. Tell me what you'd like, for example what's critical.",
        intent="confirm_nothing", tool=None, tool_ok=False,
    )


def _dispatch(scope: Scope, conv: Dict[str, Any], text: str, tenant: Optional[Dict[str, Any]], fallback: Optional[Fallback], trace: Any) -> Dict[str, Any]:
    pending = _live_pending(conv["id"])

    # 1. Answers to something TIA asked. Bare "yes" needs a pending action.
    # "yes, please open it" confirms that pending offer (or the focused case) — it is not a dashboard recap.
    if pending and (is_bare_confirmation(text) or is_decline(text) or is_yes_open(text)):
        return _answer_pending(scope, conv, pending, confirm=not is_decline(text))
    if not pending and is_bare_confirmation(text) and has_affirmative(text):
        return _confirm_nothing_or_expired(conv)
    if not pending and is_yes_open(text):
        stale = _recently_expired_pending(conv["id"])
        if stale:
            return _confirm_nothing_or_expired(conv)
        listing = conv.get("referenced_alert_ids") or []
        # After a multi-item list, "open it" is ambiguous even if a page is already on screen.
        if len(listing) > 1 and not _ordinal_refs(text):
            return _reply(
                "Which alert should I open? Say the first, second, or its title.",
                intent="open_ambiguous", tool="open_case", tool_ok=False, clarification=True,
            )
        try:
            alert_id = resolve_reference(text, conv, pending)
        except Ambiguous as amb:
            return _reply(amb.question, intent="open_ambiguous", tool="open_case", tool_ok=False, clarification=True)
        target = alert_id or conv.get("selected_alert_id")
        if target:
            return _open(scope, conv, target, None)
        return _confirm_nothing_or_expired(conv)
    if not pending and is_decline(text):
        return _reply("Okay, I've stopped. Say what's critical when you want to continue.", "Okay, I've stopped.", intent="cancelled", tool=None)

    # 2. Disruptive or state-changing requests are never executed from conversation.
    if _DISRUPTIVE.search(text):
        msg = (
            "I won't do that from chat or voice. Isolating, disabling, blocking, containing, closing or resolving needs a human "
            "approval in Needs You, tied to the exact target. I can open the alert so you can approve it there."
        )
        return _reply(msg, "I can't do that by voice. It needs your approval in Needs You.", intent="disruptive_refused", tool=None, tool_ok=False)

    if _RE_CAPS.search(text):
        names = ", ".join(t["name"].replace("_", " ") for t in tools.capabilities())
        return _reply(
            f"Right now I can: {names}. Ask me to investigate an open alert and I will queue a deep look without waiting for the model. "
            "Isolating, disabling, blocking or closing still needs your approval in Needs You.",
            intent="capabilities", tool=None,
        )

    # 3. Navigation: explicit "open ..." needs no extra confirmation.
    if _RE_OPEN.search(text) and not _RE_COUNT.search(text):
        try:
            alert_id = resolve_reference(text, conv, pending)
        except Ambiguous as amb:
            return _reply(amb.question, intent="open_ambiguous", tool="open_case", tool_ok=False, clarification=True)
        if alert_id:
            return _open(scope, conv, alert_id, None)

    if _RE_NEXT.search(text):
        nxt = tools.next_alert(scope, conv["referenced_alert_ids"], conv.get("selected_alert_id"))
        if not nxt:
            return _reply("There's no next alert in the list I gave you. Ask me what's critical for a fresh list.", intent="next", tool="next_alert", tool_ok=False)
        return _describe(scope, conv, nxt, tenant, intent="next")

    if _RE_CURRENT.search(text):
        if not conv.get("selected_alert_id"):
            return _reply("No alert is selected. Pick one from the list or open one.", intent="current", tool=None, tool_ok=False)
        return _describe(scope, conv, conv["selected_alert_id"], tenant, intent="current", offer_open=False)

    # 3a. Public reference lookup (cited, off unless configured). Only the identifier leaves the platform.
    cve, tech = _RE_CVE.search(text), _RE_TECH.search(text)
    if (cve or tech) and _RE_RESEARCH.search(text):
        return _research(scope, "cve" if cve else "mitre_technique", (cve or tech).group(0))

    # 3b. Natural ops questions (inventory, ingest vs reachability, criticality, delay).
    # Ingest questions must win over generic "reachable" health matching.
    kn = _knowledge_dispatch(scope, conv, text, pending)
    if kn:
        return kn

    # 3c. Engine and infrastructure health: real adapters, never a model guess.
    if _RE_HEALTH.search(text) and not _RE_COUNT.search(text):
        return _engine_health(scope, text)

    # 4. Counts and listings (real data, scoped).
    # "OK, what's critical first?" is a list request, not "the first one" of an earlier list.
    picking_item = bool(_ordinal_refs(text) or _UUID_FIND.search(text))
    if _RE_COUNT.search(text) or (
        _is_list_request(text)
        and not picking_item
        and not _RE_DESCRIBE.search(text)
        and not _RE_OPEN.search(text)
        and not _RE_INVESTIGATE.search(text)
    ):
        return _count_and_list(scope, conv, tenant)
    if _is_list_request(text) and not picking_item:
        return _count_and_list(scope, conv, tenant)

    # 5. Describing or explaining one alert.
    try:
        ref = resolve_reference(text, conv, pending)
    except Ambiguous as amb:
        if _RE_INVESTIGATE.search(text):
            return _reply(amb.question, intent="investigate_ambiguous", tool="start_investigation", tool_ok=False, clarification=True)
        if _RE_DESCRIBE.search(text) or _RE_EVIDENCE.search(text):
            return _reply(amb.question, intent="ambiguous", tool=None, tool_ok=False, clarification=True)
        ref = None
    if ref and _RE_EVIDENCE.search(text) and not _RE_DESCRIBE.search(text.replace("what's in", "")):
        return _evidence(scope, conv, ref)
    # Investigate must win over "the third one" describe: "investigate the third one" is a job request.
    if _RE_INVESTIGATE.search(text) and not _RE_INV_STATUS.search(text):
        target = ref or conv.get("selected_alert_id")
        if not target:
            return _reply("Which alert should I investigate? Tell me the first, second, or open one.", intent="investigate_needs_target", tool="start_investigation", tool_ok=False)
        return _start_investigation(scope, conv, target)
    if ref and (_RE_DESCRIBE.search(text) or _ordinal_refs(text)):
        return _describe(scope, conv, ref, tenant, intent="describe", offer_open=ref != conv.get("on_screen_alert_id"))
    if conv.get("selected_alert_id") and _RE_EVIDENCE.search(text):
        return _evidence(scope, conv, conv["selected_alert_id"])

    if _RE_INV_STATUS.search(text):
        target = conv.get("selected_alert_id")
        if not target:
            return _reply("No alert is selected, so I have no investigation to report on.", intent="investigation_status", tool="investigation_status", tool_ok=False)
        return _investigation_status(scope, conv, target)

    # 5b. Sanitised behavioural research (public binary names only) — never free text about the customer.
    if _RE_BEHAVIOUR_RESEARCH.search(text):
        target = conv.get("selected_alert_id")
        if not target:
            return _reply("Pick an alert first, then I can look up the public binaries named in its record.", intent="research", tool="research_lookup", tool_ok=False)
        return _behavioural_research(scope, target)

    # 6. Natural language: grounded model or a clear miss. Never a dashboard recap.
    if _looks_like_question(text) or _RE_OPEN_QUESTION.search(text):
        return _grounded_fallback(scope, conv, text, fallback)
    return _reply(
        "I didn't catch a command I can run. Ask what's critical, describe the first one, open it, check an engine, or name a VM.",
        "I didn't catch that. Ask what's critical, or describe an alert.",
        intent="unrecognised", tool=None, tool_ok=False,
    )


def _start_investigation(scope: Scope, conv: Dict[str, Any], alert_id: str) -> Dict[str, Any]:
    try:
        out = tools.start_investigation(scope, alert_id)
    except ToolError as err:
        return _reply(err.message, intent="start_investigation", tool="start_investigation", tool_ok=False, error=err.code)
    already = "already queued" if not out["created"] else "queued"
    msg = (
        f"I've {already} a deep investigation for {out['title']} ({out['short_code']}). "
        f"Job {out['job_id'][:8]}. I'll keep answering other questions; ask for investigation status when you want an update. "
        "I have not waited for the model."
    )
    spoken = f"Investigation {already} for {out['short_code']}. I haven't waited for it."
    return _reply(msg, spoken, intent="start_investigation", tool="start_investigation", tool_ok=True, job=out)


def _investigation_status(scope: Scope, conv: Dict[str, Any], alert_id: str) -> Dict[str, Any]:
    try:
        out = tools.investigation_status(scope, alert_id)
    except ToolError as err:
        return _reply(err.message, intent="investigation_status", tool="investigation_status", tool_ok=False, error=err.code)
    job = out.get("job")
    if not job:
        return _reply("No investigation job is queued for this alert.", intent="investigation_status", tool="investigation_status", tool_ok=True, job=None)
    msg = f"The investigation job is {job['state']} (attempt {job['attempts']} of {job['max_attempts']}). {_investigation_sentence(out['investigation'])}"
    return _reply(msg, intent="investigation_status", tool="investigation_status", tool_ok=True, job=job)


def _behavioural_research(scope: Scope, alert_id: str) -> Dict[str, Any]:
    try:
        out = tools.research_behaviour(scope, alert_id)
    except ToolError as err:
        if err.code == "tenant_not_authorised":
            msg = "This customer has not authorised behavioural research, so I will not send anything derived from their alert to an external site."
        elif err.code == "nothing_sendable":
            msg = "The alert names no publicly known binary I am allowed to look up, so I sent nothing."
        else:
            msg = f"I couldn't look that up: {err.message.lower()}."
        return _reply(msg, intent="research", tool="research_lookup", tool_ok=False, error=err.code)
    lines = [f"Public-binary lookup via {out['provider']} (query class {out['query_class']}). Sent only: {', '.join(out['sent'])}."]
    if out.get("withheld_names"):
        lines.append(f"{out['withheld_names']} customer-specific name(s) were withheld.")
    for fnd in out.get("findings") or []:
        if fnd.get("found"):
            lines.append(f"- {fnd['binary']} from {fnd['source_url']} (fetched {fnd['fetched_at']}): {fnd['applies']}")
        else:
            lines.append(f"- {fnd['binary']}: no page found. Absence is not evidence of safety.")
    lines.append("This is a public technique reference. It does not prove the technique occurred in the customer environment.")
    return _reply("\n".join(lines), "I looked up the public binaries named in the record. That is a reference, not proof it happened here.", intent="research", tool="research_lookup", tool_ok=True, citation=out)


def _research(scope: Scope, kind: str, value: str) -> Dict[str, Any]:
    try:
        out = tools.research_lookup(scope, kind=kind, value=value)
    except tools.ToolError as err:
        if err.code == "research_disabled":
            msg = "Reference lookups are switched off on this platform because no approved reference sites are configured, so I won't guess what that is."
        else:
            msg = f"I couldn't look that up: {err.message.lower()}."
        return _reply(msg, intent="research", tool="research_lookup", tool_ok=False, error=err.code)
    if not out["ok"]:
        return _reply(f"The reference site answered with status {out['status']}, so I have nothing to cite for {value}.", intent="research", tool="research_lookup", tool_ok=False)
    excerpt = out["excerpt"][:300].rsplit(" ", 1)[0] + ("..." if len(out["excerpt"]) > 300 else "")
    msg = f"From {out['source_url']} (external reference text, fetched {out['fetched_at']}): {excerpt}"
    return _reply(msg, f"I found a reference for {value}. The source is {out['source_url'].split('/')[2]}.", intent="research", tool="research_lookup", tool_ok=True, citation={"url": out["source_url"], "fetched_at": out["fetched_at"], "trust": out["trust"]})


def _engine_health(scope: Scope, text: str) -> Dict[str, Any]:
    from app.services import tia_engine_health as eh

    low = text.lower()
    focus = next((eid for name, eid in _ENGINE_NAMES.items() if name in low), None)
    try:
        report = tools.engine_health(scope, engine=focus, force=bool(re.search(r"\b(right now|just now|recheck|re-check|again|fresh)\b", low)))
    except tools.ToolError as err:
        return _reply(err.message, intent="engine_health", tool="engine_health", tool_ok=False, error=err.code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("engine health failed: %s", type(exc).__name__)
        return _reply("I couldn't run the health checks just now, so I can't say whether the engines are up.", intent="engine_health", tool="engine_health", tool_ok=False, error="health_unavailable")
    said = eh.summarize(report, focus=focus)
    return _reply(said["answer"], said["spoken"], intent="engine_health", tool="engine_health", tool_ok=True, health={"counts": report["counts"], "checked_at": report["checked_at"], "detail_level": report.get("detail_level", "full")})


def _answer_pending(scope: Scope, conv: Dict[str, Any], pending: Dict[str, Any], *, confirm: bool) -> Dict[str, Any]:
    # Defence in depth: the row was found by conversation, and must still match this exact scope.
    if (
        pending["session_id"] != scope.session_id
        or pending["operator_email"] != scope.operator_email
        or (pending.get("tenant_id") or None) != (scope.tenant_id or None)
    ):
        _resolve_pending(pending["id"], "refused", "scope_mismatch")
        return _reply("That offer belonged to a different session or customer, so I dropped it.", intent="confirm_scope_mismatch", tool=None, tool_ok=False)
    if not confirm:
        _resolve_pending(pending["id"], "cancelled", "operator_declined")
        return _reply("Okay, I won't open it.", intent="pending_cancelled", tool=None)
    if pending["risk_class"] == "disruptive":
        _resolve_pending(pending["id"], "refused", "disruptive_needs_approval")
        return _reply("That needs a human approval in Needs You; a yes in chat isn't approval.", intent="pending_refused", tool=None, tool_ok=False)
    if pending["action_type"] != "open_case":
        _resolve_pending(pending["id"], "refused", "unsupported_action")
        return _reply("I can't carry that out from here.", intent="pending_refused", tool=None, tool_ok=False)
    alert_id = str((pending["target"] or {}).get("alert_id") or "")
    if not _resolve_pending(pending["id"], "executed", "operator_confirmed"):
        return _reply("That was already handled.", intent="pending_duplicate", tool=None)
    return _open(scope, conv, alert_id, pending["id"])


def _open(scope: Scope, conv: Dict[str, Any], alert_id: str, pending_id: Optional[str]) -> Dict[str, Any]:
    try:
        target = tools.open_case_target(scope, alert_id)
    except ToolError as exc:
        if pending_id is None:
            _cancel_live_pending(conv["id"], "open_failed")
        return _reply(exc.message, intent="open_failed", tool="open_case", tool_ok=False, error=exc.code)
    if pending_id is None:  # an explicit instruction replaces any earlier offer
        _cancel_live_pending(conv["id"], "superseded_by_explicit_open")
    cmd = _issue_open_case(conv["id"], scope, target, pending_id)
    msg = f"Asking your dashboard to open {target['title']} ({target['short_code']}). I'll confirm once it has loaded."
    return _reply(msg, "Opening it now.", intent="open_case", tool="open_case", ui_command=cmd, verification="pending")


def _describe(scope: Scope, conv: Dict[str, Any], alert_id: str, tenant: Optional[Dict[str, Any]], *, intent: str, offer_open: bool = True) -> Dict[str, Any]:
    d = tools.describe_alert(scope, alert_id)
    a, inv = d["alert"], d["investigation"]
    when = f", seen {a['event_time']} UTC" if a.get("event_time") else ""
    body = f"This is a {a['severity']} alert: {_short_alert(a)}{when}. Status: {a['status']}. {_investigation_sentence(inv)}"
    spoken = f"This is a {a['severity']} alert, {a['title']}, for {a['short_code']}. {_investigation_sentence(inv)}"
    extra: Dict[str, Any] = {"intent": intent, "tool": "describe_alert", "alert": {k: a[k] for k in ("id", "title", "severity", "status", "short_code", "host")}}
    _set_selected(conv["id"], a["id"])
    conv["selected_alert_id"] = a["id"]
    _pin_alert(conv["id"], a["id"], topic="case")
    conv["pinned_alert_id"] = a["id"]
    if offer_open:
        pend = _create_pending(
            conv["id"], scope, "open_case",
            {"alert_id": a["id"], "title": a["title"], "short_code": a["short_code"]},
            f"Open {a['title']} ({a['short_code']})", "navigation",
        )
        extra["pending_action"] = pend
        body += " Shall I open it?"
        spoken += " Shall I open it?"
    return _reply(body, spoken, **extra)


def _evidence(scope: Scope, conv: Dict[str, Any], alert_id: str) -> Dict[str, Any]:
    e = tools.explain_evidence(scope, alert_id)
    a = e["alert"]
    lines = [f"What the stored record shows for {a['title']} ({a['short_code']}):"]
    if e["description"]:
        lines.append(f"Detection: {e['description']}")
    lines += [f"- {p['field']}: {p['value']}" for p in e["present"]] or ["- no structured evidence fields are populated"]
    if e["missing"]:
        lines.append("Not in the record: " + ", ".join(e["missing"]) + ".")
    ai = e["prior_ai_assessment"]
    if ai.get("verdict"):
        lines.append(f"An earlier automated assessment said {ai['verdict']}; that is a recommendation, not a finding.")
    inv = e["investigation"]
    lines.append(_investigation_sentence(inv))
    checked = _checked_sentences(inv.get("checked"))
    if checked["did"]:
        lines.append("What I checked: " + "; ".join(checked["did"]) + ".")
    if checked["gaps"]:
        lines.append("What I could not check: " + "; ".join(checked["gaps"]) + ".")
    if not inv.get("checked"):
        lines.append("No investigation evidence was recorded for this alert, so I can only speak to the stored record.")
    view = inv.get("model_view") or {}
    if view.get("summary"):
        lines.append(f"The investigation's own view, unverified: {view['summary']}")
    lines.append("I haven't established a cause. Ask me to investigate if you want a deeper look.")
    trigger = f"It triggered on {e['description'][:160]}" if e["description"] else f"It triggered as {a['title']}"
    fact = _spoken_fact(e["present"])
    spoken_checked = (" I checked " + ", ".join(checked["did_short"]) + ".") if checked["did_short"] else " No investigation evidence is recorded yet."
    spoken_gap = (" I couldn't check " + ", ".join(checked["gap_short"]) + ".") if checked["gap_short"] else ""
    spoken_missing = f" {len(e['missing'])} details, such as {e['missing'][0]}, are not in the record." if e["missing"] else ""
    spoken = f"{trigger}.{fact}{spoken_checked}{spoken_gap}{spoken_missing} " + _investigation_sentence(inv) + " I haven't established a cause."
    return _reply("\n".join(lines), spoken, intent="evidence", tool="explain_evidence", alert={"id": a["id"], "title": a["title"]}, checked=inv.get("checked"))


def _spoken_fact(present: List[Dict[str, Any]]) -> str:
    """One recorded fact, phrased to be heard rather than read. Command lines are never read out."""
    by = {p["field"]: str(p["value"]) for p in present}
    exe = lambda v: re.split(r"[\\/]", v.strip().strip('"').split(" ")[0])[-1]  # noqa: E731
    parent, cmd = by.get("parent process"), by.get("parent command line")
    if parent and cmd:
        encoded = " with an encoded command" if re.search(r"\s-(?:e|en|enc|encodedcommand)\s", f" {cmd} ", re.I) else ""
        return f" The record shows {exe(parent)} started {exe(cmd)}{encoded}."
    if parent:
        return f" The record shows the parent process {exe(parent)}."
    return ""


_SECTION_LABEL = {
    "raw_event": "the raw event", "correlations": "related alerts", "asset": "the asset record",
    "identity": "the user's activity", "runbooks": "runbooks", "prior_cases": "reviewed past cases", "research": "external research",
}


def _checked_sentences(checked: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {"did": [], "gaps": [], "did_short": [], "gap_short": []}
    for name, s in ((checked or {}).get("sections") or {}).items():
        label = _SECTION_LABEL.get(name, name.replace("_", " "))
        if s["status"] == "present":
            out["did"].append(f"{label} ({s['items']} item(s))")
            out["did_short"].append(label)
        elif s["status"] == "empty":
            out["did"].append(f"{label}: nothing found" + (f" ({s['note']})" if s.get("note") else ""))
            out["did_short"].append(f"{label}, nothing found")
        elif s["status"] == "unavailable":
            out["gaps"].append(f"{label}: the source was unavailable, so its silence proves nothing")
            out["gap_short"].append(label)
        else:
            out["gaps"].append(f"{label}: no source" + (f" ({s['note']})" if s.get("note") else ""))
            out["gap_short"].append(label)
    return out


def _count_and_list(scope: Scope, conv: Dict[str, Any], tenant: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    counts = tools.count_alerts(scope)
    rows = remember_listing(scope)
    conv["referenced_alert_ids"] = [r["id"] for r in rows]
    conv["selected_alert_id"] = None
    place = f"for {tenant['name']}" if (scope.tenant_id and tenant) else "across all customers"
    by = counts["by_severity"]
    extra_bits = [f"{by[s]} {s}" for s in ("medium", "low") if by.get(s)]
    head = f"{place.capitalize()}: {counts['critical']} critical and {counts['high']} high open alerts" + (f", plus {', '.join(extra_bits)}" if extra_bits else "") + "."
    if not rows:
        return _reply(head + " Nothing critical or high is open.", intent="list", tool="count_alerts", counts=counts, alerts=[])
    lines = [head, "Most urgent:"] + [f"{i}. [{r['severity']}] {_short_alert(r)}" for i, r in enumerate(rows, 1)]
    first = rows[0]
    spoken = f"{place.capitalize()}, {counts['critical']} critical and {counts['high']} high are open. The most urgent is {first['title']} for {first['short_code']}. Ask me about the first, or any other."
    return _reply("\n".join(lines), spoken, intent="list", tool="list_alerts", counts=counts, alerts=rows)
