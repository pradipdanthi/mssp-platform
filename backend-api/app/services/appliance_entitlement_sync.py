"""Push entitled catalogue services to tenant appliances via heartbeat jobs."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from app.db.session import fetch_all
from app.services import appliance_jobs as appliance_jobs_service
from app.services.tenant_entitlement_defaults import current_tenant_service_ids

logger = logging.getLogger(__name__)


def enqueue_tenant_entitlement_jobs(
    *,
    tenant_id: str,
    catalog_key: str,
    action: str,
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
    asset_ids: Optional[Sequence[str]] = None,
    appliance_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    service_ids = current_tenant_service_ids(tenant_id)
    where = ["tenant_id = %s::uuid", "status <> 'retired'"]
    params: List[Any] = [tenant_id]
    if appliance_ids:
        where.append("id = ANY(%s::uuid[])")
        params.append(list(appliance_ids))
    rows = fetch_all(
        f"""
        SELECT id::text
        FROM appliances
        WHERE {' AND '.join(where)}
        ORDER BY last_seen_at DESC NULLS LAST;
        """,
        tuple(params),
    )
    queued: List[str] = []
    errors: List[str] = []
    payload = {
        "catalog_key": catalog_key,
        "action": action,
        "service_ids": service_ids,
        "asset_ids": [str(a) for a in (asset_ids or [])],
        "order_number": order_number,
    }
    for row in rows:
        try:
            job = appliance_jobs_service.enqueue_job(
                appliance_id=row["id"],
                tenant_id=tenant_id,
                job_type="apply_entitlements",
                payload=payload,
                requested_by_user_id=actor_user_id,
                expires_hours=72,
            )
            queued.append(job.get("id") or row["id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("entitlement job enqueue failed for %s: %s", row["id"], exc)
            errors.append(str(exc)[:180])
    return {
        "service_ids": service_ids,
        "appliances": len(rows),
        "jobs_queued": len(queued),
        "errors": errors,
    }


def appliance_ids_for_assets(tenant_id: str, asset_ids: Sequence[str]) -> List[str]:
    if not asset_ids:
        return []
    rows = fetch_all(
        """
        SELECT DISTINCT appliance_id::text
        FROM protected_assets
        WHERE tenant_id = %s::uuid
          AND appliance_id IS NOT NULL
          AND id = ANY(%s::uuid[]);
        """,
        (tenant_id, list(asset_ids)),
    )
    return [r["appliance_id"] for r in rows if r.get("appliance_id")]
