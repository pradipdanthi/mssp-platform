"""Tail local Wazuh alerts.json and forward only high-fidelity alerts to cloud.

Deployment model (KB-073 on_prem_appliance / cloud_appliance / hybrid):
  endpoint wazuh-agent → local appliance Manager (LAN)
  appliance → scrub + filter → POST /api/v1/telemetry/ingest (secure channel)

Raw logs and low-noise alerts stay on the appliance. Default forward threshold
is Wazuh rule level >= 10 (high + critical). Set KEVANTIC_FORWARD_MIN_LEVEL=12
for critical-only.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Iterator, Optional

from appliance.common import metadata_db
from appliance.common.privacy import to_cloud_alert
from appliance.telemetry.forwarder import TelemetryForwarder

logger = logging.getLogger("kevantic.critical-alert-forwarder")

DEFAULT_ALERTS_PATH = "/var/ossec/logs/alerts/alerts.json"
DEFAULT_MIN_LEVEL = 10
STATE_KEY = "critical_alert_forwarder"


def _env(*keys: str, default: str = "") -> str:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return default


def _min_level() -> int:
    raw = _env("KEVANTIC_FORWARD_MIN_LEVEL", "JUNEXIS_FORWARD_MIN_LEVEL", default=str(DEFAULT_MIN_LEVEL))
    try:
        return max(1, min(15, int(raw)))
    except ValueError:
        return DEFAULT_MIN_LEVEL


def _alerts_path() -> Path:
    return Path(
        _env(
            "KEVANTIC_WAZUH_ALERTS_PATH",
            "JUNEXIS_WAZUH_ALERTS_PATH",
            default=DEFAULT_ALERTS_PATH,
        )
    )


def _rule_level(event: dict[str, Any]) -> int:
    rule = event.get("rule") if isinstance(event.get("rule"), dict) else {}
    try:
        return int(rule.get("level") or event.get("level") or 0)
    except (TypeError, ValueError):
        return 0


def should_forward(event: dict[str, Any], *, min_level: int) -> bool:
    """True for high-fidelity alerts at or above the configured Wazuh level."""
    if not isinstance(event, dict):
        return False
    return _rule_level(event) >= min_level


def _load_cursor() -> dict[str, Any]:
    with metadata_db.connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS forwarder_state (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        row = db.execute(
            "SELECT value_json FROM forwarder_state WHERE key = ?",
            (STATE_KEY,),
        ).fetchone()
        if not row:
            return {"path": "", "inode": None, "offset": 0}
        try:
            data = json.loads(row["value_json"])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        return {"path": "", "inode": None, "offset": 0}


def _save_cursor(cursor: dict[str, Any]) -> None:
    with metadata_db.connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS forwarder_state (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        db.execute(
            """
            INSERT INTO forwarder_state (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value_json = excluded.value_json,
              updated_at = excluded.updated_at
            """,
            (STATE_KEY, json.dumps(cursor), metadata_db.utc_now()),
        )
        db.commit()


def _normalize_for_cloud(event: dict[str, Any]) -> dict[str, Any]:
    """Ensure Wazuh events map to the safe ingest contract."""
    enriched = dict(event)
    enriched.setdefault("source_tool", "wazuh")
    agent = enriched.get("agent") if isinstance(enriched.get("agent"), dict) else {}
    if agent.get("name") and not enriched.get("destination_host"):
        enriched["destination_host"] = agent.get("name")
    return enriched


def process_event(
    event: dict[str, Any],
    *,
    forwarder: TelemetryForwarder,
    min_level: int,
) -> Optional[dict[str, Any]]:
    if not should_forward(event, min_level=min_level):
        return None
    payload_event = _normalize_for_cloud(event)
    # Sanity: never forward medium/low after mapping
    cloud = to_cloud_alert(payload_event)
    if cloud.get("severity") not in ("high", "critical"):
        return None
    return forwarder.forward_event(payload_event)


def _iter_new_lines(path: Path, *, start_offset: int) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(start_offset)
        while True:
            line = fh.readline()
            if not line:
                break
            yield fh.tell(), line


def drain_once(
    *,
    path: Optional[Path] = None,
    forwarder: Optional[TelemetryForwarder] = None,
    min_level: Optional[int] = None,
) -> dict[str, int]:
    """Read newly appended alert lines and forward qualifying events."""
    alerts = path or _alerts_path()
    level = _min_level() if min_level is None else min_level
    fwd = forwarder or TelemetryForwarder()
    stats = {"read": 0, "forwarded": 0, "skipped": 0, "errors": 0, "missing": 0}

    if not alerts.is_file():
        stats["missing"] = 1
        logger.debug("alerts file not present yet: %s", alerts)
        return stats

    st = alerts.stat()
    cursor = _load_cursor()
    inode = getattr(st, "st_ino", None)
    offset = int(cursor.get("offset") or 0)
    if cursor.get("path") != str(alerts) or cursor.get("inode") != inode:
        # Rotated or first run — start at EOF to avoid flooding cloud with history
        offset = st.st_size
        logger.info(
            "alert cursor reset path=%s inode=%s offset=%s",
            alerts,
            inode,
            offset,
        )
    if offset > st.st_size:
        offset = 0

    new_offset = offset
    for new_offset, line in _iter_new_lines(alerts, start_offset=offset):
        line = line.strip()
        if not line:
            continue
        stats["read"] += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            stats["errors"] += 1
            continue
        try:
            result = process_event(event, forwarder=fwd, min_level=level)
        except Exception:  # noqa: BLE001
            logger.exception("forward failed")
            stats["errors"] += 1
            continue
        if result is None:
            stats["skipped"] += 1
        else:
            stats["forwarded"] += 1

    _save_cursor({"path": str(alerts), "inode": inode, "offset": new_offset})
    # Always attempt buffer flush (covers prior network failures)
    try:
        flush = fwd.flush_buffer(max_items=50)
        stats["flushed_sent"] = int(flush.get("sent") or 0)
        stats["flushed_failed"] = int(flush.get("failed") or 0)
    except Exception:  # noqa: BLE001
        logger.exception("buffer flush failed")
    return stats


def run_loop(*, poll_seconds: float = 2.0) -> None:
    logging.basicConfig(
        level=os.environ.get("KEVANTIC_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    level = _min_level()
    path = _alerts_path()
    logger.info(
        "starting critical-alert forwarder path=%s min_level=%s",
        path,
        level,
    )
    fwd = TelemetryForwarder()
    while True:
        try:
            stats = drain_once(path=path, forwarder=fwd, min_level=level)
            if stats.get("forwarded") or stats.get("flushed_sent"):
                logger.info("forward cycle %s", stats)
        except Exception:  # noqa: BLE001
            logger.exception("drain cycle failed")
        time.sleep(max(0.5, poll_seconds))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Forward high/critical local Wazuh alerts to Kevantic cloud SOC"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process new lines once and exit (for timers)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=float(os.environ.get("KEVANTIC_FORWARD_POLL_SECONDS") or "2"),
    )
    parser.add_argument("--json", action="store_true", help="Print stats as JSON")
    args = parser.parse_args(argv)
    if args.once:
        stats = drain_once()
        if args.json:
            print(json.dumps(stats))
        return 0
    run_loop(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
