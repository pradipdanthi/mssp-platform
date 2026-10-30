"""Correlated latency tracing for TIA turns (chat, voice, tools, investigations).

Design rules
  * Durations use ``time.monotonic()`` (immune to clock steps). Wall-clock epoch values are
    recorded only so VMs can be lined up afterwards; cross-VM comparisons must apply the
    measured offset (see ``estimate_clock_offset``) and are only as good as that estimate.
  * A trace carries four correlation ids: request, conversation, turn and job. They travel
    to the SOC agent in ``X-Tia-*`` headers and come back in the agent's own timings.
  * Telemetry holds identifiers, path names, stage names and numbers. Never operator text,
    alert content, evidence, tokens or any other credential. Stage names are checked
    against an allow-list so free text cannot leak in by accident.
  * Recording is best effort and must never fail or slow a turn: errors are logged once
    per failure and swallowed.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from typing import Any, Deque, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

PATHS = ("navigation", "status", "connector", "model", "deep", "action")

# Server-side stages (fixed vocabulary).
SERVER_STAGES = frozenset(
    {
        "auth_and_context",       # token validation + conversation load
        "intent",                 # deterministic routing
        "db_query",               # structured platform queries
        "snapshot",               # legacy operator snapshot (engine wall + Proxmox cache)
        "connector_probe",        # live engine checks
        "queue_wait",             # time a job waited before a worker took it
        "agent_connect",          # TCP/TLS setup to the SOC agent
        "agent_total",            # request to agent until the reply was read
        "agent_queue",            # time inside the agent before the CLI started
        "cli_spawn",              # process creation
        "cli_first_output",       # CLI start to first output byte (model first token proxy)
        "cli_total",              # CLI start to exit
        "tool_execution",         # tool handler time
        "persist",                # conversation/turn persistence
        "tts",                    # speech synthesis (server side)
        "total",
    }
)

# Browser-side stages, reported back by the dashboard.
CLIENT_STAGES = frozenset(
    {
        "eos_to_request",         # end of speech to the HTTP request being sent
        "transcription",          # audio upload to transcript
        "chat_roundtrip",         # request sent to response received
        "tts_roundtrip",          # speech request to audio bytes
        "first_audio",            # speech request to audible start
        "playback_buffering",     # audio bytes received to audible start
        "interrupt_to_stop",      # operator speech detected to playback stopped
        "action_ack",             # command received to dashboard acknowledged the case loaded
        "eos_to_first_audio",     # end of speech to first audible response
        "eos_to_answer_done",     # end of speech to completed answer text
    }
)

_RING: Deque[Dict[str, Any]] = deque(maxlen=1000)
_ring_lock = threading.Lock()
_persist_failed = False


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class Trace:
    def __init__(
        self,
        path: str = "model",
        *,
        request_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> None:
        self.path = path if path in PATHS else "model"
        self.request_id = (request_id or new_id())[:64]
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.job_id = job_id
        self.stages: Dict[str, float] = {}
        self.extra: Dict[str, Any] = {}
        self._t0 = time.monotonic()
        self.started_epoch_ms = int(time.time() * 1000)
        self.clock_offset_ms: Optional[float] = None
        self._finished = False

    # -- recording -------------------------------------------------------
    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.add(name, (time.monotonic() - start) * 1000.0)

    def add(self, name: str, ms: float) -> None:
        if name not in SERVER_STAGES:
            logger.debug("tia_trace: ignoring unknown stage %r", name)
            return
        self.stages[name] = round(self.stages.get(name, 0.0) + max(0.0, float(ms)), 2)

    def merge_agent(self, agent_timings: Optional[Dict[str, Any]], *, send_started: float, received: float) -> None:
        """Fold the SOC agent's own stage timings in and estimate the clock offset.

        ``send_started`` / ``received`` are this process's monotonic times around the HTTP
        call; the agent reports its wall clock at reply time, so the offset estimate assumes
        the reply was produced halfway through the return leg (NTP-style, error bounded by
        half the network round trip).
        """
        if not isinstance(agent_timings, dict):
            return
        for key in ("agent_queue", "cli_spawn", "cli_first_output", "cli_total"):
            val = agent_timings.get(key)
            if isinstance(val, (int, float)):
                self.add(key, float(val))
        epoch = agent_timings.get("agent_epoch_ms")
        if isinstance(epoch, (int, float)):
            rtt_ms = (received - send_started) * 1000.0
            local_mid = int(time.time() * 1000) - rtt_ms / 2.0
            self.clock_offset_ms = round(float(epoch) - local_mid, 2)

    def headers(self) -> Dict[str, str]:
        out = {"X-Tia-Request-Id": self.request_id}
        if self.conversation_id:
            out["X-Tia-Conversation-Id"] = str(self.conversation_id)
        if self.turn_id:
            out["X-Tia-Turn-Id"] = str(self.turn_id)
        if self.job_id:
            out["X-Tia-Job-Id"] = str(self.job_id)
        return out

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    # -- completion ------------------------------------------------------
    def finish(self, ok: bool = True) -> Dict[str, Any]:
        total = round(self.elapsed_ms(), 2)
        self.stages["total"] = total
        record = {
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "job_id": self.job_id,
            "path": self.path,
            "ok": bool(ok),
            "total_ms": total,
            "stages": dict(self.stages),
            "clock_offset_ms": self.clock_offset_ms,
            "started_epoch_ms": self.started_epoch_ms,
        }
        if not self._finished:
            self._finished = True
            with _ring_lock:
                _RING.append(record)
            _persist(record)
            logger.info(
                "tia_turn request=%s conversation=%s turn=%s path=%s ok=%s total_ms=%s stages=%s",
                self.request_id, self.conversation_id, self.turn_id, self.path, ok, total, self.stages,
            )
        return record


def _persist(record: Dict[str, Any]) -> None:
    global _persist_failed
    try:
        import json

        from app.db.session import execute

        execute(
            "INSERT INTO tia_turn_timings (request_id, conversation_id, turn_id, job_id, path, ok, total_ms, stages, clock_offset_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s);",
            (
                record["request_id"], record["conversation_id"], record["turn_id"], record["job_id"],
                record["path"], record["ok"], record["total_ms"], json.dumps(record["stages"]),
                record["clock_offset_ms"],
            ),
        )
        _persist_failed = False
    except Exception as exc:  # noqa: BLE001
        if not _persist_failed:
            logger.warning("tia_trace: timing not persisted (%s); in-memory ring only", type(exc).__name__)
        _persist_failed = True


def record_client_stages(request_id: str, stages: Dict[str, Any]) -> int:
    """Attach browser-measured stages to a stored turn. Unknown names and bad numbers are dropped."""
    import json

    from app.db.session import execute

    clean: Dict[str, float] = {}
    for name, value in (stages or {}).items():
        if name in CLIENT_STAGES and isinstance(value, (int, float)) and 0 <= float(value) <= 600000:
            clean[name] = round(float(value), 2)
    if not clean:
        return 0
    execute(
        "UPDATE tia_turn_timings SET client_stages = client_stages || %s::jsonb WHERE request_id = %s;",
        (json.dumps(clean), str(request_id)[:64]),
    )
    with _ring_lock:
        for rec in _RING:
            if rec["request_id"] == request_id:
                rec.setdefault("client_stages", {}).update(clean)
    return len(clean)


def recent(limit: int = 50) -> List[Dict[str, Any]]:
    with _ring_lock:
        return list(_RING)[-limit:]


def reset_ring() -> None:
    with _ring_lock:
        _RING.clear()


def summarize(window_minutes: int = 60, path: Optional[str] = None) -> Dict[str, Any]:
    """p50/p95 per path and per stage over a window, with sample sizes."""
    from app.db.session import fetch_all

    window_minutes = max(1, min(int(window_minutes), 7 * 24 * 60))
    rows = fetch_all(
        """
        SELECT path, count(*)::int AS n, count(*) FILTER (WHERE NOT ok)::int AS failed,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_ms,
               max(total_ms) AS max_ms
        FROM tia_turn_timings
        WHERE created_at > now() - make_interval(mins => %s) AND (%s::text IS NULL OR path = %s)
        GROUP BY path ORDER BY path;
        """,
        (window_minutes, path, path),
    )
    stage_rows = fetch_all(
        """
        SELECT t.path, s.key AS stage, count(*)::int AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (s.value)::numeric) AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY (s.value)::numeric) AS p95_ms
        FROM tia_turn_timings t, jsonb_each_text(t.stages) s
        WHERE t.created_at > now() - make_interval(mins => %s) AND (%s::text IS NULL OR t.path = %s)
        GROUP BY t.path, s.key ORDER BY t.path, p95_ms DESC;
        """,
        (window_minutes, path, path),
    )
    client_rows = fetch_all(
        """
        SELECT s.key AS stage, count(*)::int AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (s.value)::numeric) AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY (s.value)::numeric) AS p95_ms
        FROM tia_turn_timings t, jsonb_each_text(t.client_stages) s
        WHERE t.created_at > now() - make_interval(mins => %s) AND (%s::text IS NULL OR t.path = %s)
        GROUP BY s.key ORDER BY s.key;
        """,
        (window_minutes, path, path),
    )

    def clean(rs):
        return [{k: (round(float(v), 1) if k.endswith("_ms") and v is not None else v) for k, v in r.items()} for r in rs]

    return {
        "window_minutes": window_minutes,
        "paths": clean(rows),
        "server_stages": clean(stage_rows),
        "client_stages": clean(client_rows),
        "note": "Sample sizes are in n. Percentiles from n < 20 are indicative, not a target verification.",
    }
