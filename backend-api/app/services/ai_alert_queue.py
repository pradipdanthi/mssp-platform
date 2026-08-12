"""KB-092: Redis queue + daemon worker for AI alert analysis."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from app.services.ai_alert_analysis import (
    ai_alert_enabled,
    process_alert_job,
    severity_meets_threshold,
)
from app.services.ai_soc_triage import ai_soc_triage_enabled, process_soc_triage_job

logger = logging.getLogger(__name__)

QUEUE_KEY = os.getenv("AI_ALERT_QUEUE_KEY", "mssp:ai:alert_analysis")
DEAD_KEY = f"{QUEUE_KEY}:dead"
MAX_ATTEMPTS = int(os.getenv("AI_ALERT_RETRY_MAX_ATTEMPTS", "4"))
BASE_DELAY = float(os.getenv("AI_ALERT_RETRY_BASE_DELAY", "2"))

_worker_started = False
_lock = threading.Lock()


def _redis():
    try:
        import redis  # type: ignore

        url = (os.getenv("REDIS_URL") or "").strip()
        if url:
            return redis.Redis.from_url(url, decode_responses=True)
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = (os.getenv("REDIS_PASSWORD") or "").strip() or None
        return redis.Redis(host=host, port=port, password=password, decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable for AI alert queue: %s", exc)
        return None


def _ai_pipeline_enabled() -> bool:
    return ai_alert_enabled() or ai_soc_triage_enabled()


def _run_ai_pipeline(alert_id: str, tenant_id: str) -> bool:
    """Explain (KB-092) then triage assist (KB-096). Soft-fail per stage."""
    ok_any = False
    if ai_alert_enabled():
        try:
            ok_any = bool(process_alert_job(alert_id=alert_id, tenant_id=tenant_id)) or ok_any
        except Exception:  # noqa: BLE001
            logger.exception("AI explain stage failed id=%s", alert_id)
    if ai_soc_triage_enabled():
        try:
            ok_any = bool(process_soc_triage_job(alert_id=alert_id, tenant_id=tenant_id)) or ok_any
        except Exception:  # noqa: BLE001
            logger.exception("AI SOC triage stage failed id=%s", alert_id)
    return ok_any


def enqueue_ai_alert_analysis(
    *,
    alert_id: str,
    tenant_id: str,
    severity: Optional[str] = None,
) -> bool:
    """
    Queue an alert for LLM plain-English fill and optional SOC triage assist.
    No-op when both AI workers are disabled or severity below threshold.
    """
    if not _ai_pipeline_enabled():
        return False
    if severity is not None and not severity_meets_threshold(severity):
        return False
    if not alert_id or not tenant_id:
        return False

    item: Dict[str, Any] = {
        "alert_id": str(alert_id),
        "tenant_id": str(tenant_id),
        "attempts": 0,
        "enqueued_at": time.time(),
    }
    client = _redis()
    if client is None:
        # Best-effort inline when Redis is down
        try:
            return _run_ai_pipeline(item["alert_id"], item["tenant_id"])
        except Exception:  # noqa: BLE001
            logger.exception("Inline AI alert pipeline failed")
            return False
    try:
        client.rpush(QUEUE_KEY, json.dumps(item))
        _ensure_worker()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI alert enqueue failed (%s); trying inline", exc)
        try:
            return _run_ai_pipeline(item["alert_id"], item["tenant_id"])
        except Exception:  # noqa: BLE001
            logger.exception("Inline AI alert pipeline failed")
            return False


def _worker_loop() -> None:
    while True:
        if not _ai_pipeline_enabled():
            time.sleep(5)
            continue
        client = _redis()
        if client is None:
            time.sleep(5)
            continue
        try:
            raw = client.blpop(QUEUE_KEY, timeout=5)
            if not raw:
                continue
            _, payload = raw
            item = json.loads(payload)
            alert_id = str(item.get("alert_id") or "")
            tenant_id = str(item.get("tenant_id") or "")
            ok = False
            try:
                ok = _run_ai_pipeline(alert_id, tenant_id)
            except Exception:  # noqa: BLE001
                logger.exception("AI alert worker job error id=%s", alert_id)
                ok = False
            if ok:
                continue
            item["attempts"] = int(item.get("attempts") or 0) + 1
            if item["attempts"] >= MAX_ATTEMPTS:
                client.rpush(DEAD_KEY, json.dumps(item))
                logger.error(
                    "AI alert job moved to dead letter after %s attempts id=%s",
                    MAX_ATTEMPTS,
                    alert_id,
                )
                continue
            delay = min(60.0, BASE_DELAY * (2 ** (item["attempts"] - 1)))
            time.sleep(delay)
            client.rpush(QUEUE_KEY, json.dumps(item))
        except Exception:
            logger.exception("AI alert queue worker error")
            time.sleep(2)


def _ensure_worker() -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, name="ai-alert-analysis-worker", daemon=True)
        t.start()
        _worker_started = True
        logger.info("AI alert analysis worker started")


def start_ai_alert_worker() -> None:
    """Call from FastAPI startup when AI explain and/or SOC triage is enabled."""
    if _ai_pipeline_enabled():
        _ensure_worker()
        logger.info(
            "AI pipeline worker starting (explain=%s triage=%s)",
            ai_alert_enabled(),
            ai_soc_triage_enabled(),
        )
    else:
        logger.info(
            "AI pipeline worker not started (AI_ALERT_ENABLED=false, AI_SOC_TRIAGE_ENABLED=false)"
        )
