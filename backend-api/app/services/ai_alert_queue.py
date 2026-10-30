"""KB-092: Redis queue + daemon worker for AI alert analysis."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import psycopg

from app.services.tia_schema import SchemaNotReady
from app.services.ai_alert_analysis import (
    ai_alert_enabled,
    process_alert_job,
    severity_meets_threshold,
)
from app.services.ai_deep_triage import deep_triage_enabled, process_deep_triage_job
from app.services.ai_soc_triage import ai_soc_triage_enabled, process_soc_triage_job
from app.services.soc_agent_client import soc_agent_enabled

logger = logging.getLogger(__name__)

QUEUE_KEY = os.getenv("AI_ALERT_QUEUE_KEY", "mssp:ai:alert_analysis")
DEAD_KEY = f"{QUEUE_KEY}:dead"
MAX_ATTEMPTS = int(os.getenv("AI_ALERT_RETRY_MAX_ATTEMPTS", "4"))
BASE_DELAY = float(os.getenv("AI_ALERT_RETRY_BASE_DELAY", "2"))

_worker_started = False
_lock = threading.Lock()
_ctx = threading.local()

# Only jobs that died because the database/schema was unavailable are re-queued
# automatically: nothing was lost, and a retry is certain to help once it returns.
RECOVERABLE_DEAD_REASONS = frozenset({"schema_not_ready", "database_error"})
MAX_DEAD_REQUEUES = int(os.getenv("TIA_DEADLETTER_MAX_REQUEUES", "5"))


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
    return (
        ai_alert_enabled()
        or ai_soc_triage_enabled()
        or deep_triage_enabled()
        or soc_agent_enabled()
    )


def _run_ai_pipeline(alert_id: str, tenant_id: str) -> bool:
    """Explain (KB-092), triage assist (KB-096), deep triage + escalation (KB-116).

    Soft-fail per stage so one unhealthy stage never blocks the others.
    """
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
    deep_ok = True
    _ctx.reason = None
    # Operator-queued jobs use SOC_AGENT_ENABLED even when the local Ollama
    # deep-triage flag is off. Skipping this stage left those jobs dead-lettered
    # with no investigation and no ticket note.
    investigate = deep_triage_enabled() or soc_agent_enabled()
    if investigate:
        try:
            deep_ok = bool(process_deep_triage_job(alert_id=alert_id, tenant_id=tenant_id))
        except SchemaNotReady as exc:
            logger.error(
                "AI deep triage held: TIA schema not ready (missing=%s) id=%s — work stays queued",
                exc.missing,
                alert_id,
            )
            _ctx.reason = "schema_not_ready"
            deep_ok = False
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI deep triage stage failed id=%s", alert_id)
            _ctx.reason = "database_error" if isinstance(exc, psycopg.Error) else "job_failed"
            deep_ok = False
        ok_any = deep_ok or ok_any
    # The investigation stage owns the case. A success in an earlier descriptive
    # stage must not hide a failed or unrouted investigation: report not-ok so the
    # job is retried (bounded) and then dead-lettered with a review item.
    if investigate and not deep_ok:
        return False
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

    from app.services import tia_jobs

    if tia_jobs.schema_ready():
        # System of record: one committed row. A crash after this line cannot lose the job.
        try:
            tia_jobs.enqueue(alert_id=str(alert_id), tenant_id=str(tenant_id), severity=severity)
        except Exception:  # noqa: BLE001
            # Never run the pipeline inline here: that would report success for non-durable work.
            # The alert is already stored; the sweeper creates the job once the database recovers.
            logger.exception("AI alert enqueue FAILED alert=%s; the sweeper will pick it up", alert_id)
            return False
        _ensure_worker()
        return True

    # Migration 120 is not applied yet: degraded legacy path (readiness reports a fault).
    item: Dict[str, Any] = {
        "alert_id": str(alert_id),
        "tenant_id": str(tenant_id),
        "attempts": 0,
        "enqueued_at": time.time(),
    }
    client = _redis()
    if client is None:
        logger.error("AI alert enqueue FAILED alert=%s: no durable queue available (jobs schema missing, Redis down)", alert_id)
        return False
    try:
        client.rpush(QUEUE_KEY, json.dumps(item))
        _ensure_worker()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("AI alert enqueue FAILED alert=%s: %s", alert_id, type(exc).__name__)
        return False


def job_handler(alert_id: str, tenant_id: str) -> "tuple[bool, Optional[str]]":
    """Adapter for tia_jobs: run the pipeline and return (ok, failure category)."""
    ok = False
    _ctx.reason = None
    try:
        ok = _run_ai_pipeline(alert_id, tenant_id)
    except Exception:  # noqa: BLE001
        logger.exception("AI alert job error id=%s", alert_id)
        return False, "job_failed"
    if ok:
        # Verified-playbook evaluation: shadow-only unless a human recorded customer authorisation.
        from app.services import tia_playbooks

        tia_playbooks.run_for_alert(alert_id, tenant_id)
    return ok, (None if ok else (getattr(_ctx, "reason", None) or "job_failed"))


def dead_letter_count() -> int:
    """Dead jobs in the durable table plus anything left in the legacy Redis dead list."""
    total = 0
    from app.services import tia_jobs

    if tia_jobs.schema_ready():
        total += int(tia_jobs.stats().get("dead") or 0)
    client = _redis()
    if client is not None:
        try:
            total += int(client.llen(DEAD_KEY))
        except Exception:  # noqa: BLE001
            pass
    elif not tia_jobs.schema_ready():
        raise RuntimeError("no queue available")
    return total


def requeue_dead_letters(limit: int = 20) -> int:
    """Durable dead jobs plus the legacy Redis dead list (see _requeue_legacy_dead_letters)."""
    from app.services import tia_jobs

    moved = 0
    if tia_jobs.schema_ready():
        try:
            moved += tia_jobs.requeue_dead(limit)
        except Exception:  # noqa: BLE001
            logger.exception("durable dead-letter requeue failed")
    return moved + _requeue_legacy_dead_letters(limit)


def _requeue_legacy_dead_letters(limit: int = 20) -> int:
    """Return jobs that died only because the schema/database was down to the queue.

    Called by the outbox worker once the schema is ready again. Bounded per tick
    and per job (``requeues``) so a job that keeps failing cannot loop forever;
    the rest stay in the dead-letter list and are reported by readiness.
    """
    client = _redis()
    if client is None:
        return 0
    moved = 0
    for raw in client.lrange(DEAD_KEY, 0, 199):
        if moved >= limit:
            break
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if item.get("dead_reason") not in RECOVERABLE_DEAD_REASONS:
            continue
        if int(item.get("requeues") or 0) >= MAX_DEAD_REQUEUES:
            continue
        if client.lrem(DEAD_KEY, 1, raw) < 1:
            continue
        item["requeues"] = int(item.get("requeues") or 0) + 1
        item["attempts"] = 0
        item.pop("dead_reason", None)
        client.rpush(QUEUE_KEY, json.dumps(item))
        moved += 1
    if moved:
        logger.warning("Re-queued %s dead-lettered investigation job(s) after recovery", moved)
        _ensure_worker()
    return moved


def _review_for_dead_letter(alert_id: str, tenant_id: str, attempts: int) -> None:
    """A dead-lettered job must still be visible to an analyst. Best effort, logged."""
    try:
        from app.services.ai_deep_triage import record_dead_letter_review

        record_dead_letter_review(alert_id=alert_id, tenant_id=tenant_id, attempts=attempts)
    except Exception:  # noqa: BLE001
        logger.exception("Dead-letter review item could not be recorded id=%s", alert_id)


def _worker_loop() -> None:
    while True:
        if not _ai_pipeline_enabled():
            time.sleep(5)
            continue
        from app.services import tia_jobs

        if tia_jobs.schema_ready():
            # Migration 120 was applied after this process started: switch to the durable workers.
            tia_jobs.start_workers(job_handler)
            logger.warning("AI alert queue: durable job workers took over from the legacy Redis loop")
            return
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
                item["dead_reason"] = getattr(_ctx, "reason", None) or "job_failed"
                client.rpush(DEAD_KEY, json.dumps(item))
                if item["dead_reason"] not in RECOVERABLE_DEAD_REASONS:
                    _review_for_dead_letter(alert_id, tenant_id, item["attempts"])
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
        from app.services import tia_jobs

        if tia_jobs.schema_ready():
            tia_jobs.start_workers(job_handler)
            _worker_started = True
            return
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, name="ai-alert-analysis-worker", daemon=True)
        t.start()
        _worker_started = True
        logger.error("AI alert analysis worker started on the LEGACY Redis path (migration 120 missing)")


def start_ai_alert_worker() -> None:
    """Call from FastAPI startup when AI explain and/or SOC triage is enabled."""
    if _ai_pipeline_enabled():
        _ensure_worker()
        from app.services import tia_jobs
        from app.services.tia_outbox import start_outbox_worker

        start_outbox_worker()
        logger.warning(
            "AI pipeline workers ready (explain=%s triage=%s deep=%s soc_agent=%s durable_workers=%s schema=%s)",
            ai_alert_enabled(),
            ai_soc_triage_enabled(),
            deep_triage_enabled(),
            soc_agent_enabled(),
            tia_jobs.alive_workers(),
            tia_jobs.schema_ready(),
        )
    else:
        logger.warning(
            "AI pipeline worker not started (AI_ALERT_ENABLED=false, "
            "AI_SOC_TRIAGE_ENABLED=false, AI_DEEP_TRIAGE_ENABLED=false, "
            "SOC_AGENT_ENABLED=false)"
        )
