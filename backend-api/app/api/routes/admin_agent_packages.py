"""KB-086: Per-tenant agent install package downloads."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_one
from app.services.agent_package_builder import build_agent_package_zip
from app.services.agent_install_repo import publish_linux_install
from app.services.audit_service import audit_from_user
from app.services.tenant_engine_provisioner import (
    ensure_binding_row,
    provision_tenant_engines,
    wazuh_group_for,
)

router = APIRouter(prefix="/admin/tenants", tags=["admin-agent-packages"])

WRITE_ROLES = ("platform_admin", "soc_manager")
READ_ROLES = ("platform_admin", "soc_manager", "soc_analyst")


@router.get("/{tenant_id}/agent-install/linux")
def get_tenant_linux_install_command(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*READ_ROLES)),
) -> Dict[str, Any]:
    """Return a ready one-liner for headless Linux install (publishes token if needed)."""
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code
        FROM tenants
        WHERE id = %s::uuid;
        """,
        (str(tenant_id),),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

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
        "tenant_id": tenant["id"],
        "tenant_name": tenant["name"],
        "short_code": tenant["short_code"],
        "one_liner": published["one_liner"],
        "script_url": published["script_url"],
        "wazuh_agent_group": published["wazuh_agent_group"],
        "help": (
            "Run this single command on the Linux endpoint (no browser). "
            "It downloads this customer's installer from the control-plane repo and installs via apt/yum."
        ),
    }


@router.post("/{tenant_id}/agent-install/linux/rotate")
def rotate_tenant_linux_install_command(
    tenant_id: UUID,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    tenant = fetch_one(
        "SELECT id::text, name, short_code FROM tenants WHERE id = %s::uuid;",
        (str(tenant_id),),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    published = publish_linux_install(
        tenant_id=tenant["id"],
        short_code=tenant["short_code"],
        rotate=True,
    )
    audit_from_user(
        current_user,
        action="AGENT_INSTALL_TOKEN_ROTATE",
        entity_type="tenant",
        entity_id=tenant["id"],
        tenant_id=tenant["id"],
        details={"short_code": tenant["short_code"], "os_type": "linux"},
    )
    return {
        "tenant_id": tenant["id"],
        "short_code": tenant["short_code"],
        "one_liner": published["one_liner"],
        "script_url": published["script_url"],
        "rotated": True,
    }


@router.get("/{tenant_id}/agent-packages/{os_type}")
def download_tenant_agent_package(
    tenant_id: UUID,
    os_type: str,
    current_user: Dict[str, Any] = Depends(require_roles(*WRITE_ROLES)),
) -> Response:
    """
    Download a ZIP that installs the endpoint agent into this tenant's Wazuh group.

    os_type: windows | linux | all
    """
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code
        FROM tenants
        WHERE id = %s::uuid;
        """,
        (str(tenant_id),),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Ensure engine binding / group exists before packaging.
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
        # Package still usable; group create may already exist.
        pass

    try:
        payload, filename = build_agent_package_zip(
            tenant_name=tenant["name"],
            short_code=tenant["short_code"],
            wazuh_agent_group=group,
            os_type=os_type,
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
            "wazuh_agent_group": group,
            "filename": filename,
        },
    )

    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
