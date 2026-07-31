"""Outbound email via Resend HTTP API (sales notifications)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_SALES_TO = "sales@keroxsys.com"
DEFAULT_FROM = "MSSP Control Plane <onboarding@resend.dev>"


def _api_key() -> str:
    return (os.getenv("RESEND_API_KEY") or "").strip()


def resend_configured() -> bool:
    return bool(_api_key())


def send_resend_email(
    *,
    subject: str,
    html: str,
    to: Optional[List[str]] = None,
    from_addr: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send one email through Resend.
    Returns {"ok": True, "id": ...} or {"ok": False, "error": "..."}.
    Never raises — callers decide how to surface dispatch failures.
    """
    key = _api_key()
    if not key:
        return {"ok": False, "error": "RESEND_API_KEY is not configured"}

    payload = {
        "from": (from_addr or os.getenv("RESEND_FROM_EMAIL") or DEFAULT_FROM).strip(),
        "to": to or [os.getenv("SALES_NOTIFY_EMAIL") or DEFAULT_SALES_TO],
        "subject": subject,
        "html": html,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return {"ok": True, "id": data.get("id"), "raw": data}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        logger.warning("Resend HTTP %s: %s", exc.code, detail)
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resend send failed: %s", exc)
        return {"ok": False, "error": str(exc)[:500]}


def build_consultation_request_html(
    *,
    tenant_id: str,
    tenant_name: str,
    short_code: str,
    contact_name: str,
    contact_email: str,
    service_name: str,
    pricing_tier: str,
    endpoint_count: Optional[int],
    m365_seat_count: Optional[int],
    target_domains: List[str],
    scope_notes: str,
    request_id: str,
    admin_review_url: str,
) -> str:
    domains = ", ".join(target_domains) if target_domains else "—"
    rows = [
        ("Request ID", request_id),
        ("Tenant ID", tenant_id),
        ("Organization", f"{tenant_name} ({short_code})"),
        ("Contact name", contact_name or "—"),
        ("Contact email", contact_email or "—"),
        ("Requested service", service_name),
        ("Pricing tier", pricing_tier or "—"),
        ("Endpoints (est.)", str(endpoint_count) if endpoint_count is not None else "—"),
        ("M365 seats (est.)", str(m365_seat_count) if m365_seat_count is not None else "—"),
        ("Target domains", domains),
        ("Customer notes", scope_notes or "—"),
        ("Admin review", f'<a href="{admin_review_url}">{admin_review_url}</a>'),
    ]
    trs = "".join(
        f"<tr><th style='text-align:left;padding:8px;border:1px solid #ddd;background:#f6f8fa'>{k}</th>"
        f"<td style='padding:8px;border:1px solid #ddd'>{v}</td></tr>"
        for k, v in rows
    )
    return (
        "<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#111'>"
        "<h2 style='margin:0 0 12px'>New consulting / service request</h2>"
        "<p>A customer (or SOC on their behalf) submitted a Service Catalog consultation request.</p>"
        f"<table style='border-collapse:collapse;width:100%;max-width:720px'>{trs}</table>"
        "<p style='margin-top:16px;color:#555'>Sent by MSSP Control Plane.</p>"
        "</div>"
    )
