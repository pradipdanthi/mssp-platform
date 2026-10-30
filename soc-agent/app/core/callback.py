"""Push expert triage results back to the MSSP control plane.

A result that cannot be delivered is never discarded. It is written to a local
spool and retried with backoff until the control plane accepts it, answers with a
permanent rejection (which is kept for inspection), or the entry expires.

Result acceptance, duplicate handling and tenant/job binding are decided by the
control plane; this module only delivers and retries. Every push carries the
attempt binding the control plane issued, so a late retry can be matched to the
exact attempt it answers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 4xx answers that mean "try again later"; every other 4xx is a permanent rejection.
_RETRYABLE_4XX = {408, 425, 429}
_SPOOL_MAX_AGE_SECONDS = 7 * 24 * 3600
_lock = threading.Lock()
_retry_thread_started = False


def callback_configured() -> bool:
    url = (os.environ.get("MSSP_CALLBACK_URL") or "").strip()
    token = (os.environ.get("MSSP_CALLBACK_TOKEN") or os.environ.get("SOC_AGENT_INGEST_TOKEN") or "").strip()
    return bool(url and token)


def _spool_dir() -> Path:
    base = os.environ.get("SOC_AGENT_CALLBACK_SPOOL") or os.path.join(
        os.environ.get("SOC_AGENT_DATA_DIR") or "data", "callback_spool"
    )
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def build_body(result: dict[str, Any], alert: dict[str, Any]) -> dict[str, Any] | None:
    alert_id = str(result.get("alert_id") or alert.get("alert_id") or "").strip()
    if not alert_id:
        return None
    raw = alert.get("raw") if isinstance(alert.get("raw"), dict) else {}
    binding = raw.get("tia") if isinstance(raw.get("tia"), dict) else {}
    llm = result.get("llm") if isinstance(result.get("llm"), dict) else None
    return {
        "alert_id": alert_id,
        "tenant_id": binding.get("tenant_id") or raw.get("tenant_id") or alert.get("tenant_id"),
        "tenant_short_code": alert.get("tenant"),
        # Binding issued by the control plane when it opened the attempt.
        "attempt_id": binding.get("attempt_id"),
        "job_id": binding.get("job_id"),
        "evidence_version": binding.get("evidence_version"),
        # ok is true only when a validated analysis completed.
        "ok": bool(result.get("ok")),
        "contract": result.get("contract"),
        "execution": result.get("execution"),
        "disposition": result.get("disposition"),
        "source_severity": result.get("source_severity"),
        "human_review": result.get("human_review"),
        "limited_evidence": result.get("limited_evidence"),
        "verdict": result.get("verdict"),
        "llm": llm,
        "action_package": llm.get("action_package") if llm else None,
        "dossier_id": result.get("dossier_id"),
        "llm_meta": result.get("llm_meta"),
    }


def _settings() -> tuple[str, str]:
    base = (os.environ.get("MSSP_CALLBACK_URL") or "").rstrip("/")
    token = (os.environ.get("MSSP_CALLBACK_TOKEN") or os.environ.get("SOC_AGENT_INGEST_TOKEN") or "").strip()
    return base, token


def _post(body: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Returns (outcome, response) where outcome is delivered | retry | rejected."""
    base, token = _settings()
    if not base or not token:
        return "retry", None
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{base}/api/v1/soc-agent/triage-result",
                json=body,
                headers={"Content-Type": "application/json", "X-Soc-Agent-Token": token},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MSSP callback failed: %s", type(exc).__name__)
        return "retry", None
    if r.status_code < 300:
        return "delivered", (r.json() if r.content else {"ok": True})
    logger.warning("MSSP callback HTTP %s: %s", r.status_code, r.text[:200])
    if r.status_code >= 500 or r.status_code in _RETRYABLE_4XX:
        return "retry", None
    return "rejected", None


def _spool_path(body: dict[str, Any]) -> Path:
    key = hashlib.sha256(
        json.dumps([body.get("attempt_id"), body.get("alert_id")], sort_keys=True).encode()
    ).hexdigest()[:32]
    return _spool_dir() / f"{key}.json"


def _spool(body: dict[str, Any], *, rejected: bool = False) -> None:
    path = _spool_path(body)
    if rejected:
        path = path.with_suffix(".rejected")  # kept for inspection; never retried
    entry = {"body": body, "first_failed_at": time.time(), "attempts": 1, "next_at": time.time() + 30}
    tmp = path.with_suffix(".tmp")
    with _lock:
        if path.exists():
            return
        tmp.write_text(json.dumps(entry), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)
    if not rejected:
        start_retry_thread()


def push_triage_result(result: dict[str, Any], alert: dict[str, Any]) -> dict[str, Any] | None:
    """POST /api/v1/soc-agent/triage-result. Never raises into the analyst path.

    Returns the control-plane response when delivered, else None; an undelivered
    result is spooled for retry (unless the control plane permanently rejected it).
    """
    if not callback_configured():
        return None
    body = build_body(result, alert)
    if body is None:
        return None
    outcome, response = _post(body)
    if outcome == "delivered":
        return response
    if outcome == "retry":
        _spool(body)
    elif outcome == "rejected":
        _spool(body, rejected=True)
    return None


def retry_spool_once(now: float | None = None) -> dict[str, int]:
    """One pass over the spool. Exposed for tests and for the retry thread."""
    now = time.time() if now is None else now
    counts = {"delivered": 0, "retry": 0, "rejected": 0, "expired": 0}
    for path in sorted(_spool_dir().glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if now - float(entry.get("first_failed_at") or now) > _SPOOL_MAX_AGE_SECONDS:
            path.rename(path.with_suffix(".expired"))
            counts["expired"] += 1
            continue
        if float(entry.get("next_at") or 0) > now:
            continue
        outcome, _ = _post(entry["body"])
        if outcome == "delivered":
            path.unlink(missing_ok=True)
            counts["delivered"] += 1
        elif outcome == "rejected":
            # Kept for inspection; retrying cannot help.
            path.rename(path.with_suffix(".rejected"))
            counts["rejected"] += 1
        else:
            entry["attempts"] = int(entry.get("attempts") or 1) + 1
            entry["next_at"] = now + min(900, 30 * (2 ** min(entry["attempts"], 5)))
            path.write_text(json.dumps(entry), encoding="utf-8")
            counts["retry"] += 1
    return counts


def spool_depth() -> int:
    return len(list(_spool_dir().glob("*.json")))


def _retry_loop() -> None:
    while True:
        try:
            retry_spool_once()
        except Exception:  # noqa: BLE001
            logger.exception("callback spool retry failed")
        time.sleep(30)


def start_retry_thread() -> None:
    global _retry_thread_started
    with _lock:
        if _retry_thread_started:
            return
        threading.Thread(target=_retry_loop, name="callback-spool", daemon=True).start()
        _retry_thread_started = True
