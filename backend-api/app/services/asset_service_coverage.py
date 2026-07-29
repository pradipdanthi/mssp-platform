"""Asset-scoped entitlement coverage (which hosts get which optional service)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write


def validate_tenant_asset_ids(tenant_id: str, asset_ids: Sequence[str]) -> List[str]:
    """Return normalized unique asset ids that belong to the tenant; drop unknowns."""
    cleaned: List[str] = []
    seen = set()
    for raw in asset_ids:
        aid = str(raw or "").strip()
        if not aid or aid in seen:
            continue
        seen.add(aid)
        cleaned.append(aid)
    if not cleaned:
        return []
    rows = fetch_all(
        """
        SELECT id::text
        FROM protected_assets
        WHERE tenant_id = %s::uuid
          AND id = ANY(%s::uuid[]);
        """,
        (tenant_id, cleaned),
    )
    found = {r["id"] for r in rows}
    return [aid for aid in cleaned if aid in found]


def list_assets_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            pa.id::text,
            pa.hostname,
            pa.asset_type,
            pa.os_name,
            pa.status,
            host(pa.ip_address) AS ip_address
        FROM protected_assets pa
        WHERE pa.tenant_id = %s::uuid
        ORDER BY pa.hostname NULLS LAST, pa.created_at DESC
        LIMIT 2000;
        """,
        (tenant_id,),
    )


def list_covered_asset_ids(tenant_id: str, service_key: str) -> List[str]:
    rows = fetch_all(
        """
        SELECT asset_id::text
        FROM tenant_asset_service_coverage
        WHERE tenant_id = %s::uuid
          AND service_key = %s
          AND status = 'active';
        """,
        (tenant_id, service_key),
    )
    return [r["asset_id"] for r in rows]


def replace_coverage(
    *,
    tenant_id: str,
    service_key: str,
    asset_ids: Sequence[str],
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Replace active coverage for a tenant+service with the given asset list.
    Invalid / foreign assets are ignored. Empty list clears coverage.
    """
    valid = validate_tenant_asset_ids(tenant_id, asset_ids)

    # Deactivate all current rows for this service.
    execute(
        """
        UPDATE tenant_asset_service_coverage
        SET status = 'inactive', updated_at = now()
        WHERE tenant_id = %s::uuid
          AND service_key = %s
          AND status = 'active';
        """,
        (tenant_id, service_key),
    )

    for aid in valid:
        fetch_one_write(
            """
            INSERT INTO tenant_asset_service_coverage (
                tenant_id, asset_id, service_key, status, enabled_by
            )
            VALUES (%s::uuid, %s::uuid, %s, 'active', %s::uuid)
            ON CONFLICT (tenant_id, asset_id, service_key) DO UPDATE
              SET status = 'active',
                  enabled_by = EXCLUDED.enabled_by,
                  updated_at = now()
            RETURNING id::text;
            """,
            (tenant_id, aid, service_key, actor_user_id),
        )

    return {
        "tenant_id": tenant_id,
        "service_key": service_key,
        "covered_asset_ids": valid,
        "covered_count": len(valid),
    }


def coverage_picker_payload(tenant_id: str, service_key: str) -> Dict[str, Any]:
    assets = list_assets_for_tenant(tenant_id)
    covered = set(list_covered_asset_ids(tenant_id, service_key))
    for row in assets:
        row["covered"] = row["id"] in covered
    return {
        "tenant_id": tenant_id,
        "service_key": service_key,
        "covered_asset_ids": sorted(covered),
        "assets": assets,
    }


def summarize_assets(tenant_id: str, asset_ids: Sequence[str]) -> List[Dict[str, Any]]:
    valid = validate_tenant_asset_ids(tenant_id, asset_ids)
    if not valid:
        return []
    return fetch_all(
        """
        SELECT id::text, hostname, asset_type, os_name, host(ip_address) AS ip_address
        FROM protected_assets
        WHERE tenant_id = %s::uuid
          AND id = ANY(%s::uuid[])
        ORDER BY hostname NULLS LAST;
        """,
        (tenant_id, valid),
    )
