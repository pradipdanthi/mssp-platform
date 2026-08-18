"""Publish / serve per-tenant Linux agent install one-liners (headless hosts).

The generated script installs wazuh-agent, then fail-open auditd execve
collection (mid-layer EDR) and a Wazuh <localfile> reader for
/var/log/audit/audit.log so Manager alerts parse as endpoint_audit_exec.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, Optional
from urllib.parse import quote

from app.db.session import fetch_one, fetch_one_write
from app.services.agent_package_builder import build_linux_install_script
from app.services.tenant_engine_provisioner import ensure_binding_row, wazuh_group_for as _wg


def public_base_url() -> str:
    raw = (os.getenv("AGENT_INSTALL_PUBLIC_BASE") or "").strip().rstrip("/")
    if raw:
        return raw
    # Default lab control-plane API (reachable from endpoint VMs).
    return (os.getenv("PUBLIC_API_BASE") or "http://192.168.0.201:8000").strip().rstrip("/")


def _new_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_install_token(tenant_id: str, *, rotate: bool = False) -> Dict[str, Any]:
    existing = fetch_one(
        """
        SELECT
            tenant_id::text,
            install_token,
            linux_published_at::text,
            created_at::text,
            updated_at::text,
            rotated_at::text
        FROM tenant_agent_install_tokens
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    if existing and not rotate:
        return existing

    token = _new_token()
    if existing:
        row = fetch_one_write(
            """
            UPDATE tenant_agent_install_tokens
            SET install_token = %s,
                rotated_at = NOW(),
                linux_published_at = NOW(),
                updated_at = NOW()
            WHERE tenant_id = %s::uuid
            RETURNING
                tenant_id::text,
                install_token,
                linux_published_at::text,
                created_at::text,
                updated_at::text,
                rotated_at::text;
            """,
            (token, tenant_id),
        )
    else:
        row = fetch_one_write(
            """
            INSERT INTO tenant_agent_install_tokens (
                tenant_id, install_token, linux_published_at
            )
            VALUES (%s::uuid, %s, NOW())
            ON CONFLICT (tenant_id) DO UPDATE
              SET install_token = EXCLUDED.install_token,
                  linux_published_at = NOW(),
                  rotated_at = NOW(),
                  updated_at = NOW()
            RETURNING
                tenant_id::text,
                install_token,
                linux_published_at::text,
                created_at::text,
                updated_at::text,
                rotated_at::text;
            """,
            (tenant_id, token),
        )
    return row or {}


def resolve_token(short_code: str, token: str) -> Optional[Dict[str, Any]]:
    code = (short_code or "").strip().upper()
    tok = (token or "").strip()
    if not code or not tok:
        return None
    return fetch_one(
        """
        SELECT
            t.id::text AS tenant_id,
            t.name AS tenant_name,
            t.short_code,
            tok.install_token
        FROM tenant_agent_install_tokens tok
        JOIN tenants t ON t.id = tok.tenant_id
        WHERE upper(t.short_code) = %s
          AND tok.install_token = %s;
        """,
        (code, tok),
    )


def linux_install_commands(*, short_code: str, token: str) -> Dict[str, str]:
    base = public_base_url()
    code = quote(short_code.strip().upper(), safe="")
    tok = quote(token.strip(), safe="")
    script_url = f"{base}/v1/agent-install/{code}/{tok}/linux.sh"
    # Single command: download from control-plane repo and install (apt under the hood).
    # Script also configures auditd execve telemetry (fail-open if auditd is unavailable).
    one_liner = f'curl -fsSL "{script_url}" | sudo bash'
    apt_style = (
        f'# Headless Linux install (downloads tenant package from MSSP repo, then apt-get installs agent + auditd execve telemetry)\n'
        f'{one_liner}'
    )
    return {
        "script_url": script_url,
        "one_liner": one_liner,
        "apt_style_help": apt_style,
    }


def publish_linux_install(
    *,
    tenant_id: str,
    short_code: str,
    rotate: bool = False,
) -> Dict[str, Any]:
    binding = ensure_binding_row(tenant_id, short_code)
    group = binding.get("wazuh_agent_group") or _wg(short_code)
    tok_row = ensure_install_token(tenant_id, rotate=rotate)
    cmds = linux_install_commands(short_code=short_code, token=tok_row["install_token"])
    fetch_one_write(
        """
        UPDATE tenant_agent_install_tokens
        SET linux_published_at = NOW(), updated_at = NOW()
        WHERE tenant_id = %s::uuid
        RETURNING tenant_id::text;
        """,
        (tenant_id,),
    )
    return {
        "tenant_id": tenant_id,
        "short_code": short_code.strip().upper(),
        "wazuh_agent_group": group,
        "published": True,
        **cmds,
        "token_rotated": rotate,
    }


def build_script_for_tenant(short_code: str, tenant_id: str) -> str:
    from app.services.appliance_manager_resolver import resolve_tenant_manager_address

    binding = ensure_binding_row(tenant_id, short_code)
    group = binding.get("wazuh_agent_group") or _wg(short_code)
    mgr = resolve_tenant_manager_address(tenant_id)["manager_address"]
    return build_linux_install_script(
        short_code=short_code,
        wazuh_agent_group=group,
        manager=mgr,
    )
