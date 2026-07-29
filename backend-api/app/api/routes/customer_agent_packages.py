"""KB-086: Customer portal endpoint-agent package downloads (tenant-scoped)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.dependencies import get_current_user, require_tenant_match
from app.db.session import fetch_one
from app.services.agent_package_builder import build_agent_package_zip
from app.services.agent_install_repo import publish_linux_install
from app.services.audit_service import audit_from_user
from app.services.tenant_engine_provisioner import (
    ensure_binding_row,
    provision_tenant_engines,
    wazuh_group_for,
)

router = APIRouter(prefix="/customer", tags=["customer-agent-packages"])

_CUSTOMER_ROLES = frozenset({"customer_admin", "customer_viewer"})


def _resolve_tenant(short_code: str, user: Dict[str, Any]) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, short_code, name FROM tenants WHERE short_code = %s;",
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    require_tenant_match(tenant["id"], user)
    return tenant


@router.get("/agent-install/{short_code}/linux")
def get_customer_linux_install_command(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Customer-safe one-liner for headless Linux install."""
    if current_user.get("role") not in _CUSTOMER_ROLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    tenant = _resolve_tenant(short_code, current_user)
    ensure_binding_row(tenant["id"], tenant["short_code"])
    try:
        provision_tenant_engines(
            tenant_id=tenant["id"],
            short_code=tenant["short_code"],
            tenant_name=tenant["name"],
            actor_user_id=current_user.get("id"),
        )
    except Exception:
        pass
    published = publish_linux_install(
        tenant_id=tenant["id"],
        short_code=tenant["short_code"],
        rotate=False,
    )
    return {
        "short_code": tenant["short_code"],
        "one_liner": published["one_liner"],
        "script_url": published["script_url"],
        "help": (
            "Run this single command on each Linux computer. "
            "No browser needed — the installer is hosted on your MSSP platform."
        ),
    }


@router.get("/agent-packages/{short_code}/{os_type}")
def download_customer_agent_package(
    short_code: str,
    os_type: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Response:
    """
    Download a ZIP that installs the endpoint monitoring agent for this tenant.

    os_type: windows | linux | all
    """
    if current_user.get("role") not in _CUSTOMER_ROLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    tenant = _resolve_tenant(short_code, current_user)

    binding = ensure_binding_row(tenant["id"], tenant["short_code"])
    group = binding.get("wazuh_agent_group") or wazuh_group_for(tenant["short_code"])
    try:
        provision_tenant_engines(
            tenant_id=tenant["id"],
            short_code=tenant["short_code"],
            tenant_name=tenant["name"],
            actor_user_id=current_user.get("id"),
        )
        binding = ensure_binding_row(tenant["id"], tenant["short_code"])
        group = binding.get("wazuh_agent_group") or group
    except Exception:
        pass

    try:
        payload, filename = build_agent_package_zip(
            tenant_name=tenant["name"],
            short_code=tenant["short_code"],
            wazuh_agent_group=group,
            os_type=os_type,
            customer_facing=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if os_type.lower() in ("linux", "all"):
        try:
            publish_linux_install(
                tenant_id=tenant["id"],
                short_code=tenant["short_code"],
                rotate=False,
            )
        except Exception:
            pass

    audit_from_user(
        current_user,
        action="AGENT_PACKAGE_DOWNLOAD",
        entity_type="tenant",
        entity_id=tenant["id"],
        tenant_id=tenant["id"],
        details={
            "short_code": tenant["short_code"],
            "os_type": os_type.lower(),
            "audience": "customer",
            "filename": filename,
        },
    )

    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
