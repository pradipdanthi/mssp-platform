"""Appliance-local Tier-1 style triage gate before cloud SOC forward.

Calls localhost Ollama (native /api/chat + JSON schema). Fail-open by default:
AI outages never drop security events unless LOCAL_AI_FAIL_OPEN=false.

Does not require control-plane Postgres. Enrichment is limited to the alert
itself (no VT). Feature-flagged via ENABLE_LOCAL_AI_FILTER (default off).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from appliance.common import metadata_db

logger = logging.getLogger("kevantic.local-ai-filter")

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|token|secret|authorization|bearer)\s*[:=]\s*\S+"
)

VERDICTS = frozenset({"BENIGN_FALSE_POSITIVE", "SUSPICIOUS", "MALICIOUS"})
ACTIONS = frozenset({"AUTO_SUPPRESS", "INVESTIGATE_HOST", "ISOLATE_AGENT"})

SYSTEM_PROMPT = (
    "You are a Senior Cyber Threat Analyst specializing in Windows Security, "
    "Sysmon, and Enterprise Telemetry Triage.\n"
    "Your task is to analyze telemetry events and determine if an alert is "
    "benign administrative noise or genuine threat behavior.\n"
    "CRITICAL: You MUST evaluate Process Name, Path, Parent Process, "
    "CommandLine, and User context together.\n"
    "Never declare a process benign based on name alone if it executes from "
    "Temp, User Profile, or un-signed directories.\n"
    "GROUNDING RULES:\n"
    "- Base conclusions only on Telemetry provided. No external intel is available.\n"
    "- If signature status or hash reputation is unknown, say unknown — "
    "do NOT invent VirusTotal or reputation data.\n"
    "- recommended_action AUTO_SUPPRESS means suggest human-confirmed "
    "suppression only — never imply silent auto-close.\n"
    "- Prefer SUSPICIOUS when evidence is incomplete."
)

JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": sorted(VERDICTS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "recommended_action": {"type": "string", "enum": sorted(ACTIONS)},
        "suggested_suppression_scope": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "process_path": {"type": "string"},
                "justification": {"type": "string"},
            },
            "required": ["rule_id", "process_path", "justification"],
        },
    },
    "required": [
        "verdict",
        "confidence",
        "summary",
        "recommended_action",
        "suggested_suppression_scope",
    ],
}

# Suppress only high-confidence BENIGN; escalate suspicious/malicious or high conf non-benign.
DEFAULT_SUPPRESS_CONFIDENCE = 85.0
DEFAULT_ESCALATE_CONFIDENCE = 70.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_NUM_THREAD_LAB = 4
DEFAULT_NUM_THREAD_PROD = 6
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_KEEP_ALIVE = "-1"
DEFAULT_CACHE_TTL_SECONDS = 86400

AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS local_ai_triage_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  external_alert_id TEXT,
  rule_id TEXT,
  rule_level INTEGER,
  verdict TEXT,
  confidence REAL,
  recommended_action TEXT,
  summary TEXT,
  decision TEXT NOT NULL,
  reason TEXT,
  model TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_local_ai_audit_created
  ON local_ai_triage_audit(created_at);
"""

CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS local_ai_triage_cache (
  content_hash TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  confidence REAL NOT NULL,
  summary TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  model TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_local_ai_cache_created
  ON local_ai_triage_cache(created_at);
"""


def _env(*keys: str, default: str = "") -> str:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return default


def _env_bool(*keys: str, default: bool = False) -> bool:
    raw = _env(*keys, default="")
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_float(*keys: str, default: float) -> float:
    raw = _env(*keys, default="")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(*keys: str, default: int) -> int:
    raw = _env(*keys, default="")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def is_enabled() -> bool:
    return _env_bool(
        "ENABLE_LOCAL_AI_FILTER",
        "KEVANTIC_LOCAL_AI_FILTER_ENABLED",
        "JUNEXIS_LOCAL_AI_FILTER_ENABLED",
        default=False,
    )


def fail_open() -> bool:
    # Default fail-open: forward on AI outage unless operator sets false.
    return _env_bool(
        "LOCAL_AI_FAIL_OPEN",
        "KEVANTIC_LOCAL_AI_FAIL_OPEN",
        "JUNEXIS_LOCAL_AI_FAIL_OPEN",
        default=True,
    )


def _ollama_url() -> str:
    return _env(
        "OLLAMA_URL",
        "KEVANTIC_OLLAMA_URL",
        "JUNEXIS_OLLAMA_URL",
        default=DEFAULT_OLLAMA_URL,
    ).rstrip("/")


def _model() -> str:
    return _env(
        "LOCAL_AI_MODEL",
        "KEVANTIC_LOCAL_AI_MODEL",
        "JUNEXIS_LOCAL_AI_MODEL",
        default=DEFAULT_MODEL,
    )


def _timeout_seconds() -> float:
    val = _env_float(
        "LOCAL_AI_TIMEOUT_SECONDS",
        "KEVANTIC_LOCAL_AI_TIMEOUT_SECONDS",
        "JUNEXIS_LOCAL_AI_TIMEOUT_SECONDS",
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    return max(5.0, min(val, 180.0))


def _num_thread() -> int:
    """Thread budget for Ollama inference — prefer OLLAMA_CPU_THREADS (systemd profile)."""
    raw = _env(
        "OLLAMA_CPU_THREADS",
        "LOCAL_AI_NUM_THREAD",
        "KEVANTIC_LOCAL_AI_NUM_THREAD",
        "JUNEXIS_LOCAL_AI_NUM_THREAD",
        default="",
    )
    if not raw:
        profile = _env(
            "KEVANTIC_APPLIANCE_PROFILE",
            "KEVANTIC_DEPLOY_PROFILE",
            default="lab",
        ).lower()
        raw = str(DEFAULT_NUM_THREAD_PROD if profile in {"prod", "production"} else DEFAULT_NUM_THREAD_LAB)
    try:
        val = int(raw)
    except ValueError:
        val = DEFAULT_NUM_THREAD_LAB
    return max(1, min(val, 32))


def _keep_alive() -> str:
    return _env(
        "OLLAMA_KEEP_ALIVE",
        "KEVANTIC_OLLAMA_KEEP_ALIVE",
        "JUNEXIS_OLLAMA_KEEP_ALIVE",
        default=DEFAULT_KEEP_ALIVE,
    )


def _cache_enabled() -> bool:
    return _env_bool(
        "LOCAL_AI_CACHE_ENABLED",
        "KEVANTIC_LOCAL_AI_CACHE_ENABLED",
        default=True,
    )


def _cache_ttl_seconds() -> int:
    val = _env_int(
        "LOCAL_AI_CACHE_TTL_SECONDS",
        "KEVANTIC_LOCAL_AI_CACHE_TTL_SECONDS",
        default=DEFAULT_CACHE_TTL_SECONDS,
    )
    return max(60, min(val, 604800))


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ensure_cache_table(db: sqlite3.Connection) -> None:
    db.executescript(CACHE_TABLE)


def _load_cached_triage(content_hash: str) -> Optional[dict[str, Any]]:
    if not _cache_enabled():
        return None
    ttl = _cache_ttl_seconds()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl)).isoformat()
    try:
        with metadata_db.connect() as db:
            _ensure_cache_table(db)
            row = db.execute(
                """
                SELECT verdict, confidence, summary, recommended_action, scope_json, model
                FROM local_ai_triage_cache
                WHERE content_hash = ? AND created_at >= ?
                """,
                (content_hash, cutoff),
            ).fetchone()
            if not row:
                return None
            scope = json.loads(row["scope_json"] or "{}")
            if not isinstance(scope, dict):
                scope = {}
            return {
                "verdict": row["verdict"],
                "confidence": float(row["confidence"]),
                "summary": row["summary"],
                "recommended_action": row["recommended_action"],
                "suggested_suppression_scope": scope,
                "_cache_hit": True,
                "_model": row["model"] or _model(),
            }
    except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError):
        logger.debug("local AI cache read failed", exc_info=True)
        return None


def _store_cached_triage(content_hash: str, triage: dict[str, Any], model: str) -> None:
    if not _cache_enabled():
        return
    try:
        scope = triage.get("suggested_suppression_scope") or {}
        with metadata_db.connect() as db:
            _ensure_cache_table(db)
            db.execute(
                """
                INSERT INTO local_ai_triage_cache (
                  content_hash, verdict, confidence, summary,
                  recommended_action, scope_json, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_hash) DO UPDATE SET
                  verdict = excluded.verdict,
                  confidence = excluded.confidence,
                  summary = excluded.summary,
                  recommended_action = excluded.recommended_action,
                  scope_json = excluded.scope_json,
                  model = excluded.model,
                  created_at = excluded.created_at
                """,
                (
                    content_hash,
                    triage["verdict"],
                    float(triage["confidence"]),
                    triage["summary"],
                    triage["recommended_action"],
                    json.dumps(scope, default=str),
                    model[:128],
                    metadata_db.utc_now(),
                ),
            )
            db.commit()
    except sqlite3.Error:
        logger.debug("local AI cache write failed", exc_info=True)


def _suppress_confidence() -> float:
    return max(
        50.0,
        min(
            100.0,
            _env_float(
                "LOCAL_AI_SUPPRESS_CONFIDENCE",
                "KEVANTIC_LOCAL_AI_SUPPRESS_CONFIDENCE",
                default=DEFAULT_SUPPRESS_CONFIDENCE,
            ),
        ),
    )


def _escalate_confidence() -> float:
    return max(
        50.0,
        min(
            100.0,
            _env_float(
                "LOCAL_AI_ESCALATE_CONFIDENCE",
                "KEVANTIC_LOCAL_AI_ESCALATE_CONFIDENCE",
                default=DEFAULT_ESCALATE_CONFIDENCE,
            ),
        ),
    )


def _redact(text: str, limit: int = 2000) -> str:
    cleaned = _SECRET_RE.sub(r"\1=[REDACTED]", text or "")
    cleaned = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "[REDACTED_TOKEN]", cleaned)
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _rule_level(event: dict[str, Any]) -> int:
    rule = event.get("rule") if isinstance(event.get("rule"), dict) else {}
    try:
        return int(rule.get("level") or event.get("level") or 0)
    except (TypeError, ValueError):
        return 0


def _severity_bucket(event: dict[str, Any]) -> str:
    lvl = _rule_level(event)
    if lvl >= 12:
        return "critical"
    if lvl >= 10:
        return "high"
    if lvl >= 7:
        return "medium"
    return "low"


def _extract_process_fields(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    ed = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    syscheck = event.get("syscheck") if isinstance(event.get("syscheck"), dict) else {}
    agent = event.get("agent") if isinstance(event.get("agent"), dict) else {}
    rule = event.get("rule") if isinstance(event.get("rule"), dict) else {}

    image = (
        ed.get("Image")
        or data.get("process_name")
        or data.get("image")
        or syscheck.get("path")
        or ""
    )
    parent = ed.get("ParentImage") or data.get("parent_image") or ""
    cmdline = ed.get("CommandLine") or data.get("command") or data.get("cmdline") or ""
    user = (
        ed.get("User")
        or ed.get("TargetUserName")
        or ed.get("SubjectUserName")
        or data.get("srcuser")
        or ""
    )
    return {
        "rule_id": str(rule.get("id") or ""),
        "rule_description": str(rule.get("description") or "")[:500],
        "rule_level": _rule_level(event),
        "severity": _severity_bucket(event),
        "agent_name": str(agent.get("name") or "")[:255],
        "process_path": str(image)[:1024],
        "parent_path": str(parent)[:1024],
        "cmdline": str(cmdline)[:1500],
        "user": str(user)[:255],
        "location": str(event.get("location") or "")[:255],
    }


def build_triage_payload(event: dict[str, Any]) -> dict[str, Any]:
    fields = _extract_process_fields(event)
    return {
        "process_name": os.path.basename(fields["process_path"].replace("\\", "/"))
        if fields["process_path"]
        else "",
        "process_path": fields["process_path"],
        "parent_process": os.path.basename(fields["parent_path"].replace("\\", "/"))
        if fields["parent_path"]
        else "",
        "parent_path": fields["parent_path"],
        "cmdline": fields["cmdline"],
        "user": fields["user"],
        "rule_id": fields["rule_id"],
        "rule_description": fields["rule_description"],
        "rule_level": fields["rule_level"],
        "severity": fields["severity"],
        "host": fields["agent_name"],
        "location": fields["location"],
    }


def build_user_prompt(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Analyze this telemetry alert and return structured triage JSON only.",
            "Evaluate Process Name, Path, Parent Process, CommandLine, and User together.",
            "Base conclusions on Telemetry only. Unknown means unknown.",
            "No VirusTotal / TI FACTS are available on this appliance.",
            "",
            "Telemetry:",
            _redact(json.dumps(payload, default=str, indent=2), 2800),
        ]
    )


def _normalize_result(parsed: dict[str, Any], fallback_rule: str = "") -> dict[str, Any]:
    verdict = str(parsed.get("verdict") or "").strip().upper()
    if verdict not in VERDICTS:
        verdict = "SUSPICIOUS"
    try:
        confidence = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        confidence = 50.0
    confidence = max(0.0, min(100.0, confidence))
    action = str(parsed.get("recommended_action") or "").strip().upper()
    if action not in ACTIONS:
        action = "INVESTIGATE_HOST"
    summary = str(parsed.get("summary") or "").strip()[:2000]
    if not summary:
        summary = "Appliance local AI triage completed without a detailed summary."
    scope_raw = parsed.get("suggested_suppression_scope") or {}
    if not isinstance(scope_raw, dict):
        scope_raw = {}
    scope = {
        "rule_id": str(scope_raw.get("rule_id") or fallback_rule or "")[:512],
        "process_path": str(scope_raw.get("process_path") or "")[:1024],
        "justification": str(scope_raw.get("justification") or summary)[:2000],
    }
    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "recommended_action": action,
        "suggested_suppression_scope": scope,
    }


def call_ollama_chat(user_prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _ollama_url()
    model = _model()
    timeout = _timeout_seconds()
    url = f"{root}/api/chat"
    body = {
        "model": model,
        "stream": False,
        "format": JSON_SCHEMA,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "num_thread": _num_thread(),
            "temperature": 0.1,
            "num_predict": 280,
        },
        "keep_alive": _keep_alive(),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "kevantic-local-ai-filter/1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except TimeoutError as exc:
        raise TimeoutError(f"Ollama triage timed out after {timeout:.0f}s") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or "timed out" in str(exc).lower():
            raise TimeoutError(f"Ollama triage timed out after {timeout:.0f}s") from exc
        raise RuntimeError(f"Ollama unreachable: {exc}") from exc

    content = ((raw.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty Ollama triage content")
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama JSON was not an object")
    return parsed, {"model": model, "ollama_raw": raw}


def _should_hold(triage: dict[str, Any], event: dict[str, Any]) -> tuple[bool, str]:
    """Return (hold, reason). Hold = do not forward to cloud SOC."""
    verdict = triage["verdict"]
    confidence = float(triage["confidence"])
    severity = _severity_bucket(event)
    level = _rule_level(event)

    # Always escalate critical / very high Wazuh levels regardless of BENIGN.
    if severity == "critical" or level >= 12:
        return False, "severity_critical_always_forward"

    if verdict in {"MALICIOUS", "SUSPICIOUS"}:
        return False, f"verdict_{verdict.lower()}"

    if verdict != "BENIGN_FALSE_POSITIVE":
        # Unknown / unexpected → forward
        return False, "non_benign_forward"

    # BENIGN_FALSE_POSITIVE
    if confidence < _suppress_confidence():
        return False, "benign_confidence_too_low"

    # High confidence benign — still escalate if confidence on "non-benign
    # pressure" is high is N/A here; we hold.
    # If escalate threshold would contradict (high conf but not benign) —
    # already handled above.
    _ = _escalate_confidence()  # documented for operators; used when extending
    return True, "benign_high_confidence_hold"


def _audit(
    *,
    event: dict[str, Any],
    triage: Optional[dict[str, Any]],
    decision: str,
    reason: str,
    model: str = "",
    error: str = "",
) -> None:
    fields = _extract_process_fields(event)
    external_id = str(
        event.get("id") or event.get("uuid") or event.get("timestamp") or ""
    )[:255]
    try:
        with metadata_db.connect() as db:
            db.executescript(AUDIT_TABLE)
            db.execute(
                """
                INSERT INTO local_ai_triage_audit (
                  created_at, external_alert_id, rule_id, rule_level,
                  verdict, confidence, recommended_action, summary,
                  decision, reason, model, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata_db.utc_now(),
                    external_id,
                    fields["rule_id"],
                    fields["rule_level"],
                    (triage or {}).get("verdict"),
                    (triage or {}).get("confidence"),
                    (triage or {}).get("recommended_action"),
                    ((triage or {}).get("summary") or "")[:2000],
                    decision,
                    reason[:500],
                    model[:128],
                    error[:1000],
                ),
            )
            db.commit()
    except sqlite3.Error:
        logger.exception("failed to write local AI triage audit row")


def classify(event: dict[str, Any]) -> dict[str, Any]:
    """
    Classify one alert for forward-path gating.

    Returns:
      {
        "enabled": bool,
        "forward": bool,          # True → send to cloud SOC
        "held": bool,             # True → keep local only (or low-priority metadata)
        "fail_open_used": bool,
        "triage": dict|None,
        "reason": str,
        "error": str|None,
      }
    """
    if not is_enabled():
        return {
            "enabled": False,
            "forward": True,
            "held": False,
            "fail_open_used": False,
            "triage": None,
            "reason": "filter_disabled",
            "error": None,
        }

    payload = build_triage_payload(event)
    cache_key = _content_hash(payload)
    try:
        cached = _load_cached_triage(cache_key)
        if cached:
            triage = {k: v for k, v in cached.items() if not str(k).startswith("_")}
            meta = {"model": cached.get("_model") or _model(), "cache_hit": True}
            logger.debug("local AI cache hit hash=%s", cache_key[:12])
        else:
            parsed, meta = call_ollama_chat(build_user_prompt(payload))
            triage = _normalize_result(parsed, fallback_rule=payload.get("rule_id") or "")
            meta = dict(meta)
            meta["cache_hit"] = False
            _store_cached_triage(cache_key, triage, str(meta.get("model") or _model()))
        hold, reason = _should_hold(triage, event)
        decision = "hold" if hold else "forward"
        _audit(
            event=event,
            triage=triage,
            decision=decision,
            reason=reason,
            model=str(meta.get("model") or ""),
        )
        return {
            "enabled": True,
            "forward": not hold,
            "held": hold,
            "fail_open_used": False,
            "triage": triage,
            "reason": reason,
            "error": None,
            "model": meta.get("model"),
            "cache_hit": bool(meta.get("cache_hit")),
        }
    except Exception as exc:  # noqa: BLE001 — fail-open/closed policy
        err = str(exc)
        logger.warning("local AI triage failed: %s", err)
        if fail_open():
            _audit(
                event=event,
                triage=None,
                decision="forward",
                reason="ai_failure_fail_open",
                error=err,
            )
            return {
                "enabled": True,
                "forward": True,
                "held": False,
                "fail_open_used": True,
                "triage": None,
                "reason": "ai_failure_fail_open",
                "error": err,
            }
        _audit(
            event=event,
            triage=None,
            decision="hold",
            reason="ai_failure_fail_closed",
            error=err,
        )
        return {
            "enabled": True,
            "forward": False,
            "held": True,
            "fail_open_used": False,
            "triage": None,
            "reason": "ai_failure_fail_closed",
            "error": err,
        }


def attach_triage_to_event(event: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Annotate a copy of the event with appliance AI fields for cloud ingest."""
    out = dict(event)
    triage = result.get("triage")
    if not isinstance(triage, dict):
        return out
    out["appliance_ai"] = {
        "verdict": triage.get("verdict"),
        "confidence": triage.get("confidence"),
        "summary": triage.get("summary"),
        "recommended_action": triage.get("recommended_action"),
        "suggested_suppression_scope": triage.get("suggested_suppression_scope"),
        "reason": result.get("reason"),
        "model": result.get("model") or _model(),
        "filter": "local_ai_v1",
    }
    return out
