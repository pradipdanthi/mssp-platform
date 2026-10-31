"""KB-116: SOC escalation delivery worker.

Drains queued rows from `notification_events` and delivers them to the on-call
human. Provider-agnostic: the escalation decision in `ai_deep_triage` never
knows which channel is configured.

Adapters:
  whatsapp  -> Meta WhatsApp Cloud API (business-initiated template, or plain
               text inside an open 24h service window)
  telegram  -> Telegram Bot API (free; useful for lab validation before the
               WhatsApp Business number is approved)
  webhook   -> generic HTTP POST, for Slack/Teams/PagerDuty style endpoints

Delivery is at-least-once with bounded retries. Acknowledgement is recorded
separately when the analyst confirms, so an unacknowledged page can later be
escalated further (voice call) by policy.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one_write

logger = logging.getLogger(__name__)

_worker_started = False
_lock = threading.Lock()

DEFAULT_POLL_SECONDS = 10.0
DEFAULT_BATCH = 20


def _max_attempts() -> int:
    try:
        n = int(os.getenv("SOC_NOTIFIER_MAX_ATTEMPTS") or "4")
    except ValueError:
        n = 4
    return max(1, min(n, 20))


class NotifyError(RuntimeError):
    """Raised when a provider rejects or fails a delivery."""


def notifier_enabled() -> bool:
    return (os.getenv("SOC_NOTIFIER_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _http_post_json(
    url: str,
    payload: Dict[str, Any],
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        raise NotifyError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise NotifyError(str(exc)) from exc
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _send_whatsapp(recipient: str, message: str) -> str:
    """Meta WhatsApp Cloud API. Returns the provider message id."""
    token = (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip()
    phone_number_id = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    if not token or not phone_number_id:
        raise NotifyError(
            "WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID are not configured"
        )

    api_version = (os.getenv("WHATSAPP_API_VERSION") or "v21.0").strip()
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    to = recipient.lstrip("+").strip()

    template_name = (os.getenv("WHATSAPP_TEMPLATE_NAME") or "").strip()
    if template_name:
        # Business-initiated pages must use an approved template. The whole
        # escalation body is passed as a single body parameter.
        lang = (os.getenv("WHATSAPP_TEMPLATE_LANG") or "en").strip()
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": message[:1000]}],
                    }
                ],
            },
        }
    else:
        # Plain text only works inside an open 24h service window.
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message[:4000], "preview_url": False},
        }

    result = _http_post_json(
        url, payload, headers={"Authorization": f"Bearer {token}"}
    )
    messages = result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        return str(messages[0].get("id") or "")
    return ""


def _send_telegram(recipient: str, message: str) -> str:
    """Telegram Bot API. `recipient` is a chat id. Free, no approval needed."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise NotifyError("TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    result = _http_post_json(
        url, {"chat_id": recipient.strip(), "text": message[:4000]}
    )
    if not result.get("ok"):
        raise NotifyError(f"Telegram rejected the message: {result}")
    return str(((result.get("result") or {}).get("message_id")) or "")


def _send_webhook(recipient: str, message: str) -> str:
    """Generic webhook POST. `recipient` is the full destination URL."""
    # Lab local sink may use http://127.0.0.1 when explicitly allowed.
    allow_http = (os.getenv("SOC_NOTIFIER_ALLOW_HTTP_WEBHOOK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    lower = recipient.lower()
    if lower.startswith("https://"):
        pass
    elif allow_http and lower.startswith("http://127.0.0.1"):
        pass
    elif allow_http and lower.startswith("http://localhost"):
        pass
    else:
        raise NotifyError("Webhook recipient must be an https URL")
    _http_post_json(recipient, {"text": message})
    return ""


def _send_file(recipient: str, message: str) -> str:
    """Controlled local file sink for provider-independent escalation tests.

    `recipient` is an absolute path under SOC_NOTIFIER_FILE_SINK_DIR (default
    /var/cache/mssp/notify-sink). Never invents human acknowledgement.
    """
    from pathlib import Path
    import uuid

    sink_root = Path(
        (os.getenv("SOC_NOTIFIER_FILE_SINK_DIR") or "/var/cache/mssp/notify-sink").strip()
    )
    sink_root.mkdir(parents=True, exist_ok=True)
    # recipient may be a relative leaf name; reject path escape
    leaf = Path(recipient).name if recipient else "page.txt"
    if not leaf or leaf in (".", ".."):
        leaf = "page.txt"
    path = sink_root / f"{uuid.uuid4().hex}-{leaf}"
    path.write_text(message[:8000], encoding="utf-8")
    return str(path)


_ADAPTERS = {
    "whatsapp": _send_whatsapp,
    "telegram": _send_telegram,
    "webhook": _send_webhook,
    "file": _send_file,
}


def _provider_label(channel: str) -> str:
    return {
        "whatsapp": "meta_cloud_api",
        "telegram": "telegram_bot_api",
        "webhook": "http_webhook",
        "file": "local_file_sink",
    }.get(channel, channel)


def deliver_one(event: Dict[str, Any]) -> bool:
    """Deliver a single queued notification. Returns True when sent."""
    event_id = str(event.get("id"))
    channel = str(event.get("notification_type") or "").strip().lower()
    recipient = str(event.get("recipient_address") or "").strip()
    message = str(event.get("message_body") or "")

    adapter = _ADAPTERS.get(channel)
    if adapter is None:
        _mark_failed(event_id, f"no adapter for channel '{channel}'")
        return False
    if not recipient:
        _mark_failed(event_id, "empty recipient address")
        return False

    try:
        provider_message_id = adapter(recipient, message)
    except NotifyError as exc:
        logger.warning("SOC page delivery failed event=%s: %s", event_id, exc)
        _mark_failed(event_id, str(exc)[:500])
        return False
    except Exception as exc:  # noqa: BLE001
        logger.exception("SOC page delivery error event=%s", event_id)
        _mark_failed(event_id, str(exc)[:500])
        return False

    fetch_one_write(
        """
        UPDATE notification_events
        SET status = 'sent',
            sent_at = now(),
            provider = %s,
            provider_message_id = NULLIF(%s, ''),
            error_message = NULL
        WHERE id = %s::uuid
        RETURNING id::text AS id;
        """,
        (_provider_label(channel), provider_message_id or "", event_id),
    )
    logger.info(
        "SOC page delivered event=%s channel=%s provider_msg=%s",
        event_id,
        channel,
        provider_message_id or "-",
    )
    return True


def _mark_failed(event_id: str, error: str) -> None:
    """Increment attempts; keep queued until MAX_ATTEMPTS, then mark failed."""
    ceiling = _max_attempts()
    fetch_one_write(
        """
        UPDATE notification_events
        SET attempts = COALESCE(attempts, 0) + 1,
            error_message = %s,
            status = CASE
                WHEN COALESCE(attempts, 0) + 1 >= %s THEN 'failed'
                ELSE 'queued'
            END
        WHERE id = %s::uuid
        RETURNING id::text AS id;
        """,
        (error[:500], ceiling, event_id),
    )


def fetch_queued(limit: int = DEFAULT_BATCH) -> List[Dict[str, Any]]:
    ceiling = _max_attempts()
    return fetch_all(
        """
        SELECT id::text AS id,
               tenant_id::text AS tenant_id,
               alert_id::text AS alert_id,
               notification_type,
               recipient_name,
               recipient_address,
               message_body,
               COALESCE(attempts, 0)::int AS attempts
        FROM notification_events
        WHERE status = 'queued'
          AND COALESCE(attempts, 0) < %s
        ORDER BY created_at ASC
        LIMIT %s;
        """,
        (ceiling, limit),
    )


def drain_once(limit: int = DEFAULT_BATCH) -> int:
    """Deliver up to `limit` queued pages. Returns the number sent."""
    sent = 0
    for event in fetch_queued(limit):
        if deliver_one(event):
            sent += 1
    return sent


def acknowledge(event_id: str) -> bool:
    """Record analyst acknowledgement so escalation policy can stand down."""
    row = fetch_one_write(
        """
        UPDATE notification_events
        SET status = 'acknowledged', acknowledged_at = now()
        WHERE id = %s::uuid AND status IN ('sent', 'delivered', 'queued')
        RETURNING id::text AS id;
        """,
        (event_id,),
    )
    return bool(row)


def _poll_seconds() -> float:
    try:
        return float(os.getenv("SOC_NOTIFIER_POLL_SECONDS") or DEFAULT_POLL_SECONDS)
    except ValueError:
        return DEFAULT_POLL_SECONDS


def _worker_loop() -> None:
    while True:
        if not notifier_enabled():
            time.sleep(15)
            continue
        try:
            drain_once()
        except Exception:  # noqa: BLE001
            logger.exception("SOC notifier worker error")
        time.sleep(_poll_seconds())


def _ensure_worker() -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return
        thread = threading.Thread(
            target=_worker_loop, name="soc-escalation-notifier", daemon=True
        )
        thread.start()
        _worker_started = True
        logger.info("SOC escalation notifier worker started")


def start_soc_notifier() -> None:
    """Call from FastAPI startup alongside the AI alert worker."""
    if notifier_enabled():
        _ensure_worker()
        logger.info(
            "SOC notifier starting (channel default=%s)",
            os.getenv("SOC_ESCALATION_CHANNEL") or "whatsapp",
        )
    else:
        logger.info("SOC notifier not started (SOC_NOTIFIER_ENABLED=false)")
