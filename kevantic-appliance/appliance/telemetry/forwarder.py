"""Anonymizing edge telemetry forwarder with SQLite disk buffer + backoff."""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from appliance.common import metadata_db
from appliance.common.paths import ensure_engine_dirs, telemetry_url
from appliance.common.privacy import to_cloud_alert

logger = logging.getLogger(__name__)


def _env_first(*keys: str) -> str:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def _read_api_key_file() -> str:
    candidates = [
        os.environ.get("KEVANTIC_API_KEY_FILE"),
        os.environ.get("NIKTIAR_API_KEY_FILE"),
        os.environ.get("JUNEXIS_API_KEY_FILE"),
        "/var/lib/niktiar/secrets/appliance_api_key",
        "/var/lib/junexis/secrets/appliance_api_key",
        "/var/lib/kevantic/secrets/appliance_api_key",
    ]
    for path in candidates:
        if not path:
            continue
        try:
            text = Path(path).read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            continue
    return ""


def _parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _backoff_seconds(attempts: int) -> int:
    return min(3600, 2 ** max(0, attempts))


class TelemetryForwarder:
    """
    Strip PII and POST normalized alerts to control-plane telemetry ingest.
    On failure, buffer to SQLite and retry with exponential backoff.
    """

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        appliance_id: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        ensure_engine_dirs()
        self.url = url or telemetry_url()
        self.appliance_id = appliance_id or _env_first(
            "NIKTIAR_APPLIANCE_ID",
            "KEVANTIC_APPLIANCE_ID",
            "JUNEXIS_APPLIANCE_ID",
        )
        self.api_key = (
            api_key
            or _env_first(
                "NIKTIAR_APPLIANCE_API_KEY",
                "KEVANTIC_APPLIANCE_API_KEY",
                "JUNEXIS_APPLIANCE_API_KEY",
            )
            or _read_api_key_file()
        )
        self.timeout = timeout

    def forward_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = to_cloud_alert(event)
        return self._send_or_buffer(payload)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.appliance_id and self.api_key:
            h["X-Appliance-ID"] = self.appliance_id
            h["X-Appliance-API-Key"] = self.api_key
        return h

    def _http_post(self, payload: dict[str, Any]) -> tuple[int, str]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers=self._headers(), method="POST"
        )
        # HTTP lab URLs must not force TLS context.
        if str(self.url).startswith("https://"):
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return int(resp.status), body
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body

    def _send_or_buffer(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            status, body = self._http_post(payload)
            return {"ok": True, "status": status, "body": body[:500], "buffered": False}
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
        ) as exc:
            self._enqueue(payload, error=str(exc))
            logger.warning("telemetry send failed; buffered: %s", exc)
            return {"ok": False, "buffered": True, "error": str(exc)}

    def _enqueue(self, payload: dict[str, Any], *, error: str) -> None:
        now = metadata_db.utc_now()
        next_at = (
            datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(0))
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with metadata_db.connect() as db:
            db.execute(
                """
                INSERT INTO telemetry_buffer
                  (payload_json, attempts, next_attempt_at, last_error, created_at)
                VALUES (?, 0, ?, ?, ?)
                """,
                (json.dumps(payload), next_at, error[:1000], now),
            )
            db.commit()

    def flush_buffer(self, *, max_items: int = 50) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        sent = failed = skipped = 0
        with metadata_db.connect() as db:
            rows = list(
                db.execute(
                    """
                    SELECT id, payload_json, attempts, next_attempt_at
                    FROM telemetry_buffer
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (max_items,),
                )
            )
            for row in rows:
                rid = int(row["id"])
                attempts = int(row["attempts"])
                next_at = _parse_ts(row["next_attempt_at"])
                if next_at > now:
                    skipped += 1
                    continue
                payload = json.loads(row["payload_json"])
                try:
                    self._http_post(payload)
                    db.execute("DELETE FROM telemetry_buffer WHERE id = ?", (rid,))
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    attempts += 1
                    nxt = (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=_backoff_seconds(attempts))
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    db.execute(
                        """
                        UPDATE telemetry_buffer
                        SET attempts = ?, next_attempt_at = ?, last_error = ?
                        WHERE id = ?
                        """,
                        (attempts, nxt, str(exc)[:1000], rid),
                    )
                    failed += 1
            db.commit()
        return {"sent": sent, "failed": failed, "skipped": skipped}
