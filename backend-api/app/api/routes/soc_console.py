"""SOC Agent Console APIs — Cursor chat, overview, live activity SSE."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import soc_console_activity, soc_console_chat, tia_conversation, tia_tools, tia_trace
from app.services.soc_agent_client import soc_agent_enabled
from app.services.soc_console_engines import build_engine_wall
from app.services.soc_console_socfeed import build_soc_kpis, list_soc_feed
from app.services.soc_console_stack import build_stack_skeleton
from app.services.subscription_tier_service import get_tenant_id_from_short_code

router = APIRouter(prefix="/admin/soc-console", tags=["soc-console"])
logger = logging.getLogger(__name__)


class SocConsoleChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=3, max_length=4000)
    tenant_id: Optional[UUID] = None
    tenant_short_code: Optional[str] = Field(default=None, max_length=64)
    alert_id: Optional[str] = Field(default=None, max_length=64)
    apply_actions: bool = False
    auto_approve: bool = False


_ID_PATTERN = r"^[A-Za-z0-9_-]{6,64}$"


class TiaConverseRequest(BaseModel):
    """One operator turn. The server, not this payload, decides what 'yes' refers to."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=2, max_length=4000)
    session_id: str = Field(pattern=_ID_PATTERN)
    client_turn_id: Optional[str] = Field(default=None, pattern=_ID_PATTERN)
    tenant_id: Optional[UUID] = None
    tenant_short_code: Optional[str] = Field(default=None, max_length=64)
    view_alert_id: Optional[str] = Field(default=None, max_length=64)


class TiaUiAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=_ID_PATTERN)
    loaded_alert_id: Optional[str] = Field(default=None, max_length=64)
    failure: Optional[str] = Field(default=None, max_length=120)


class TiaClientTimingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=6, max_length=64)
    stages: Dict[str, float] = Field(default_factory=dict, max_length=16)


class SocConsoleActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: List[Dict[str, Any]] = Field(default_factory=list, max_length=5)


class SocConsoleApprovalDecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(min_length=6, max_length=16)


class SocConsoleRoutinePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = None
    hour_local: Optional[int] = Field(default=None, ge=0, le=23)
    minute_local: Optional[int] = Field(default=None, ge=0, le=59)
    timezone: Optional[str] = Field(default=None, max_length=64)


class SocConsoleSpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=2, max_length=900)


class SocConsoleSttRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_base64: str = Field(min_length=64, max_length=5_000_000)
    content_type: str = Field(default="audio/wav", max_length=64)


@router.get("/status")
def soc_console_status(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    from app.services.soc_console_stt import stt_available
    from app.services.soc_console_tts import tts_configured

    enabled = soc_console_chat.soc_console_chat_enabled()
    return {
        "enabled": enabled,
        "soc_agent_enabled": soc_agent_enabled(),
        "agent": "Tia",
        "provider": "cursor-agent",
        "neural_tts": tts_configured(),
        "server_stt": stt_available(),
        "message": (
            "Tia is online (Cursor SOC agent)."
            if enabled
            else "Enable SOC_AGENT_ENABLED and SOC_AGENT_TOKEN so Tia can answer."
        ),
    }


@router.post("/stt")
def soc_console_stt(
    payload: SocConsoleSttRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Transcribe push-to-talk WAV from the SOC console mic (bypasses Chrome Web Speech)."""
    _ = current_user
    ctype = (payload.content_type or "").lower()
    if "wav" not in ctype and "wave" not in ctype:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_type must be audio/wav",
        )
    from app.services.soc_console_stt import transcribe_wav_base64

    text, meta = transcribe_wav_base64(payload.audio_base64)
    if not text:
        logger.info(
            "soc-console STT miss reason=%s duration=%s",
            meta.get("reason"),
            meta.get("duration_sec"),
        )
        return {"ok": False, "text": "", **meta}
    logger.info(
        "soc-console STT hit duration=%s text=%r",
        meta.get("duration_sec"),
        (text or "")[:120],
    )
    return {"ok": True, "text": text, **meta}


@router.post("/speak")
def soc_console_speak(
    payload: SocConsoleSpeakRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Neural TTS for Tia when TIA_TTS_ENABLED + API key are set."""
    _ = current_user
    from app.services.soc_console_tts import synthesize_tia_speech, tts_configured

    if not tts_configured():
        return {"available": False, "reason": "neural_tts_not_configured"}
    audio = synthesize_tia_speech(payload.text)
    if not audio:
        return {"available": False, "reason": "tts_failed"}
    return {"available": True, **audio}


@router.get("/wake-briefing")
def soc_console_wake_briefing(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
    session_id: Optional[str] = Query(default=None, pattern=_ID_PATTERN),
    tenant_id: Optional[UUID] = Query(default=None),
    tenant_short_code: Optional[str] = Query(default=None, max_length=64),
) -> Dict[str, Any]:
    """Proactive 'Hi Tia' welcome: alerts + urgency + end-to-end stack health.

    When session_id is present, the same list_alerts order is stored on that
    conversation so 'the first one' resolves after welcome.
    """
    from app.services.soc_console_operator import render_wake_briefing

    listed = None
    if session_id:
        tenant = None
        if tenant_id or tenant_short_code:
            tenant = tia_tools.resolve_tenant(str(tenant_id) if tenant_id else None, tenant_short_code)
            if not tenant:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        scope = _tia_scope(current_user, session_id, tenant["id"] if tenant else None)
        listed = tia_conversation.remember_listing(scope)
    result = render_wake_briefing(listed_alerts=listed)
    actor = str(current_user.get("email") or current_user.get("full_name") or "soc")
    soc_console_activity.push_local_activity(
        kind="ai_response",
        title="Tia wake briefing",
        detail=str(result.get("spoken_answer") or "")[:240],
        severity="info",
        actor=actor,
    )
    return result


@router.get("/command-center")
def soc_console_command_center(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Jarvis-style Command Center payload for the SOC Agent Console home."""
    _ = current_user
    from app.services.soc_console_approvals import list_approvals, pending_count
    from app.services.soc_console_chat import soc_console_chat_enabled
    from app.services.soc_console_operator import gather_operator_snapshot, render_wake_briefing
    from app.services.soc_console_routines import list_routines, tick_routines
    from app.services.soc_console_stt import stt_available
    from app.services.soc_console_tts import tts_configured

    # Fire due morning/afternoon briefs when the console is open.
    ran_routines = tick_routines()

    snap = gather_operator_snapshot()
    wake = render_wake_briefing(snap)
    cp = ((snap.get("proxmox") or {}).get("named") or {}).get("mssp_control") or {}
    urg = snap.get("urgency") or {}
    stack = snap.get("stack") or {}
    kpis = build_soc_kpis()
    try:
        from app.db.session import fetch_one as _fetch_one

        cust = _fetch_one("SELECT COUNT(*)::int AS n FROM tenants WHERE status = 'active';") or {}
        kpis = {**kpis, "customers": int(cust.get("n") or 0)}
    except Exception:  # noqa: BLE001
        kpis = {**kpis, "customers": int(kpis.get("customers") or 0)}

    # Reuse lanes already gathered inside operator snapshot (avoid a second engine wall probe).
    agents = []
    for lane in ((snap.get("stack") or {}).get("lanes") or []):
        agents.append(
            {
                "id": lane.get("id"),
                "label": lane.get("label"),
                "vm": lane.get("vm"),
                "status": "active" if lane.get("reachable") else "offline",
                "reachable": bool(lane.get("reachable")),
                "latency_ms": lane.get("latency_ms"),
                "pulse_24h": lane.get("pulse_24h") or 0,
            }
        )
    if not agents:
        for lane in (build_engine_wall().get("lanes") or []):
            agents.append(
                {
                    "id": lane.get("id"),
                    "label": lane.get("label"),
                    "vm": lane.get("vm"),
                    "status": "active" if lane.get("reachable") else "offline",
                    "reachable": bool(lane.get("reachable")),
                    "latency_ms": lane.get("latency_ms"),
                    "pulse_24h": lane.get("pulse_24h") or 0,
                }
            )

    quick = [
        {"id": "brief", "label": "Wake briefing", "prompt": "Hi Tia, what needs my attention?"},
        {"id": "crit", "label": "Critical alerts", "prompt": "Hi Tia, list critical and high alerts"},
        {"id": "wazuh", "label": "Wazuh health", "prompt": "Hi Tia, Wazuh manager health and RAM"},
        {"id": "stack", "label": "Stack health", "prompt": "Hi Tia, end-to-end stack health"},
        {"id": "patches", "label": "Patch gaps", "prompt": "Hi Tia, break down the patch gaps"},
        {"id": "proxmox", "label": "Proxmox VMs", "prompt": "Hi Tia, summarize Proxmox VM CPU and RAM"},
    ]

    return {
        "generated_at": snap.get("generated_at"),
        "agent": "Tia",
        "version": "TIA COMMAND CENTER v1.0",
        "system_status": "OPTIMAL" if snap.get("priority") == "clear" else str(snap.get("priority") or "ATTENTION").upper(),
        "kpis": kpis,
        "chat_enabled": soc_console_chat_enabled(),
        "voice": {
            "server_stt": stt_available(),
            "neural_tts": tts_configured(),
            "wake_phrase": "Hi Tia",
            "free_hand": True,
        },
        "core": {
            "name": "Tia AI Core",
            "status": "active" if soc_console_chat_enabled() else "standby",
            "provider": "cursor-agent" if soc_console_chat_enabled() else "offline",
            "memory_note": "Live operator snapshot each turn",
        },
        "gauges": {
            "cpu_pct": cp.get("cpu_pct"),
            "ram_used_pct": (
                round(
                    100.0
                    * float(cp.get("ram_used_gb") or 0)
                    / float(cp.get("ram_configured_gb") or 1),
                    1,
                )
                if cp.get("ram_configured_gb")
                else None
            ),
            "ram_used_gb": cp.get("ram_used_gb"),
            "ram_configured_gb": cp.get("ram_configured_gb"),
            "vcpus": cp.get("vcpus"),
            "engines_online": stack.get("engines_online"),
            "engines_total": stack.get("engines_total"),
        },
        "urgency": urg,
        "needs_attention": snap.get("needs_attention") or [],
        "priority": snap.get("priority"),
        "top_alerts": snap.get("top_alerts") or [],
        "top_incidents": snap.get("top_incidents") or [],
        "agents": agents,
        "proxmox_named": (snap.get("proxmox") or {}).get("named") or {},
        "compliance": snap.get("compliance") or {},
        "wake_preview": {
            "spoken": wake.get("spoken_answer"),
            "answer": wake.get("answer"),
        },
        "quick_commands": quick,
        "activity": soc_console_activity.list_activity(limit=24),
        "approvals": list_approvals(status="pending", limit=12),
        "pending_approvals": pending_count(),
        "routines": list_routines(),
        "routines_ran_now": [
            {
                "id": (r.get("routine") or {}).get("id"),
                "name": (r.get("routine") or {}).get("name"),
                "spoken_answer": (r.get("briefing") or {}).get("spoken_answer"),
            }
            for r in (ran_routines or [])
        ],
    }


@router.post("/chat")
def soc_console_chat_endpoint(
    payload: SocConsoleChatRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    if not soc_console_chat.soc_console_chat_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SOC Console Cursor chat is not configured",
        )
    tenant_id = str(payload.tenant_id) if payload.tenant_id else None
    if not tenant_id and payload.tenant_short_code:
        tenant_id = get_tenant_id_from_short_code(payload.tenant_short_code)

    actor = str(current_user.get("email") or current_user.get("full_name") or "soc")
    actor_id = str(current_user.get("id") or "") or None
    soc_console_activity.push_local_activity(
        kind="ai_query",
        title="Tia query",
        detail=payload.message[:240],
        severity="info",
        alert_id=payload.alert_id,
        actor=actor,
    )

    legacy_trace = tia_trace.Trace("model")
    try:
        result = soc_console_chat.answer_with_cursor(
            question=payload.message,
            tenant_id=tenant_id,
            tenant_short_code=payload.tenant_short_code,
            alert_id=payload.alert_id,
            actor_user_id=actor_id,
            actor_email=actor,
            apply_actions=bool(payload.apply_actions),
            auto_approve=bool(payload.auto_approve),
            trace=legacy_trace,
        )
    except ValueError as exc:
        legacy_trace.finish(ok=False)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        legacy_trace.finish(ok=False)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    legacy_trace.finish(ok=True)

    soc_console_activity.push_local_activity(
        kind="ai_response",
        title="Tia answered",
        detail=str(result.get("spoken_answer") or result.get("answer") or "")[:240],
        severity="info",
        alert_id=payload.alert_id,
        actor="Tia",
    )
    return result


def _tia_scope(current_user: Dict[str, Any], session_id: str, tenant_id: Optional[str]) -> tia_tools.Scope:
    return tia_tools.Scope(
        operator_email=str(current_user.get("email") or ""),
        operator_id=str(current_user.get("id") or "") or None,
        role=str(current_user.get("role") or ""),
        session_id=session_id,
        tenant_id=tenant_id,
    )


def _tia_not_ready(exc: Exception) -> HTTPException:
    logger.error("TIA conversation unavailable: %s", exc)
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="conversation_schema_unavailable")


@router.get("/capabilities")
def soc_console_capabilities(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """What TIA can really do through chat and voice, read from the tool registry."""
    return {
        "tools": tia_tools.capabilities(),
        "not_available_by_chat": list(tia_tools.NOT_AVAILABLE_BY_CHAT),
        "conversation_ready": tia_conversation.schema_fault() is None,
    }


@router.post("/converse")
def soc_console_converse(
    payload: TiaConverseRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Conversational turn: tools, pending actions and verified dashboard commands."""
    trace = tia_trace.Trace("navigation", turn_id=payload.client_turn_id)
    ok = True
    try:
        with trace.stage("auth_and_context"):
            tenant = None
            if payload.tenant_id or payload.tenant_short_code:
                tenant = tia_tools.resolve_tenant(str(payload.tenant_id) if payload.tenant_id else None, payload.tenant_short_code)
                if not tenant:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
            scope = _tia_scope(current_user, payload.session_id, tenant["id"] if tenant else None)

        def model_fallback(
            question: str,
            selected_alert_id: Optional[str],
            sc: tia_tools.Scope,
            evidence: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            trace.path = "model"
            out = soc_console_chat.answer_with_cursor(
                question=question,
                tenant_id=sc.tenant_id,
                alert_id=selected_alert_id,
                actor_user_id=sc.operator_id,
                actor_email=sc.operator_email,
                trace=trace,
                evidence=evidence,
                allow_live_floor=False,
            )
            return {
                "answer": out.get("answer"),
                "spoken_answer": out.get("spoken_answer"),
                "provider": out.get("provider"),
                "pending_approval": out.get("pending_approval"),
                "proposed_actions": out.get("proposed_actions"),
                "briefing_counts": out.get("briefing_counts"),
            }

        trace_started = trace.elapsed_ms()
        try:
            result = tia_conversation.handle_turn(
                scope,
                text=payload.message,
                client_turn_id=payload.client_turn_id,
                view_alert_id=payload.view_alert_id,
                request_id=trace.request_id,
                tenant=tenant,
                fallback=model_fallback,
                trace=trace,
            )
        except tia_conversation.ConversationNotReady as exc:
            ok = False
            raise _tia_not_ready(exc) from exc
        except tia_conversation.TurnInProgress as exc:
            ok = False
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="turn_in_progress") from exc
        except tia_tools.ToolError as exc:
            ok = False
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message) from exc
        if trace.path != "model":
            trace.add("tool_execution", trace.elapsed_ms() - trace_started)
            if result.get("intent") in ("list",):
                trace.path = "status"
            elif result.get("intent") in ("open_case", "pending_cancelled", "confirm_expired"):
                trace.path = "action"
        if result.get("replayed"):
            trace.path = "navigation"
        return result
    except HTTPException:
        ok = False
        raise
    finally:
        trace.finish(ok=ok)


@router.get("/ui-commands")
def soc_console_pending_ui_commands(
    session_id: str = Query(pattern=_ID_PATTERN),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Commands this browser session has not yet confirmed (used after a reconnect)."""
    try:
        return {"commands": tia_conversation.pending_commands(_tia_scope(current_user, session_id, None))}
    except tia_conversation.ConversationNotReady as exc:
        raise _tia_not_ready(exc) from exc


@router.get("/ui-commands/{command_id}")
def soc_console_ui_command_status(
    command_id: str,
    session_id: str = Query(pattern=_ID_PATTERN),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    try:
        row = tia_conversation.command_status(_tia_scope(current_user, session_id, None), command_id)
    except tia_conversation.ConversationNotReady as exc:
        raise _tia_not_ready(exc) from exc
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
    return row


@router.post("/ui-commands/{command_id}/ack")
def soc_console_ui_command_ack(
    command_id: str,
    payload: TiaUiAckRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """The dashboard reports what it actually loaded. Only a matching id is believed."""
    try:
        return tia_conversation.acknowledge_command(
            _tia_scope(current_user, payload.session_id, None),
            command_id,
            loaded_alert_id=payload.loaded_alert_id,
            failure=payload.failure,
        )
    except tia_conversation.ConversationNotReady as exc:
        raise _tia_not_ready(exc) from exc
    except tia_tools.ToolError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc


@router.post("/telemetry/client")
def soc_console_client_timing(
    payload: TiaClientTimingRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Browser-measured stages (speech end, first audio, interruption) joined to the server turn."""
    return {"recorded": tia_trace.record_client_stages(payload.request_id, payload.stages)}


@router.get("/telemetry/latency")
def soc_console_latency_summary(
    window_minutes: int = Query(default=60, ge=1, le=10080),
    path: Optional[str] = Query(default=None, max_length=16),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """p50/p95 by path and stage with sample sizes. Numbers and ids only."""
    return tia_trace.summarize(window_minutes, path if path in tia_trace.PATHS else None)


@router.post("/actions")
def soc_console_actions(
    payload: SocConsoleActionRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Explicit ticket updates from the SOC console (Tia / analyst)."""
    from app.services.soc_console_tia import apply_tia_actions

    actor = str(current_user.get("email") or current_user.get("full_name") or "soc")
    actor_id = str(current_user.get("id") or "") or None
    results = apply_tia_actions(
        list(payload.actions or [])[:5],
        actor_user_id=actor_id,
        actor_email=actor,
        execution_source="analyst_api",
    )
    return {"results": results, "applied": sum(1 for r in results if r.get("ok"))}


@router.get("/approvals")
def soc_console_list_approvals(
    status: str = Query(default="pending", max_length=16),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    from app.services.soc_console_approvals import list_approvals, pending_count

    items = list_approvals(status=status, limit=30)
    return {"items": items, "pending_count": pending_count()}


@router.post("/approvals/{approval_id}/decide")
def soc_console_decide_approval(
    approval_id: str,
    payload: SocConsoleApprovalDecideRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    from app.services.soc_console_approvals import decide_approval

    actor = str(current_user.get("email") or current_user.get("full_name") or "soc")
    actor_id = str(current_user.get("id") or "") or None
    try:
        item = decide_approval(
            approval_id,
            decision=payload.decision,
            actor_user_id=actor_id,
            actor_email=actor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    soc_console_activity.push_local_activity(
        kind="approval",
        title=f"Tia action {item.get('status')}",
        detail=str(item.get("summary") or "")[:240],
        severity="info",
        actor=actor,
    )
    return {"approval": item}


@router.get("/routines")
def soc_console_list_routines(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    from app.services.soc_console_routines import list_routines, tick_routines

    # Catch up due schedules when the console is open.
    ran = tick_routines()
    return {"routines": list_routines(), "ran_now": [r.get("routine", {}).get("id") for r in ran]}


@router.patch("/routines/{routine_id}")
def soc_console_patch_routine(
    routine_id: str,
    payload: SocConsoleRoutinePatchRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    from app.services.soc_console_routines import update_routine

    patch = payload.model_dump(exclude_none=True)
    try:
        item = update_routine(routine_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="routine not found") from exc
    return {"routine": item}


@router.post("/routines/{routine_id}/run")
def soc_console_run_routine(
    routine_id: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    from app.services.soc_console_routines import run_routine

    try:
        result = run_routine(routine_id, force=True)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="routine not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return result


@router.get("/overview")
def soc_console_overview(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    kpis = build_soc_kpis()
    recent = fetch_all(
        """
        SELECT id::text, alert_title, severity, status, event_time::text,
               destination_host, source_tool, ai_verdict, ai_confidence,
               occurrence_count, first_seen_at::text, last_seen_at::text,
               CASE WHEN source_ip IS NOT NULL THEN host(source_ip)::text ELSE NULL END AS source_ip
        FROM security_alerts
        WHERE status NOT IN ('closed','false_positive')
        ORDER BY created_at DESC
        LIMIT 8;
        """
    )
    return {
        "kpis": kpis,
        "recent_alerts": recent or [],
        "chat_enabled": soc_console_chat.soc_console_chat_enabled(),
    }


@router.get("/stack")
def soc_console_stack(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Live MSSP system skeleton — portals, control plane, engines, appliances."""
    _ = current_user
    return build_stack_skeleton()


@router.get("/engines")
def soc_console_engines(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Hollywood engine wall — VM/tool lanes with reachability + live streams."""
    _ = current_user
    return build_engine_wall()


@router.get("/engine-health")
def soc_console_engine_health(
    engine: Optional[str] = Query(default=None, max_length=40),
    refresh: bool = Query(default=False),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Layered engine health (reachability / API / login / application / telemetry), role-gated detail."""
    from app.services import tia_engine_health as eh

    report = eh.get_health(force=refresh, only=engine)
    return eh.redact_for_role(report, str(current_user.get("role") or ""))


@router.get("/alerts/{alert_id}/ticket-summary")
def soc_console_ticket_summary(
    alert_id: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Case-specific summary built only from the stored record (facts, unknowns, hypotheses, next step)."""
    from app.services import tia_ticket_summary

    scope = tia_tools.Scope(
        operator_email=str(current_user.get("email") or ""), operator_id=str(current_user.get("id") or "") or None,
        role=str(current_user.get("role") or ""), session_id="ticket-summary", tenant_id=None,
    )
    try:
        return tia_ticket_summary.build(scope, alert_id)
    except tia_tools.ToolError as err:
        raise HTTPException(status_code=404 if err.code == "not_found" else 403, detail=err.message)


@router.get("/queue")
def soc_console_queue(
    severity: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=80, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """High-density alert/incident queue for the center panel."""
    _ = current_user
    clauses = ["1=1"]
    params: list[Any] = []
    if severity:
        sev_list = [s.strip().lower() for s in severity.split(",") if s.strip()]
        if sev_list:
            clauses.append("lower(sa.severity) = ANY(%s)")
            params.append(sev_list)
    if status_filter:
        st_list = [s.strip().lower() for s in status_filter.split(",") if s.strip()]
        if st_list:
            clauses.append("lower(sa.status) = ANY(%s)")
            params.append(st_list)
    if q:
        clauses.append(
            "(sa.alert_title ILIKE %s OR COALESCE(sa.destination_host,'') ILIKE %s "
            "OR COALESCE(t.short_code,'') ILIKE %s)"
        )
        like = f"%{q}%"
        params.extend([like, like, like])
    where = " AND ".join(clauses)
    params.append(limit)
    alerts = fetch_all(
        f"""
        SELECT sa.id::text AS id, sa.alert_title, sa.severity, sa.status,
               sa.event_time::text, sa.destination_host, sa.source_tool,
               sa.ai_verdict, sa.ai_confidence, sa.ai_containment_suggestion,
               sa.occurrence_count, sa.first_seen_at::text, sa.last_seen_at::text,
               CASE WHEN sa.source_ip IS NOT NULL THEN host(sa.source_ip)::text ELSE NULL END AS source_ip,
               t.name AS tenant_name, t.short_code
        FROM security_alerts sa
        JOIN tenants t ON t.id = sa.tenant_id
        WHERE {where}
        ORDER BY
          CASE lower(sa.severity)
            WHEN 'critical' THEN 0 WHEN 'high' THEN 1
            WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
          END,
          sa.created_at DESC
        LIMIT %s;
        """,
        tuple(params),
    )
    incidents = fetch_all(
        """
        SELECT i.id::text AS id, i.incident_number, i.title, i.severity, i.status,
               i.opened_at::text, t.short_code, t.name AS tenant_name
        FROM incidents i
        JOIN tenants t ON t.id = i.tenant_id
        WHERE i.status IN ('open','in_progress')
        ORDER BY i.opened_at DESC NULLS LAST
        LIMIT 40;
        """
    )
    return {"alerts": alerts or [], "incidents": incidents or []}


def _review_call(fn, *args, **kwargs) -> Dict[str, Any]:
    """Run a review-service call and map its refusals to HTTP errors."""
    from app.services import tia_review
    from app.services.tia_schema import SchemaNotReady

    try:
        return fn(*args, **kwargs)
    except tia_review.ReviewError as exc:
        raise HTTPException(status_code=exc.http, detail=exc.message)
    except SchemaNotReady as exc:
        logger.error("review queue unavailable: schema not ready (missing=%s)", exc.missing)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review queue is not available: required database migration is missing",
        )


@router.get("/review-queue")
def soc_console_review_queue(
    status_filter: Optional[str] = Query(default=None, alias="status", pattern="^(open|acknowledged|resolved)$"),
    tenant_id: Optional[UUID] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None, max_length=200),
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Investigations that did not complete or need a person, soonest deadline first.

    SOC roles only (customer roles get 403). Deadlines are provisional. Holds no raw
    alert payloads; customer APIs never read it.
    """
    from app.services import tia_review

    _ = current_user
    return _review_call(
        tia_review.list_items,
        status=status_filter,
        tenant_id=str(tenant_id) if tenant_id else None,
        assigned_to=assigned_to,
        include_resolved=include_resolved or status_filter == "resolved",
        limit=limit,
        offset=offset,
    )


@router.get("/review-queue/summary")
def soc_console_review_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    from app.services import tia_review

    _ = current_user
    return _review_call(tia_review.summary)


@router.get("/review-queue/{item_id}")
def soc_console_review_detail(
    item_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    from app.services import tia_review

    _ = current_user
    return _review_call(tia_review.get_item, str(item_id))


class ReviewNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None, max_length=1000)


class ReviewAssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee: Optional[str] = Field(default=None, max_length=200)


@router.post("/review-queue/{item_id}/acknowledge")
def soc_console_review_acknowledge(
    item_id: UUID,
    body: ReviewNoteIn,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Take ownership of the page. Does NOT resolve the item or change the case."""
    from app.services import tia_review

    return _review_call(tia_review.acknowledge, str(item_id), current_user, body.note)


@router.post("/review-queue/{item_id}/assign")
def soc_console_review_assign(
    item_id: UUID,
    body: ReviewAssignIn,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    from app.services import tia_review

    return _review_call(tia_review.assign, str(item_id), current_user, body.assignee)


@router.post("/review-queue/{item_id}/resolve")
def soc_console_review_resolve(
    item_id: UUID,
    body: ReviewNoteIn,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    from app.services import tia_review

    return _review_call(tia_review.resolve, str(item_id), current_user, body.note)


@router.post("/review-queue/{item_id}/reopen")
def soc_console_review_reopen(
    item_id: UUID,
    body: ReviewNoteIn,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    from app.services import tia_review

    return _review_call(tia_review.reopen, str(item_id), current_user, body.note)


@router.get("/tia-readiness")
def soc_console_tia_readiness(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """Operational readiness of the investigation/notification path (never claims paging works unless configured)."""
    from app.services import tia_schema

    _ = current_user
    return tia_schema.readiness()


@router.get("/activity")
def soc_console_activity_list(
    limit: int = Query(default=80, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    """SOC-analyst feed only: alerts, incidents, events, vulns, patch gaps."""
    _ = current_user
    items = list_soc_feed(limit=limit)
    # Merge recent AI/console markers so chat actions still appear
    local = soc_console_activity.list_activity(limit=20)
    local = [x for x in local if str(x.get("source") or "") == "soc_console"]
    merged = local + items
    seen = set()
    out = []
    for it in sorted(merged, key=lambda x: str(x.get("ts") or ""), reverse=True):
        iid = it.get("id")
        if iid in seen:
            continue
        seen.add(iid)
        out.append(it)
        if len(out) >= limit:
            break
    return {"items": out, "count": len(out), "kpis": build_soc_kpis()}


@router.get("/activity/stream")
def soc_console_activity_stream(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> StreamingResponse:
    """SSE — SOC-critical feed + KPI pulse (no engine topology)."""
    _ = current_user

    def _snapshot(limit: int = 60) -> List[Dict[str, Any]]:
        items = list_soc_feed(limit=limit)
        local = [
            x
            for x in soc_console_activity.list_activity(limit=15)
            if str(x.get("source") or "") == "soc_console"
        ]
        merged = local + items
        seen = set()
        out: List[Dict[str, Any]] = []
        for it in sorted(merged, key=lambda x: str(x.get("ts") or ""), reverse=True):
            iid = it.get("id")
            if iid in seen:
                continue
            seen.add(iid)
            out.append(it)
            if len(out) >= limit:
                break
        return out

    def event_gen() -> Iterator[bytes]:
        cursor = "1970-01-01T00:00:00.000Z"
        seed = _snapshot(60)
        if seed:
            cursor = str(seed[0].get("ts") or cursor)
            payload = json.dumps(
                {"type": "snapshot", "items": seed, "kpis": build_soc_kpis()},
                default=str,
            )
            yield f"event: snapshot\ndata: {payload}\n\n".encode("utf-8")
        yield b": connected\n\n"
        ticks = 0
        while True:
            try:
                fresh = _snapshot(80)
                new_items = [it for it in fresh if str(it.get("ts") or "") > cursor][:30]
                if new_items:
                    cursor = str(new_items[0].get("ts") or cursor)
                    payload = json.dumps({"type": "activity", "items": new_items}, default=str)
                    yield f"event: activity\ndata: {payload}\n\n".encode("utf-8")
                else:
                    yield b": keepalive\n\n"
                ticks += 1
                if ticks % 3 == 0:
                    kp = json.dumps({"type": "kpis", "kpis": build_soc_kpis()}, default=str)
                    yield f"event: kpis\ndata: {kp}\n\n".encode("utf-8")
                soc_console_activity.sleep_poll(2.0)
            except GeneratorExit:
                break
            except Exception as exc:  # noqa: BLE001
                err = json.dumps({"type": "error", "detail": str(exc)[:200]})
                yield f"event: error\ndata: {err}\n\n".encode("utf-8")
                soc_console_activity.sleep_poll(3.0)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
