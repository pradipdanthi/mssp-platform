"""KB-083: Shuffle SOAR webhooks for EDR response workflows."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _read_secret_file(*candidates: str) -> str:
    for candidate in candidates:
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return ""


def shuffle_webhook_url() -> str:
    env = (os.getenv("SHUFFLE_WEBHOOK_URL") or "").strip()
    if env:
        return env
    key_file = (os.getenv("SHUFFLE_WEBHOOK_URL_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/shuffle_webhook_url",
        "/opt/mssp-control/.secrets/shuffle_webhook_url",
    )


def forensics_workflow_name() -> str:
    return (
        os.getenv("EDR_SHUFFLE_FORENSICS_WORKFLOW") or "EDR_COLLECT_FORENSICS"
    ).strip()


def velociraptor_server_url() -> str:
    """When VM 110 is live, set VELOCIRAPTOR_SERVER_URL for direct routing."""
    return (os.getenv("VELOCIRAPTOR_SERVER_URL") or "").strip().rstrip("/")


def post_edr_workflow(payload: Dict[str, Any]) -> tuple[bool, str]:
    """
    Post structured EDR action to Shuffle. Fail-safe: never raises to caller.
    """
    url = shuffle_webhook_url()
    if not url:
        return False, "Shuffle webhook is not configured on the control plane"

    body = {
        "source": "mssp-control-plane-edr",
        "forensics_workflow": forensics_workflow_name(),
        "velociraptor_server": velociraptor_server_url() or None,
        **payload,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            resp.read()
            return True, f"Shuffle acknowledged (HTTP {getattr(resp, 'status', 200)})"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning("Shuffle EDR webhook HTTP %s: %s", exc.code, detail)
        return False, f"Shuffle webhook failed (HTTP {exc.code})"
    except Exception as exc:
        logger.exception("Shuffle EDR webhook error")
        return False, f"Shuffle webhook error: {exc}"
