"""
KB-096 Phase 3: Admin AI chat — SOC Q&A over control-plane facts.

Behind AI_CHAT_ENABLED. Read-only tooling; no containment / visibility changes.
Redacts secrets from prompts and answers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|token|secret|authorization|bearer)\s*[:=]\s*\S+"
)


def ai_chat_enabled() -> bool:
    return (os.getenv("AI_CHAT_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _redact(text: str, limit: int = 6000) -> str:
    cleaned = _SECRET_RE.sub(r"\1=[REDACTED]", text or "")
    cleaned = re.sub(r"\b[A-Za-z0-9_\-]{40,}\b", "[REDACTED_TOKEN]", cleaned)
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _resolve_tenant(tenant_id: Optional[str], short_code: Optional[str]) -> Optional[Dict[str, Any]]:
    if tenant_id:
        return fetch_one(
            """
            SELECT id::text AS id, name, short_code
            FROM tenants WHERE id = %s::uuid LIMIT 1;
            """,
            (tenant_id,),
        )
    if short_code:
        return fetch_one(
            """
            SELECT id::text AS id, name, short_code
            FROM tenants WHERE short_code = %s LIMIT 1;
            """,
            (short_code.strip().upper(),),
        )
    return None


def _gather_context(tenant: Dict[str, Any], question: str) -> Dict[str, Any]:
    tid = tenant["id"]
    alerts = fetch_all(
        """
        SELECT id::text, alert_title, severity, status, destination_host,
               ai_risk_score, ai_triage_status, event_time::text
        FROM security_alerts
        WHERE tenant_id = %s::uuid
        ORDER BY event_time DESC NULLS LAST
        LIMIT 15;
        """,
        (tid,),
    )
    incidents = fetch_all(
        """
        SELECT incident_number, title, severity, status, opened_at::text
        FROM incidents
        WHERE tenant_id = %s::uuid
        ORDER BY opened_at DESC NULLS LAST
        LIMIT 12;
        """,
        (tid,),
    )
    iocs = fetch_all(
        """
        SELECT ioc_type, ioc_value, reputation_status, confidence_score, summary
        FROM tenant_threat_intel_iocs
        WHERE tenant_id = %s::uuid AND status = 'active'
        ORDER BY
          CASE reputation_status
            WHEN 'MALICIOUS' THEN 0
            WHEN 'SUSPICIOUS' THEN 1
            ELSE 2
          END,
          confidence_score DESC
        LIMIT 20;
        """,
        (tid,),
    )
    recs = fetch_all(
        """
        SELECT title, priority, status, created_at::text
        FROM customer_recommendations
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 10;
        """,
        (tid,),
    )
    return {
        "tenant": {"name": tenant["name"], "short_code": tenant["short_code"]},
        "question": question,
        "recent_alerts": alerts or [],
        "recent_incidents": incidents or [],
        "threat_intel_iocs": iocs or [],
        "recommendations": recs or [],
    }


def _call_llm(system: str, user: str) -> str:
    base = (os.getenv("AI_ALERT_BASE_URL") or "").rstrip("/")
    model = (os.getenv("AI_CHAT_MODEL") or os.getenv("AI_ALERT_MODEL") or "qwen2.5:14b").strip()
    api_key = (os.getenv("AI_ALERT_API_KEY") or "ollama").strip()
    timeout = int(os.getenv("AI_CHAT_TIMEOUT_SECONDS") or os.getenv("AI_ALERT_TIMEOUT_SECONDS") or "90")
    if not base:
        raise RuntimeError("AI_ALERT_BASE_URL not configured")
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return (
        ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()


def answer_soc_question(
    *,
    question: str,
    tenant_id: Optional[str] = None,
    tenant_short_code: Optional[str] = None,
) -> Dict[str, Any]:
    if not ai_chat_enabled():
        raise RuntimeError("AI chat is disabled (AI_CHAT_ENABLED=false)")
    q = (question or "").strip()
    if len(q) < 3:
        raise ValueError("Question is too short")
    if len(q) > 4000:
        raise ValueError("Question is too long")

    tenant = _resolve_tenant(tenant_id, tenant_short_code)
    if not tenant:
        # Platform-wide light summary only (counts, no cross-tenant detail dump)
        counts = fetch_one(
            """
            SELECT
              (SELECT COUNT(*) FROM tenants WHERE status = 'active') AS tenants,
              (SELECT COUNT(*) FROM security_alerts WHERE created_at > now() - interval '24 hours') AS alerts_24h,
              (SELECT COUNT(*) FROM incidents WHERE status IN ('open','in_progress')) AS open_incidents;
            """
        )
        ctx = {"platform_counts": counts or {}, "question": q}
        scope = "platform"
    else:
        ctx = _gather_context(tenant, q)
        scope = "tenant"

    system = (
        "You are the MSSP Admin SOC assistant for Kevantic. Answer from the provided "
        "JSON facts only. If data is missing, say so. Never invent IOCs or credentials. "
        "Threat Intel IOC rows are the system of record — cite them; do not invent a second "
        "intel database. Do not recommend auto-containment. Keep answers concise for analysts."
    )
    user = _redact(json.dumps(ctx, default=str))
    try:
        answer = _call_llm(system, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI admin chat LLM failed: %s", exc)
        raise RuntimeError(f"AI chat unavailable: {exc}") from exc

    return {
        "scope": scope,
        "tenant": (
            {"id": tenant["id"], "name": tenant["name"], "short_code": tenant["short_code"]}
            if tenant
            else None
        ),
        "answer": _redact(answer, 8000),
        "sources": {
            "alerts": len(ctx.get("recent_alerts") or []),
            "incidents": len(ctx.get("recent_incidents") or []),
            "threat_intel_iocs": len(ctx.get("threat_intel_iocs") or []),
            "recommendations": len(ctx.get("recommendations") or []),
        },
    }
