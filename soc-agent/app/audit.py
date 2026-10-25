from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


def audit(path: str, event: str, payload: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    line = json.dumps(row, default=str)
    with _lock:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
