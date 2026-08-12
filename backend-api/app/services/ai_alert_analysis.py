"""KB-092: LLM-backed plain-English alert analysis (OpenAI-compatible / Ollama)."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from app.db.session import fetch_one, fetch_one_write

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|token|secret|authorization|bearer)\s*[:=]\s*\S+"
)
_GENERIC_SUMMARY_PREFIXES = (
    "soc is reviewing:",
    "security event logged",
    "alert received for soc",
)


def ai_alert_enabled() -> bool:
    return (os.getenv("AI_ALERT_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")


def _min_severity_rank() -> int:
    raw = (os.getenv("AI_ALERT_MIN_SEVERITY") or "high").strip().lower()
    ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return ranks.get(raw, 3)


def severity_meets_threshold(severity: Optional[str]) -> bool:
    ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    sev = (severity or "").strip().lower()
    return ranks.get(sev, 0) >= _min_severity_rank()


def _is_generic_summary(text: Optional[str]) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    return any(t.startswith(p) for p in _GENERIC_SUMMARY_PREFIXES)


def _redact(text: str, limit: int = 2500) -> str:
    cleaned = _SECRET_RE.sub(r"\1=[REDACTED]", text or "")
    cleaned = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "[REDACTED_TOKEN]", cleaned)
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _minimize_raw(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return _redact(raw, 1500)
    if not isinstance(raw, dict):
        return _redact(str(raw), 1500)
    keep_keys = (
        "rule",
        "agent",
        "data",
        "decoder",
        "location",
        "full_log",
        "title",
        "description",
    )
    slim = {k: raw[k] for k in keep_keys if k in raw}
    try:
        return _redact(json.dumps(slim, default=str)[:2000])
    except (TypeError, ValueError):
        return ""


def _call_openai_compatible(prompt: str) -> Dict[str, str]:
    base = (os.getenv("AI_ALERT_BASE_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("AI_ALERT_BASE_URL is not set")
    model = (os.getenv("AI_ALERT_MODEL") or "qwen2.5:14b").strip()
    api_key = (os.getenv("AI_ALERT_API_KEY") or "").strip()
    timeout = float(os.getenv("AI_ALERT_TIMEOUT_SECONDS") or "90")

    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    body = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an MSSP SOC writing assistant. Rewrite technical alerts into "
                    "clear customer-safe English. Never invent product/engine brand names "
                    "(no Wazuh, Suricata, etc.). Never invent facts not present in the input. "
                    "Respond with JSON only, keys: plain_summary, likely_attack_type, "
                    "business_impact, recommended_action."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    content = (
        (((payload.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    ).strip()
    if not content:
        raise RuntimeError("empty LLM content")

    # Tolerate markdown fences
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON was not an object")

    out = {
        "plain_summary": str(parsed.get("plain_summary") or "").strip()[:4000],
        "likely_attack_type": str(parsed.get("likely_attack_type") or "").strip()[:4000],
        "business_impact": str(parsed.get("business_impact") or "").strip()[:4000],
        "recommended_action": str(parsed.get("recommended_action") or "").strip()[:4000],
    }
    if not out["plain_summary"]:
        raise RuntimeError("LLM omitted plain_summary")
    return out


def build_prompt(row: Dict[str, Any]) -> str:
    parts = [
        f"Severity: {row.get('severity') or 'unknown'}",
        f"Title: {_redact(str(row.get('alert_title') or ''), 500)}",
        f"Description: {_redact(str(row.get('alert_description') or ''), 800)}",
        f"Technical notes: {_redact(str(row.get('ai_technical_summary') or ''), 800)}",
        f"Host: {_redact(str(row.get('destination_host') or ''), 200)}",
        f"Source tool (internal only, do not name to customer): {row.get('source_tool') or ''}",
        f"Raw excerpt: {_minimize_raw(row.get('raw_event'))}",
        "",
        "Write customer-facing fields only. Keep each field to 1–3 short sentences.",
    ]
    return "\n".join(parts)


def process_alert_job(*, alert_id: str, tenant_id: str) -> bool:
    """
    Load alert by id+tenant, call LLM if needed, COALESCE-fill empty/generic fields.
    Returns True if an update was applied (or already filled / skipped cleanly).
    """
    if not ai_alert_enabled():
        return False

    row = fetch_one(
        """
        SELECT id::text AS id, tenant_id::text AS tenant_id, severity, alert_title,
               alert_description, destination_host, source_tool, raw_event,
               ai_plain_summary, ai_technical_summary, ai_likely_attack_type,
               ai_business_impact, ai_recommended_action
        FROM security_alerts
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        LIMIT 1;
        """,
        (alert_id, tenant_id),
    )
    if not row:
        logger.info("AI alert job skipped — alert not found id=%s tenant=%s", alert_id, tenant_id)
        return False

    if not severity_meets_threshold(row.get("severity")):
        return False

    need_summary = _is_generic_summary(row.get("ai_plain_summary"))
    need_attack = not (row.get("ai_likely_attack_type") or "").strip()
    need_impact = not (row.get("ai_business_impact") or "").strip()
    need_action = not (row.get("ai_recommended_action") or "").strip()
    if not any((need_summary, need_attack, need_impact, need_action)):
        return True

    try:
        result = _call_openai_compatible(build_prompt(row))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI alert analysis failed id=%s: %s", alert_id, exc)
        return False

    # COALESCE empty only — never overwrite non-generic SOC text for summary
    new_summary = result["plain_summary"] if need_summary else None
    new_attack = result["likely_attack_type"] if need_attack else None
    new_impact = result["business_impact"] if need_impact else None
    new_action = result["recommended_action"] if need_action else None

    fetch_one_write(
        """
        UPDATE security_alerts
        SET
          ai_plain_summary = CASE
            WHEN %s::text IS NOT NULL AND (
              ai_plain_summary IS NULL OR btrim(ai_plain_summary) = ''
              OR lower(ai_plain_summary) LIKE 'soc is reviewing:%%'
            ) THEN %s::text
            ELSE ai_plain_summary
          END,
          ai_likely_attack_type = COALESCE(NULLIF(ai_likely_attack_type, ''), %s),
          ai_business_impact = COALESCE(NULLIF(ai_business_impact, ''), %s),
          ai_recommended_action = COALESCE(NULLIF(ai_recommended_action, ''), %s),
          updated_at = now()
        WHERE id = %s::uuid AND tenant_id = %s::uuid
        RETURNING id::text AS id;
        """,
        (
            new_summary,
            new_summary,
            new_attack,
            new_impact,
            new_action,
            alert_id,
            tenant_id,
        ),
    )
    logger.info("AI alert analysis applied id=%s tenant=%s", alert_id, tenant_id)
    return True
