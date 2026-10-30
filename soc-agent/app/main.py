from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.audit import audit
from app.config import settings
from app.core.analyst import run_analyst
from app.core.llm_provider import LLMRouter, ProviderError

app = FastAPI(
    title="MSSP SOC Analyst Agent",
    description=(
        "Sidecar Tier-1/2 analyst powered by Cursor subscription LLM. "
        "Lab Ollama stays on control-plane Tier-1 only — not used here."
    ),
    version="2.1.0",
)

_RECENT: list[dict[str, Any]] = []


@app.on_event("startup")
def _resume_callback_spool() -> None:
    """Results spooled before a restart are retried, not forgotten."""
    from app.core.callback import callback_configured, spool_depth, start_retry_thread

    if callback_configured():
        start_retry_thread()
        depth = spool_depth()
        if depth:
            import logging

            logging.getLogger(__name__).warning("callback spool has %s undelivered result(s); retrying", depth)


class AlertIn(BaseModel):
    alert_id: str | None = None
    title: str
    severity: str = "medium"
    description: str | None = None
    source_ip: str | None = None
    destination_ip: str | None = None
    domain: str | None = None
    hostname: str | None = None
    tenant: str | None = None
    source_platform: str | None = "webhook"
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


_INSECURE_TOKENS = frozenset({"", "change-me-soc-ingest", "changeme", "change-me"})


def require_token(x_soc_agent_token: str | None = Header(default=None)) -> None:
    expected = settings()["ingest_token"]
    # Fail closed: a service left on the shipped placeholder must not accept requests.
    if expected.strip().lower() in _INSECURE_TOKENS or len(expected) < 24:
        raise HTTPException(503, "SOC agent token is not configured (placeholder or too short)")
    if not x_soc_agent_token or not secrets.compare_digest(x_soc_agent_token, expected):
        raise HTTPException(401, "Invalid or missing X-Soc-Agent-Token")


def _trace_ids(request_id: str | None, conversation_id: str | None, turn_id: str | None, job_id: str | None) -> dict:
    """Correlation ids only (never content). Clipped and restricted to a safe alphabet."""
    import re as _re

    def clean(v: str | None) -> str | None:
        return v[:64] if v and _re.fullmatch(r"[A-Za-z0-9_.:\-]{1,64}", v) else None

    return {k: v for k, v in (("request_id", clean(request_id)), ("conversation_id", clean(conversation_id)),
                              ("turn_id", clean(turn_id)), ("job_id", clean(job_id))) if v}


def _spool_depth() -> int:
    try:
        from app.core.callback import spool_depth

        return spool_depth()
    except Exception:  # noqa: BLE001
        return -1


@app.get("/health")
def health() -> dict:
    cfg = settings()
    audit_path = Path(cfg["triage_audit_log"])
    llm = LLMRouter().status()
    return {
        "status": "ok" if llm["cursor"]["available"] else "degraded",
        "service": cfg["agent_name"],
        "version": "2.1.0",
        "llm": llm,
        "recent_cases": len(_RECENT),
        "callback_spool_depth": _spool_depth(),
        "triage_audit_exists": audit_path.is_file(),
        "triage_audit_bytes": audit_path.stat().st_size if audit_path.is_file() else 0,
        "note": "SOC agent uses Cursor subscription only; Ollama is not used here",
    }


@app.get("/api/cases")
def list_cases(_: None = Depends(require_token)) -> dict:
    return {"count": len(_RECENT), "cases": list(reversed(_RECENT[-50:]))}


class ChatIn(BaseModel):
    message: str = Field(min_length=3, max_length=8000)
    system: str | None = Field(default=None, max_length=4000)
    context: dict[str, Any] | None = None


@app.post("/api/v1/chat")
def chat(
    body: ChatIn,
    _: None = Depends(require_token),
    x_tia_request_id: str | None = Header(default=None),
    x_tia_conversation_id: str | None = Header(default=None),
    x_tia_turn_id: str | None = Header(default=None),
    x_tia_job_id: str | None = Header(default=None),
) -> dict:
    """Human SOC free-form chat powered by Cursor subscription."""
    import time as _time

    t_in = _time.monotonic()
    ids = _trace_ids(x_tia_request_id, x_tia_conversation_id, x_tia_turn_id, x_tia_job_id)
    if not LLMRouter().cursor.available():
        raise HTTPException(
            503,
            detail={
                "error": "cursor_llm_not_configured",
                "reason": LLMRouter().cursor.missing_reason(),
            },
        )
    system = (body.system or "").strip() or (
        "You are an enterprise MSSP SOC analyst assistant for Kevantic NikTiar. "
        "Answer from provided context when present. Never invent IOCs or credentials. "
        "Never claim you executed containment — only advise. Be concise and actionable."
    )
    user_blob = body.message
    if body.context:
        import json as _json

        user_blob = (
            "LIVE FACTS (these counts are real — quote them; never mention this block, "
            "JSON, trimming, or missing context):\n"
            f"{_json.dumps(body.context, default=str)[:6000]}\n\n"
            f"QUESTION:\n{body.message}"
        )
    try:
        answer, meta = LLMRouter().chat(system, user_blob)
    except ProviderError as exc:
        audit(
            settings()["audit_log"],
            "chat.failed",
            {"error_category": exc.category},
        )
        raise HTTPException(
            504 if exc.timed_out else 502,
            detail={"error": "provider_error", "error_category": exc.category},
        ) from exc
    cli_t = dict(meta.get("timings") or {})
    timings = {
        # Time in this process before and around the CLI call (excludes CLI runtime).
        "agent_queue": round(max(0.0, (_time.monotonic() - t_in) * 1000 - float(meta.get("duration_ms") or 0)), 2),
        "cli_spawn": cli_t.get("cli_spawn", 0.0),
        "cli_first_output": cli_t.get("cli_first_output", 0.0),
        "cli_total": cli_t.get("cli_total", 0.0),
        "runner_connect": cli_t.get("runner_connect", 0.0),
        # Wall clock at reply time, for cross-VM offset estimation by the caller.
        "agent_epoch_ms": int(_time.time() * 1000),
    }
    audit(
        settings()["audit_log"],
        "chat.complete",
        {"chars": len(answer), "provider": meta.get("provider"), **ids, "timings": {k: v for k, v in timings.items() if k != "agent_epoch_ms"}},
    )
    meta = {k: v for k, v in meta.items() if k != "timings"}
    return {"ok": True, "answer": answer, "llm_meta": meta, "timings": timings}


@app.post("/api/v1/ingest")
def ingest(
    alert: AlertIn,
    _: None = Depends(require_token),
    x_tia_request_id: str | None = Header(default=None),
    x_tia_job_id: str | None = Header(default=None),
) -> dict:
    cfg = settings()
    payload = alert.model_dump()
    audit(
        cfg["audit_log"],
        "ingest.received",
        {
            "alert_id": alert.alert_id, "title": alert.title, "severity": alert.severity,
            **_trace_ids(x_tia_request_id, None, None, x_tia_job_id),
        },
    )
    # A provider that is not configured or not working is a failed investigation,
    # not a refusal: run_analyst returns an explicit failed result and pushes it
    # to the control plane so the case lands in the analyst queue.
    result = run_analyst(payload)
    _RECENT.append(result)
    if len(_RECENT) > 200:
        del _RECENT[:-200]
    return result
