#!/usr/bin/env python3
"""MSSP AR: Windows hash block — append SHA256 to local CDB denylist.
Reads Wazuh execd JSON from stdin."""
import json
import os
import re
import sys
from datetime import datetime

LOG = r"C:\Program Files (x86)\ossec-agent\active-response\active-responses.log"
LIST = r"C:\Program Files (x86)\ossec-agent\etc\mssp_blocked_hashes.txt"


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S')} mssp-block-hash: {msg}\n")
    except OSError:
        pass


def main() -> int:
    raw = sys.stdin.readline()
    if not raw.strip() and len(sys.argv) > 1:
        raw = sys.argv[1]
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    args = (data.get("parameters") or {}).get("extra_args") or data.get("arguments") or []
    h = str(args[0]).strip().lower() if args else ""
    if not re.fullmatch(r"[a-f0-9]{64}", h):
        log(f"invalid hash={h!r}")
        return 1
    os.makedirs(os.path.dirname(LIST), exist_ok=True)
    existing = set()
    if os.path.exists(LIST):
        with open(LIST, encoding="utf-8") as fh:
            existing = {line.strip() for line in fh if line.strip()}
    if h in existing:
        log("hash already listed")
    else:
        with open(LIST, "a", encoding="utf-8") as fh:
            fh.write(h + "\n")
        log(f"hash blocked={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
