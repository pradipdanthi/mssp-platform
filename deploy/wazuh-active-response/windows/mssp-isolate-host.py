#!/usr/bin/env python3
"""MSSP AR: Windows host isolation via Windows Defender Firewall (netsh advfirewall).
Reads Wazuh execd JSON from stdin. Compatible with Wazuh 4.x AR framework on Windows."""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

LOG = r"C:\Program Files (x86)\ossec-agent\active-response\active-responses.log"
RULE_PREFIX = "MSSP_ISOLATE"
MANAGER = os.environ.get("WAZUH_MANAGER_IP", "192.168.0.211")


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.utcnow().strftime('%Y/%m/%d %H:%M:%S')} mssp-isolate-host: {msg}\n")
    except OSError:
        pass


def run(cmd: str) -> int:
    result = subprocess.run(
        cmd, shell=True, check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return result.returncode


def isolate_delete() -> None:
    """Remove MSSP isolation firewall rules — restore normal connectivity."""
    for direction in ("in", "out"):
        run(f'netsh advfirewall firewall delete rule name="{RULE_PREFIX}_BLOCK_{direction.upper()}"')
        run(f'netsh advfirewall firewall delete rule name="{RULE_PREFIX}_ALLOW_MANAGER_{direction.upper()}"')
        run(f'netsh advfirewall firewall delete rule name="{RULE_PREFIX}_ALLOW_DNS_{direction.upper()}"')
    log("ISOLATE delete — rules removed")


def isolate_add(seconds: int) -> None:
    """Block all traffic except Manager and DNS via named firewall rules."""
    # Clean any pre-existing rules first
    isolate_delete()

    # Allow Wazuh Manager (both directions)
    run(
        f'netsh advfirewall firewall add rule name="{RULE_PREFIX}_ALLOW_MANAGER_OUT" '
        f'dir=out action=allow remoteip={MANAGER} enable=yes'
    )
    run(
        f'netsh advfirewall firewall add rule name="{RULE_PREFIX}_ALLOW_MANAGER_IN" '
        f'dir=in action=allow remoteip={MANAGER} enable=yes'
    )

    # Allow DNS (UDP+TCP port 53 outbound)
    run(
        f'netsh advfirewall firewall add rule name="{RULE_PREFIX}_ALLOW_DNS_OUT" '
        f'dir=out action=allow protocol=udp remoteport=53 enable=yes'
    )
    run(
        f'netsh advfirewall firewall add rule name="{RULE_PREFIX}_ALLOW_DNS_IN" '
        f'dir=out action=allow protocol=tcp remoteport=53 enable=yes'
    )

    # Block everything else (lower priority — named rules with allow take precedence
    # because "allow" rules override "block" when profile match is equivalent)
    run(
        f'netsh advfirewall firewall add rule name="{RULE_PREFIX}_BLOCK_OUT" '
        f'dir=out action=block enable=yes'
    )
    run(
        f'netsh advfirewall firewall add rule name="{RULE_PREFIX}_BLOCK_IN" '
        f'dir=in action=block enable=yes'
    )
    log(f"ISOLATE add seconds={seconds} manager={MANAGER}")

    # Auto-release in background thread
    def _auto_release():
        time.sleep(seconds)
        isolate_delete()

    t = threading.Thread(target=_auto_release, daemon=True)
    t.start()


def main() -> int:
    raw = sys.stdin.readline()
    if not raw.strip() and len(sys.argv) > 1:
        raw = sys.argv[1]
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    cmd = str(data.get("command") or "add").lower()
    args = (data.get("parameters") or {}).get("extra_args") or data.get("arguments") or []
    if args and str(args[0]).lower() in ("delete", "remove", "unisolate"):
        cmd = "delete"
    seconds = 120
    if args and cmd not in ("delete", "remove"):
        try:
            seconds = int(args[0])
        except ValueError:
            seconds = 120
    seconds = max(30, min(seconds, 600))
    if cmd in ("delete", "remove"):
        isolate_delete()
    else:
        isolate_add(seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
