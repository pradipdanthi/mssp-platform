"""Durable Shuffle webhook queue (Redis) — replaces fire-and-forget threads."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

QUEUE_KEY = "mssp:shuffle:outbound"
DEAD_KEY = "mssp:shuffle:dead"
MAX_ATTEMPTS = int(os.getenv("SHUFFLE_RETRY_MAX_ATTEMPTS", "8"))
BASE_DELAY = float(os.getenv("SHUFFLE_RETRY_BASE_DELAY", "2"))

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
        logger.warning("Redis unavailable for Shuffle queue: %s", exc)
        return None


def enqueue_shuffle_post(
    *,
    url: str,
    body: bytes,
    content_type: str = "application/json",
    meta: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Enqueue a Shuffle webhook POST. Falls back to immediate POST if Redis is down.
    """
    item = {
        "url": url,
        "body_b64": __import__("base64").b64encode(body).decode("ascii"),
        "content_type": content_type,
        "attempts": 0,
        "meta": meta or {},
        "enqueued_at": time.time(),
    }
    client = _redis()
    if client is None:
        return _deliver_once(item)
    try:
        client.rpush(QUEUE_KEY, json.dumps(item))
        _ensure_worker()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Shuffle enqueue failed (%s); delivering inline", exc)
        return _deliver_once(item)


def _deliver_once(item: Dict[str, Any]) -> bool:
    import base64

    url = item["url"]
    body = base64.b64decode(item["body_b64"])
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": item.get("content_type") or "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            logger.info(
                "Shuffle delivery ok status=%s meta=%s",
                getattr(resp, "status", "?"),
                item.get("meta"),
            )
            return True
    except Exception:
        logger.exception("Shuffle delivery failed meta=%s", item.get("meta"))
        return False


def _worker_loop() -> None:
    while True:
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
            ok = _deliver_once(item)
            if ok:
                continue
            item["attempts"] = int(item.get("attempts") or 0) + 1
            if item["attempts"] >= MAX_ATTEMPTS:
                client.rpush(DEAD_KEY, json.dumps(item))
                logger.error("Shuffle message moved to dead letter after %s attempts", MAX_ATTEMPTS)
                continue
            delay = min(60.0, BASE_DELAY * (2 ** (item["attempts"] - 1)))
            time.sleep(delay)
            client.rpush(QUEUE_KEY, json.dumps(item))
        except Exception:
            logger.exception("Shuffle queue worker error")
            time.sleep(2)


def _ensure_worker() -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, name="shuffle-retry-worker", daemon=True)
        t.start()
        _worker_started = True
        logger.info("Shuffle durable retry worker started")


def start_shuffle_retry_worker() -> None:
    """Call from FastAPI startup."""
    _ensure_worker()
