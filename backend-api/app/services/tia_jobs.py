"""Durable investigation jobs (migration 120).

Why this exists
  The previous queue popped a job from a Redis list BEFORE processing it, slept inside the
  only worker thread when a job failed (so one failing job delayed every other tenant), and,
  when Redis was down, ran the whole pipeline inline inside the ingest request and reported
  success. A restart during analysis lost the job.

What this does instead
  * enqueue = one committed database row. Idempotent per (kind, alert).
  * claim = a time-limited lease taken with FOR UPDATE SKIP LOCKED; priority order
    (critical, high, other), per-tenant concurrency cap so one tenant cannot occupy every worker.
  * failure = reschedule with next_run_at (exponential backoff + jitter). Nothing sleeps, so
    other jobs keep moving. Infrastructure outages (schema/database) DEFER without consuming an
    attempt; ordinary failures consume bounded attempts and then dead-letter with a review item.
  * a worker that dies leaves an expired lease; recover_expired() makes the job claimable again.
    A worker that lost its lease cannot complete the job (the owner check fails).
  * a sweeper enqueues qualifying alerts that somehow have no job, attempt or review item, so
    every critical alert reaches a visible outcome.

Delivery is AT LEAST ONCE. The investigation is safe to repeat because each attempt is bound to
(alert, evidence version, attempt number) and results are immutable and unique per attempt
(tia_acceptance). This module does not, and must not be described as, providing exactly-once.
"""

from __future__ import annotations

import atexit
import logging
import os
import random
import socket
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import psycopg

logger = logging.getLogger(__name__)

KIND = "alert_analysis"
INFRASTRUCTURE_REASONS = frozenset({"schema_not_ready", "database_error"})

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
COUNTERS: Dict[str, int] = {
    "enqueued": 0, "claimed": 0, "succeeded": 0, "retried": 0, "deferred": 0,
    "dead": 0, "recovered_leases": 0, "lease_lost": 0, "swept": 0, "drained_legacy": 0,
}
_counter_lock = threading.Lock()


def _bump(name: str, n: int = 1) -> None:
    with _counter_lock:
        COUNTERS[name] = COUNTERS.get(name, 0) + n


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.getenv(name, str(default)))
    except ValueError:
        v = default
    return max(lo, min(v, hi))


def lease_seconds() -> int:
    return _int_env("TIA_JOB_LEASE_SECONDS", 900, 30, 7200)


def max_attempts() -> int:
    return _int_env("AI_ALERT_RETRY_MAX_ATTEMPTS", 4, 1, 20)


def tenant_cap() -> int:
    return _int_env("TIA_TENANT_MAX_RUNNING", 2, 1, 50)


def backoff_seconds(attempts: int) -> float:
    base = float(os.getenv("AI_ALERT_RETRY_BASE_DELAY", "2") or 2)
    return min(300.0, base * (2 ** max(0, attempts - 1))) * (0.8 + 0.4 * random.random())


def priority_for(severity: Optional[str]) -> int:
    s = (severity or "").strip().lower()
    return 0 if s == "critical" else 1 if s == "high" else 2


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

_schema_cache: Tuple[float, bool] = (0.0, False)


def schema_ready() -> bool:
    """True when migration 120 is present. Cached briefly; failures read as not ready."""
    global _schema_cache
    now = time.monotonic()
    if _schema_cache[0] and now - _schema_cache[0] < 15:
        return _schema_cache[1]
    ok = False
    try:
        from app.db.session import fetch_one

        ok = bool(fetch_one(
            "SELECT (to_regclass('public.tia_jobs') IS NOT NULL "
            "AND to_regclass('public.uq_tia_jobs_live') IS NOT NULL) AS ok;"
        ).get("ok")
        )
    except Exception:  # noqa: BLE001
        ok = False
    _schema_cache = (now, ok)
    return ok


def reset_schema_cache() -> None:
    global _schema_cache
    _schema_cache = (0.0, False)


# --------------------------------------------------------------------------
# queue operations
# --------------------------------------------------------------------------


def enqueue(*, alert_id: str, tenant_id: str, severity: Optional[str] = None, source: str = "ingest") -> Dict[str, Any]:
    """Commit a job row. Returns {job_id, created}. Raises on database failure (never silent)."""
    from app.db.session import db_transaction

    with db_transaction() as cur:
        cur.execute(
            """
            INSERT INTO tia_jobs (kind, tenant_id, alert_id, priority, max_attempts, source)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s)
            ON CONFLICT (kind, alert_id) WHERE state IN ('queued', 'running') DO NOTHING
            RETURNING id::text AS id;
            """,
            (KIND, tenant_id, alert_id, priority_for(severity), max_attempts(), source),
        )
        row = cur.fetchone()
        if row:
            _bump("enqueued")
            return {"job_id": row["id"], "created": True}
        cur.execute(
            "SELECT id::text AS id FROM tia_jobs WHERE kind = %s AND alert_id = %s::uuid AND state IN ('queued', 'running');",
            (KIND, alert_id),
        )
        existing = cur.fetchone()
    return {"job_id": existing["id"] if existing else None, "created": False}


def claim(worker_id: str = WORKER_ID) -> Optional[Dict[str, Any]]:
    from app.db.session import db_transaction

    with db_transaction() as cur:
        cur.execute(
            """
            WITH cand AS (
                SELECT j.id FROM tia_jobs j
                WHERE j.state = 'queued' AND j.next_run_at <= now()
                  AND (SELECT count(*) FROM tia_jobs r WHERE r.tenant_id = j.tenant_id AND r.state = 'running') < %s
                ORDER BY j.priority, j.next_run_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE tia_jobs t
               SET state = 'running', lease_owner = %s, lease_expires_at = now() + make_interval(secs => %s),
                   attempts = t.attempts + 1, started_at = coalesce(t.started_at, now()), updated_at = now()
              FROM cand
             WHERE t.id = cand.id
            RETURNING t.id::text AS id, t.alert_id::text AS alert_id, t.tenant_id::text AS tenant_id,
                      t.attempts, t.max_attempts, t.priority,
                      EXTRACT(EPOCH FROM (now() - t.created_at)) AS queue_age_s;
            """,
            (tenant_cap(), worker_id, lease_seconds()),
        )
        row = cur.fetchone()
    if row:
        _bump("claimed")
    return dict(row) if row else None


def heartbeat(job_id: str, worker_id: str = WORKER_ID) -> bool:
    from app.db.session import db_transaction

    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_jobs SET lease_expires_at = now() + make_interval(secs => %s), updated_at = now() "
            "WHERE id = %s::uuid AND lease_owner = %s AND state = 'running' RETURNING id;",
            (lease_seconds(), job_id, worker_id),
        )
        return cur.fetchone() is not None


def complete(job_id: str, worker_id: str = WORKER_ID) -> bool:
    from app.db.session import db_transaction

    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_jobs SET state = 'succeeded', completed_at = now(), lease_owner = NULL, lease_expires_at = NULL, "
            "last_error_category = NULL, updated_at = now() "
            "WHERE id = %s::uuid AND lease_owner = %s AND state = 'running' RETURNING id;",
            (job_id, worker_id),
        )
        done = cur.fetchone() is not None
    if done:
        _bump("succeeded")
    else:
        _bump("lease_lost")
        logger.warning("tia_jobs: completion ignored, lease for job %s was lost (effects are idempotent)", job_id)
    return done


def fail(job_id: str, category: str, worker_id: str = WORKER_ID) -> Dict[str, Any]:
    """Record a failed attempt. Returns {state, attempts, dead_reason}.

    Infrastructure categories defer without consuming the attempt. Other categories consume
    it; when attempts reach max_attempts the job dead-letters (and the caller records a review).
    """
    from app.db.session import db_transaction

    category = (category or "job_failed")[:60]
    infra = category in INFRASTRUCTURE_REASONS
    with db_transaction() as cur:
        cur.execute("SELECT attempts, max_attempts FROM tia_jobs WHERE id = %s::uuid AND lease_owner = %s AND state = 'running' FOR UPDATE;", (job_id, worker_id))
        row = cur.fetchone()
        if not row:
            _bump("lease_lost")
            return {"state": "lost", "attempts": None, "dead_reason": None}
        attempts, limit = int(row["attempts"]), int(row["max_attempts"])
        if infra:
            delay = min(60.0, 5.0 * (1 + random.random()))
            cur.execute(
                "UPDATE tia_jobs SET state = 'queued', attempts = GREATEST(attempts - 1, 0), next_run_at = now() + make_interval(secs => %s), "
                "lease_owner = NULL, lease_expires_at = NULL, last_error_category = %s, updated_at = now() WHERE id = %s::uuid;",
                (delay, category, job_id),
            )
            _bump("deferred")
            return {"state": "queued", "attempts": attempts - 1, "dead_reason": None, "deferred": True}
        if attempts >= limit:
            cur.execute(
                "UPDATE tia_jobs SET state = 'dead', dead_reason = %s, last_error_category = %s, completed_at = now(), "
                "lease_owner = NULL, lease_expires_at = NULL, updated_at = now() WHERE id = %s::uuid;",
                (category, category, job_id),
            )
            _bump("dead")
            return {"state": "dead", "attempts": attempts, "dead_reason": category}
        cur.execute(
            "UPDATE tia_jobs SET state = 'queued', next_run_at = now() + make_interval(secs => %s), lease_owner = NULL, "
            "lease_expires_at = NULL, last_error_category = %s, updated_at = now() WHERE id = %s::uuid;",
            (backoff_seconds(attempts), category, job_id),
        )
        _bump("retried")
        return {"state": "queued", "attempts": attempts, "dead_reason": None}


def release(job_id: str, worker_id: str = WORKER_ID) -> bool:
    """Graceful shutdown: hand a running job back without consuming the attempt."""
    from app.db.session import db_transaction

    with db_transaction() as cur:
        cur.execute(
            "UPDATE tia_jobs SET state = 'queued', attempts = GREATEST(attempts - 1, 0), next_run_at = now(), lease_owner = NULL, "
            "lease_expires_at = NULL, last_error_category = 'released_on_shutdown', updated_at = now() "
            "WHERE id = %s::uuid AND lease_owner = %s AND state = 'running' RETURNING id;",
            (job_id, worker_id),
        )
        return cur.fetchone() is not None


def recover_expired() -> List[Dict[str, Any]]:
    """Make jobs whose worker died claimable again; dead-letter those out of attempts."""
    from app.db.session import db_transaction

    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE tia_jobs
               SET state = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
                   dead_reason = CASE WHEN attempts >= max_attempts THEN 'lease_expired' ELSE dead_reason END,
                   completed_at = CASE WHEN attempts >= max_attempts THEN now() ELSE completed_at END,
                   last_error_category = 'lease_expired', next_run_at = now(),
                   lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
             WHERE state = 'running' AND lease_expires_at < now()
            RETURNING id::text AS id, alert_id::text AS alert_id, tenant_id::text AS tenant_id, state, attempts;
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    if rows:
        _bump("recovered_leases", len(rows))
        logger.warning("tia_jobs: recovered %s job(s) with expired leases", len(rows))
    return rows


def requeue_dead(limit: int = 20) -> int:
    """Return jobs that died only because of infrastructure to the queue (bounded per job)."""
    from app.db.session import db_transaction

    max_requeues = _int_env("TIA_DEADLETTER_MAX_REQUEUES", 5, 0, 50)
    with db_transaction() as cur:
        cur.execute(
            """
            UPDATE tia_jobs SET state = 'queued', attempts = 0, requeues = requeues + 1, next_run_at = now(),
                   dead_reason = NULL, completed_at = NULL, updated_at = now(), source = 'requeue'
             WHERE id IN (
                 SELECT id FROM tia_jobs
                  WHERE state = 'dead' AND dead_reason = ANY(%s) AND requeues < %s
                  ORDER BY priority, updated_at LIMIT %s FOR UPDATE SKIP LOCKED)
            RETURNING id;
            """,
            (list(INFRASTRUCTURE_REASONS), max_requeues, limit),
        )
        return len(cur.fetchall())


def _env_on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def sweep_missing(hours: int = 24, limit: int = 50) -> int:
    """Enqueue qualifying alerts that have no job, attempt or review item (nothing may be silently dropped).

    Off unless TIA_SWEEP_MISSING is explicitly enabled. A production cutover must not
    auto-queue the last 24 hours of high/critical alerts; operators enqueue one case.
    """
    if not _env_on("TIA_SWEEP_MISSING"):
        return 0
    from app.db.session import fetch_all
    from app.services.ai_alert_analysis import severity_meets_threshold

    rows = fetch_all(
        """
        SELECT sa.id::text AS id, sa.tenant_id::text AS tenant_id, sa.severity
        FROM security_alerts sa
        WHERE lower(sa.severity) IN ('critical', 'high')
          AND sa.status NOT IN ('closed', 'false_positive', 'resolved')
          AND sa.created_at > now() - make_interval(hours => %s)
          AND sa.created_at < now() - interval '2 minutes'
          AND NOT EXISTS (SELECT 1 FROM tia_jobs j WHERE j.alert_id = sa.id)
          AND NOT EXISTS (SELECT 1 FROM tia_investigation_attempts a WHERE a.alert_id = sa.id)
          AND NOT EXISTS (SELECT 1 FROM tia_review_items r WHERE r.alert_id = sa.id)
        ORDER BY CASE lower(sa.severity) WHEN 'critical' THEN 0 ELSE 1 END, sa.created_at
        LIMIT %s;
        """,
        (max(1, min(hours, 168)), limit),
    )
    n = 0
    for r in rows:
        if not severity_meets_threshold(r["severity"]):
            continue
        if enqueue(alert_id=r["id"], tenant_id=r["tenant_id"], severity=r["severity"], source="sweeper")["created"]:
            n += 1
    if n:
        _bump("swept", n)
        logger.warning("tia_jobs: sweeper enqueued %s alert(s) that had no investigation record", n)
    return n


def latest_for_alert(alert_id: str) -> Optional[Dict[str, Any]]:
    """Most recent job for this alert. Used by the conversation tool; never waits for the model."""
    from app.db.session import fetch_one

    return fetch_one(
        "SELECT id::text AS id, state, attempts, max_attempts, source, last_error_category, "
        "(created_at AT TIME ZONE 'utc')::text AS created_at, "
        "(started_at AT TIME ZONE 'utc')::text AS started_at, "
        "(completed_at AT TIME ZONE 'utc')::text AS completed_at "
        "FROM tia_jobs WHERE kind = %s AND alert_id = %s::uuid ORDER BY created_at DESC LIMIT 1;",
        (KIND, alert_id),
    ) or None


def stats() -> Dict[str, Any]:
    """Backlog, age, lease and dead-letter figures for readiness and metrics."""
    from app.db.session import fetch_one

    row = fetch_one(
        """
        SELECT
          count(*) FILTER (WHERE state = 'queued')::int AS queued,
          count(*) FILTER (WHERE state = 'queued' AND priority = 0)::int AS queued_critical,
          count(*) FILTER (WHERE state = 'queued' AND attempts > 0)::int AS retry_wait,
          count(*) FILTER (WHERE state = 'running')::int AS running,
          count(*) FILTER (WHERE state = 'running' AND lease_expires_at < now())::int AS expired_leases,
          count(*) FILTER (WHERE state = 'dead')::int AS dead,
          count(*) FILTER (WHERE state = 'dead' AND dead_reason = ANY(%s))::int AS dead_recoverable,
          coalesce(max(EXTRACT(EPOCH FROM (now() - next_run_at))) FILTER (WHERE state = 'queued' AND next_run_at <= now()), 0)::float AS oldest_ready_age_s,
          coalesce(max(EXTRACT(EPOCH FROM (now() - next_run_at))) FILTER (WHERE state = 'queued' AND priority = 0 AND next_run_at <= now()), 0)::float AS oldest_critical_age_s
        FROM tia_jobs;
        """,
        (list(INFRASTRUCTURE_REASONS),),
    ) or {}
    out = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in row.items()}
    out["workers_alive"] = alive_workers()
    out["counters"] = dict(COUNTERS)
    return out


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

Handler = Callable[[str, str], Tuple[bool, Optional[str]]]


def run_one(handler: Handler, worker_id: str = WORKER_ID) -> Optional[Dict[str, Any]]:
    """Claim and run one job. Returns a result dict, or None when nothing was ready."""
    job = claim(worker_id)
    if not job:
        return None
    stop = threading.Event()

    def beat() -> None:
        interval = max(10.0, lease_seconds() / 3.0)
        while not stop.wait(interval):
            try:
                if not heartbeat(job["id"], worker_id):
                    return
            except Exception:  # noqa: BLE001
                logger.warning("tia_jobs: heartbeat failed for %s", job["id"])

    hb = threading.Thread(target=beat, name=f"tia-job-hb-{job['id'][:8]}", daemon=True)
    hb.start()
    ok, category = False, "job_failed"
    try:
        ok, category = handler(job["alert_id"], job["tenant_id"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("tia_jobs: handler raised for job %s", job["id"])
        category = "database_error" if exc.__class__.__module__.startswith("psycopg") else "job_failed"
    finally:
        stop.set()
    if ok:
        complete(job["id"], worker_id)
        return {"job": job, "outcome": "succeeded"}
    res = fail(job["id"], category or "job_failed", worker_id)
    if res.get("state") == "dead":
        _record_dead_review(job)
    return {"job": job, "outcome": res.get("state"), "category": category}


def _record_dead_review(job: Dict[str, Any]) -> None:
    try:
        from app.services.ai_deep_triage import record_dead_letter_review

        record_dead_letter_review(alert_id=job["alert_id"], tenant_id=job["tenant_id"], attempts=int(job.get("attempts") or 0))
    except Exception:  # noqa: BLE001
        logger.exception("tia_jobs: dead-letter review could not be recorded for alert %s", job.get("alert_id"))


_threads: List[threading.Thread] = []
_stop = threading.Event()
_current: Dict[str, str] = {}
_start_lock = threading.Lock()


def alive_workers() -> int:
    return sum(1 for t in _threads if t.is_alive())


def _worker(handler: Handler, index: int) -> None:
    wid = f"{WORKER_ID}#{index}"
    idle = 0.0
    while not _stop.is_set():
        try:
            res = run_one(handler, wid)
        except Exception:  # noqa: BLE001
            logger.exception("tia_jobs: worker loop error")
            res = None
            _stop.wait(2.0)
        if res is None:
            idle = min(5.0, idle + 0.5)
            _stop.wait(max(0.5, idle))
        else:
            idle = 0.0


def _maintenance() -> None:
    last_sweep = 0.0
    while not _stop.wait(30.0):
        try:
            for row in recover_expired():
                if row.get("state") == "dead":
                    _record_dead_review(row)
            requeue_dead()
            drain_legacy_redis()
            if time.monotonic() - last_sweep > 120:
                last_sweep = time.monotonic()
                sweep_missing()
        except Exception:  # noqa: BLE001
            logger.exception("tia_jobs: maintenance pass failed")


def start_workers(handler: Handler) -> int:
    """Start worker and maintenance threads once. Returns the number of workers running."""
    with _start_lock:
        if _threads and alive_workers():
            return alive_workers()
        _stop.clear()
        _threads.clear()
        n = _int_env("TIA_WORKERS", 2, 1, 16)
        for i in range(n):
            t = threading.Thread(target=_worker, args=(handler, i), name=f"tia-job-worker-{i}", daemon=True)
            t.start()
            _threads.append(t)
        m = threading.Thread(target=_maintenance, name="tia-job-maintenance", daemon=True)
        m.start()
        _threads.append(m)
        atexit.register(shutdown)
        logger.info("tia_jobs: %s worker(s) and a maintenance thread started (id=%s)", n, WORKER_ID)
        return n


def shutdown(timeout: float = 20.0) -> None:
    """Graceful stop: stop claiming, wait for running handlers, then release anything still leased."""
    _stop.set()
    deadline = time.monotonic() + timeout
    for t in list(_threads):
        t.join(max(0.0, deadline - time.monotonic()))
    try:
        from app.db.session import db_transaction

        with db_transaction() as cur:
            cur.execute(
                "UPDATE tia_jobs SET state = 'queued', attempts = GREATEST(attempts - 1, 0), next_run_at = now(), lease_owner = NULL, "
                "lease_expires_at = NULL, last_error_category = 'released_on_shutdown', updated_at = now() "
                "WHERE state = 'running' AND lease_owner LIKE %s;",
                (f"{WORKER_ID}%",),
            )
    except Exception:  # noqa: BLE001
        logger.warning("tia_jobs: could not release leases on shutdown; they will expire and be recovered")


# --------------------------------------------------------------------------
# legacy Redis list (rollout compatibility)
# --------------------------------------------------------------------------


def drain_legacy_redis(limit: int = 100) -> int:
    """Move items from the old Redis list into durable jobs. An item is removed only after its
    job row is committed, so a crash in between can duplicate (idempotent) but never lose it."""
    import json

    from app.services import ai_alert_queue as q

    client = q._redis()
    if client is None:
        return 0
    moved = 0
    try:
        for raw in client.lrange(q.QUEUE_KEY, 0, limit - 1):
            try:
                item = json.loads(raw)
                alert_id, tenant_id = str(item["alert_id"]), str(item["tenant_id"])
            except (ValueError, KeyError):
                client.lrem(q.QUEUE_KEY, 1, raw)  # malformed entries can never succeed
                continue
            try:
                enqueue(alert_id=alert_id, tenant_id=tenant_id, source="legacy_redis")
            except psycopg.errors.ForeignKeyViolation:
                logger.warning("tia_jobs: dropping legacy queue item for a deleted alert/tenant (%s)", alert_id)
                client.lrem(q.QUEUE_KEY, 1, raw)
                continue
            client.lrem(q.QUEUE_KEY, 1, raw)
            moved += 1
    except Exception:  # noqa: BLE001
        logger.warning("tia_jobs: legacy Redis drain stopped early")
    if moved:
        _bump("drained_legacy", moved)
    return moved
