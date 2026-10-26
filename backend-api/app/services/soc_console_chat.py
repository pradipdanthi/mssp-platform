"""SOC Console chat — Tia (Cursor agent) with briefing facts + ticket actions."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.services.ai_admin_chat import _gather_context, _redact, _resolve_tenant
from app.services.soc_agent_client import soc_agent_enabled, soc_agent_token, soc_agent_url
from app.services.soc_console_approvals import enqueue_approval
from app.services.soc_console_operator import gather_operator_snapshot, render_wake_briefing
from app.services.soc_console_platform import gather_platform_visibility
from app.services.soc_console_tia import (
    TIA_NAME,
    TIA_SYSTEM,
    apply_tia_actions,
    gather_tia_briefing,
    parse_tia_blocks,
)

logger = logging.getLogger(__name__)


def soc_console_chat_enabled() -> bool:
    return soc_agent_enabled() and bool(soc_agent_token())


def _timeout() -> float:
    try:
        val = float(os.getenv("SOC_AGENT_TIMEOUT_SECONDS") or "120")
    except ValueError:
        val = 120.0
    return max(15.0, min(val, 300.0))


def _infer_hours_away(question: str) -> int:
    q = (question or "").lower()
    m = re.search(r"(\d+)\s*(hour|hr|hrs|h)\b", q)
    if m:
        return max(1, min(int(m.group(1)), 168))
    if "yesterday" in q:
        return 36
    if "weekend" in q:
        return 72
    if "away" in q or "while i was" in q or "missed" in q:
        return 24
    return 24


def _json_under_budget(obj: Any, budget: int) -> Dict[str, Any]:
    """Shrink a context dict until json.dumps fits budget — never mid-string truncate."""
    if not isinstance(obj, dict):
        return {"value": _redact(str(obj), max(200, budget // 4))}
    current: Dict[str, Any] = dict(obj)
    raw = json.dumps(current, default=str)
    if len(raw) <= budget:
        return current

    # Drop heavy nested blobs first (keep operator answers usable).
    drop_order = (
        "briefing",
        "tenant_context",
        "operator_snapshot",
        "platform_visibility",
    )
    for key in drop_order:
        if key not in current:
            continue
        val = current.get(key)
        if isinstance(val, dict):
            # Keep only shallow scalars / short lists under nested keys.
            slim_nested: Dict[str, Any] = {}
            for nk, nv in val.items():
                if nk in ("topic", "counts", "window_hours", "priority", "needs_attention", "generated_at"):
                    slim_nested[nk] = nv
                elif isinstance(nv, list):
                    slim_nested[nk] = nv[:5]
                elif isinstance(nv, dict):
                    # named engines / proxmox: keep keys only + small samples
                    slim_nested[nk] = {
                        sk: (sv if not isinstance(sv, (dict, list)) else (list(sv)[:8] if isinstance(sv, list) else {
                            ssk: ssv for ssk, ssv in list(sv.items())[:12]
                        }))
                        for sk, sv in list(nv.items())[:16]
                    }
                elif isinstance(nv, (str, int, float, bool)) or nv is None:
                    slim_nested[nk] = nv
            current[key] = slim_nested
        elif isinstance(val, list):
            current[key] = val[:5]
        raw = json.dumps(current, default=str)
        if len(raw) <= budget:
            return current

    # Last resort: keep question + short answer_style only.
    minimal = {
        "agent": current.get("agent") or TIA_NAME,
        "question": current.get("question") or "",
        "answer_style": current.get("answer_style") or {"mode": "point_to_point"},
        "note": "context_trimmed_for_size",
    }
    raw = json.dumps(minimal, default=str)
    if len(raw) > budget:
        minimal["question"] = _redact(str(minimal.get("question") or ""), max(80, budget // 3)).rstrip("…")
    return minimal


def _wants_local_briefing(question: str) -> bool:
    """Common SOC asks we can answer from live DB/snapshot without Cursor CLI (~7–10s)."""
    ql = (question or "").lower()
    keys = (
        "what needs my attention",
        "what needs attention",
        "anything i should know",
        "anything i need",
        "brief me",
        "status overview",
        "welcome back",
        "what's going on",
        "whats going on",
        "what is going on",
        "give me a briefing",
        "morning brief",
        "soc brief",
        "situation report",
        "sitrep",
    )
    if any(k in ql for k in keys):
        return True
    # Bare wake-style with almost no extra ask.
    words = [w for w in re.sub(r"[^a-z0-9\s]", " ", ql).split() if w]
    if words and all(w in ("hi", "hey", "hello", "tia", "tea", "there", "boss") for w in words):
        return True
    return False


def answer_with_cursor(
    *,
    question: str,
    tenant_id: Optional[str] = None,
    tenant_short_code: Optional[str] = None,
    alert_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    actor_email: str = "soc",
    apply_actions: bool = False,
    auto_approve: bool = False,
) -> Dict[str, Any]:
    if not soc_console_chat_enabled():
        raise RuntimeError(
            "SOC Console chat unavailable — set SOC_AGENT_ENABLED=true and SOC_AGENT_TOKEN"
        )
    q = (question or "").strip()
    if len(q) < 3:
        raise ValueError("Question is too short")
    if len(q) > 4000:
        raise ValueError("Question is too long")

    # Fast path: briefing-style questions skip Cursor CLI (measured ~7–10s floor).
    if _wants_local_briefing(q) and not alert_id:
        try:
            brief = render_wake_briefing()
            return {
                "agent": TIA_NAME,
                "scope": "platform",
                "tenant": None,
                "answer": brief.get("answer") or "",
                "spoken_answer": brief.get("spoken_answer") or brief.get("answer") or "",
                "provider": "local-briefing",
                "briefing_counts": (brief.get("snapshot") or {}).get("urgency") or {},
                "proposed_actions": [],
                "actions_applied": [],
                "pending_approval": None,
                "sources": {"local_briefing": 1},
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("local briefing fast-path failed: %s", exc)

    tenant = _resolve_tenant(tenant_id, tenant_short_code)
    hours = _infer_hours_away(q)
    briefing = gather_tia_briefing(
        tenant_id=tenant["id"] if tenant else None,
        hours_away=hours,
    )

    if tenant:
        tenant_ctx = _gather_context(tenant, q)
        scope = "tenant"
    else:
        tenant_ctx = {"question": q}
        scope = "platform"

    try:
        platform = gather_platform_visibility(
            question=q,
            tenant_id=tenant["id"] if tenant else None,
            tenant_short_code=tenant["short_code"] if tenant else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform visibility for Tia failed: %s", exc)
        platform = {"error": "platform_visibility_unavailable"}

    topic = str(platform.get("topic") or "general")
    # For focused topics, slim the briefing so patch/vuln detail survives the size budget.
    briefing_for_ctx: Dict[str, Any] = briefing
    if topic in ("patch_gaps", "vulnerabilities", "stack_health", "proxmox"):
        briefing_for_ctx = {
            "counts": briefing.get("counts") or {},
            "window_hours": briefing.get("window_hours"),
            "critical_or_high_open": (briefing.get("critical_or_high_open") or [])[:8],
        }

    try:
        operator_snap = gather_operator_snapshot(hours=hours)
    except Exception as exc:  # noqa: BLE001
        logger.warning("operator snapshot for Tia failed: %s", exc)
        operator_snap = {"error": "operator_snapshot_unavailable"}

    # Operator E2E snapshot + topic detail first so nothing important truncates away.
    ctx: Dict[str, Any] = {
        "agent": TIA_NAME,
        "operator": actor_email,
        "question": q,
        "selected_alert_id": alert_id,
        "answer_style": {
            "mode": "point_to_point",
            "topic": topic,
            "instruction": (
                "Answer only what was asked. Use operator_snapshot, proxmox, "
                "patch_gaps_detail / vulnerabilities_detail when present. "
                "Do not dump unrelated stack health unless asked or on a wake briefing."
            ),
        },
        "operator_snapshot": operator_snap,
        "platform_visibility": platform,
        "briefing": briefing_for_ctx,
        "tenant_context": tenant_ctx,
    }

    # Keep Cursor prompts small — large CLI payloads dominate latency after the ~7s CLI floor.
    budget = 18000 if topic in ("patch_gaps", "vulnerabilities", "proxmox") else 12000
    # Never mid-truncate JSON (that caused "Expecting property name … char 32000").
    op_snap = ctx.get("operator_snapshot")
    if isinstance(op_snap, dict):
        stack = dict(op_snap.get("stack") or {})
        stack.pop("lanes", None)
        ctx["operator_snapshot"] = {**op_snap, "stack": stack}
    safe_ctx = _json_under_budget(ctx, budget)
    if not isinstance(safe_ctx, dict):
        safe_ctx = {"question": q, "answer_style": ctx.get("answer_style")}

    body = {
        "message": q,
        "system": TIA_SYSTEM,
        "context": safe_ctx,
    }
    url = f"{soc_agent_url()}/api/v1/chat"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Soc-Agent-Token": soc_agent_token(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        logger.warning("SOC console chat HTTP %s: %s", exc.code, detail)
        raise RuntimeError(f"Cursor SOC agent chat failed (HTTP {exc.code})") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("SOC console chat unreachable: %s", exc)
        raise RuntimeError(f"Cursor SOC agent unreachable: {exc}") from exc

    answer_raw = str((raw or {}).get("answer") or "").strip()
    if not answer_raw:
        raise RuntimeError("Cursor SOC agent returned an empty answer")

    clean, spoken, proposed = parse_tia_blocks(answer_raw)
    actions_applied: List[Dict[str, Any]] = []
    pending_approval: Optional[Dict[str, Any]] = None

    # Jarvis-style: stage ticket writes for Approve/Decline unless auto_approve.
    if proposed:
        ql = q.lower()
        wants_write = any(
            k in ql
            for k in (
                "update",
                "close",
                "false positive",
                "falsepositive",
                "mark as",
                "set status",
                "resolve",
                "comment",
                "add note",
                "ticket",
            )
        )
        allow_auto = bool(auto_approve) or (
            apply_actions
            and (os.getenv("TIA_AUTO_APPROVE") or "").strip().lower() in ("1", "true", "yes")
        )
        if wants_write and allow_auto:
            actions_applied = apply_tia_actions(
                proposed,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
            ok_n = sum(1 for a in actions_applied if a.get("ok"))
            if ok_n:
                clean = f"{clean}\n\n— Tia applied {ok_n} ticket update(s)."
                spoken = f"{spoken} I also updated {ok_n} ticket{'s' if ok_n != 1 else ''} for you, boss."
        elif wants_write or proposed:
            try:
                pending_approval = enqueue_approval(
                    actions=proposed,
                    question=q,
                    answer_excerpt=clean,
                    actor_email=actor_email,
                )
                clean = (
                    f"{clean}\n\n— Proposed ticket update(s) are waiting in Needs You "
                    f"({pending_approval.get('summary')}). Approve or decline there."
                )
                spoken = (
                    f"{spoken} I staged ticket updates for your approval in Needs You, boss."
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("enqueue approval failed: %s", exc)

    return {
        "agent": TIA_NAME,
        "scope": scope,
        "tenant": (
            {
                "id": tenant["id"],
                "name": tenant["name"],
                "short_code": tenant["short_code"],
            }
            if tenant
            else None
        ),
        "answer": _redact(clean, 8000),
        "spoken_answer": _redact(spoken, 1200),
        "provider": ((raw or {}).get("llm_meta") or {}).get("provider") or "cursor-agent",
        "briefing_counts": briefing.get("counts") or {},
        "proposed_actions": proposed,
        "actions_applied": actions_applied,
        "pending_approval": pending_approval,
        "sources": {
            "critical_alerts": len(briefing.get("critical_or_high_open") or []),
            "false_positives": len(briefing.get("false_positives_closed") or []),
            "incidents": len(briefing.get("incidents_touched") or []),
            "notifications": len(briefing.get("customer_notifications") or []),
        },
    }
