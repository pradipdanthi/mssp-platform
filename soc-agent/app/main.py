from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.audit import audit
from app.config import settings
from app.core.analyst import run_analyst
from app.core.llm_provider import LLMRouter

app = FastAPI(
    title="MSSP SOC Analyst Agent",
    description=(
        "Sidecar Tier-1/2 analyst powered by Cursor subscription LLM. "
        "Lab Ollama stays on control-plane Tier-1 only — not used here."
    ),
    version="2.1.0",
)

_RECENT: list[dict[str, Any]] = []


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


def require_token(x_soc_agent_token: str | None = Header(default=None)) -> None:
    expected = settings()["ingest_token"]
    if not x_soc_agent_token or not secrets.compare_digest(x_soc_agent_token, expected):
        raise HTTPException(401, "Invalid or missing X-Soc-Agent-Token")


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
def chat(body: ChatIn, _: None = Depends(require_token)) -> dict:
    """Human SOC free-form chat powered by Cursor subscription."""
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
            f"CONTEXT (JSON facts):\n{_json.dumps(body.context, default=str)[:12000]}\n\n"
            f"QUESTION:\n{body.message}"
        )
    answer, meta = LLMRouter().chat(system, user_blob)
    audit(
        settings()["audit_log"],
        "chat.complete",
        {"chars": len(answer), "provider": meta.get("provider")},
    )
    return {"ok": True, "answer": answer, "llm_meta": meta}


@app.post("/api/v1/ingest")
def ingest(alert: AlertIn, _: None = Depends(require_token)) -> dict:
    cfg = settings()
    payload = alert.model_dump()
    audit(
        cfg["audit_log"],
        "ingest.received",
        {"alert_id": alert.alert_id, "title": alert.title, "severity": alert.severity},
    )
    if not LLMRouter().cursor.available():
        raise HTTPException(
            503,
            detail={
                "error": "cursor_llm_not_configured",
                "reason": LLMRouter().cursor.missing_reason(),
                "fix": "Set CURSOR_API_KEY in /opt/soc-agent/.env and restart mssp-soc-agent.service",
            },
        )
    result = run_analyst(payload)
    _RECENT.append(result)
    if len(_RECENT) > 200:
        del _RECENT[:-200]
    return result
