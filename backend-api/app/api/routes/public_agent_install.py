"""Public (tokenized) Linux agent install bootstrap — no browser / no JWT."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.services.agent_install_repo import build_script_for_tenant, resolve_token

router = APIRouter(prefix="/v1/agent-install", tags=["agent-install-public"])


@router.get("/{short_code}/{token}/linux.sh")
def public_linux_install_script(short_code: str, token: str) -> PlainTextResponse:
    """
    Tenant-scoped installer script for headless Linux hosts.

    Usage on the endpoint:
      curl -fsSL 'http://<control-plane>:8000/v1/agent-install/<CODE>/<TOKEN>/linux.sh' | sudo bash
    """
    row = resolve_token(short_code, token)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    script = build_script_for_tenant(row["short_code"], row["tenant_id"])
    return PlainTextResponse(
        content=script if script.endswith("\n") else script + "\n",
        media_type="text/x-shellscript",
        headers={
            "Content-Disposition": f'inline; filename="mssp-install-{row["short_code"].lower()}-linux.sh"',
            "Cache-Control": "no-store",
        },
    )
