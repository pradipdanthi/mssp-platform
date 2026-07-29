#!/usr/bin/env python3
"""MSSP AR: Windows process kill via taskkill / ctypes. Reads Wazuh execd JSON from stdin."""
import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime

LOG = r"C:\Program Files (x86)\ossec-agent\active-response\active-responses.log"


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S')} mssp-kill-process: {msg}\n")
    except OSError:
        pass


def kill_process_windows(pid: int) -> bool:
    """Kill process using taskkill (reliable cross-version). Fall back to ctypes."""
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    # Fallback: TerminateProcess via kernel32
    try:
        PROCESS_TERMINATE = 0x0001
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            success = kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
            return bool(success)
    except Exception:
        pass
    return False


def main() -> int:
    raw = sys.stdin.readline()
    if not raw.strip() and len(sys.argv) > 1:
        raw = sys.argv[1]
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    args = (data.get("parameters") or {}).get("extra_args") or data.get("arguments") or []
    pid_s = str(args[0]) if args else ""
    if not pid_s.isdigit():
        log(f"invalid pid={pid_s!r}")
        return 1
    pid = int(pid_s)
    if pid <= 4:
        log(f"refusing system pid={pid}")
        return 1
    if kill_process_windows(pid):
        log(f"killed pid={pid}")
        return 0
    else:
        log(f"kill failed pid={pid}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
