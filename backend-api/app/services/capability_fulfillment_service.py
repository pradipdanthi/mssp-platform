"""
Uniform capability fulfillment — one tier/entitlement model, deployment-aware routing.

Commercial source of truth: subscription_tier → tenant_entitlements flags.
Fulfillment targets:
  - cloud_control_plane: adapters that populate the MSSP control plane (TheHive, Shuffle, …)
  - appliance_local: signed license → local catalogue engines (svc-01..10)

See PLATFORM_SERVICE_UNIFORMITY.md.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from app.db.session import execute, fetch_one
from app.services.appliance_manager_resolver import tenant_uses_appliance_manager
from app.services.subscription_tier_service import normalize_subscription_tier, tier_rank
from app.services.tenant_entitlement_defaults import (
    CATALOG_KEY_TO_SVC_ID,
    trigger_post_enable_sync,
)

logger = logging.getLogger(__name__)

FulfillmentTarget = Literal["cloud_control_plane", "appliance_local", "both"]

# Minimum subscription tier that includes each sync-eligible capability module.
CATALOG_KEY_MIN_TIER: Dict[str, str] = {
    "cloud_identity_protection": "SILVER",
    "security_automation": "GOLD",
    "vulnerability_management": "GOLD",
    "external_attack_surface": "GOLD",
    "continuous_compliance": "PLATINUM",
    "network_detection_response": "PLATINUM",
    "threat_intelligence": "PLATINUM",
    "endpoint_forensics_deception": "PLATINUM",
}

SYNC_CATALOG_KEYS: List[str] = list(CATALOG_KEY_MIN_TIER.keys())

# On appliance deployments the local engine owns workload — skip duplicate cloud engine sync.
CLOUD_ENGINE_SYNC_SKIPPED_ON_APPLIANCE: frozenset[str] = frozenset(
    {
        "vulnerability_management",
        "external_attack_surface",
        "continuous_compliance",
        "network_detection_response",
        "network_traffic_analysis",
        "endpoint_forensics_deception",
        "endpoint_forensics",
    }
)


class CapabilityFulfillmentPlan(TypedDict):
    catalog_key: str
    min_tier: str
    appliance_svc_id: Optional[str]
    cloud_sync: bool
    appliance_license: bool
    skip_reason: Optional[str]


def catalog_keys_for_tier(tier: str) -> List[str]:
    """Capability modules included at or below the given subscription tier."""
    target_rank = tier_rank(tier)
    return [
        key
        for key in SYNC_CATALOG_KEYS
        if tier_rank(CATALOG_KEY_MIN_TIER[key]) <= target_rank
    ]


def newly_unlocked_catalog_keys(previous_tier: str, target_tier: str) -> List[str]:
    """Modules that become available when moving from previous → target tier."""
    prev = set(catalog_keys_for_tier(previous_tier))
    curr = set(catalog_keys_for_tier(target_tier))
    return sorted(curr - prev)


def revoked_catalog_keys(previous_tier: str, target_tier: str) -> List[str]:
    """Modules removed when moving from previous → lower target tier."""
    prev = set(catalog_keys_for_tier(previous_tier))
    curr = set(catalog_keys_for_tier(target_tier))
    return sorted(prev - curr)


def is_tier_downgrade(previous_tier: str, target_tier: str) -> bool:
    """True when target standard tier rank is below previous (CUSTOM excluded)."""
    from app.services.subscription_tier_service import is_custom_tier

    if is_custom_tier(previous_tier) or is_custom_tier(target_tier):
        return False
    return tier_rank(target_tier) < tier_rank(previous_tier)


def get_tenant_fulfillment_context(tenant_id: str) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT id::text,
               deployment_mode::text AS deployment_mode,
               subscription_tier::text AS subscription_tier
        FROM tenants
        WHERE id = %s::uuid;
        """,
        (tenant_id,),
    )
    if not row:
        return {
            "tenant_id": tenant_id,
            "deployment_mode": "cloud",
            "uses_appliance": False,
            "found": False,
        }
    mode = (row.get("deployment_mode") or "cloud").strip().lower()
    return {
        "tenant_id": row["id"],
        "deployment_mode": mode,
        "uses_appliance": tenant_uses_appliance_manager(mode),
        "subscription_tier": row.get("subscription_tier") or "SILVER",
        "found": True,
    }


def plan_capability_fulfillment(
    tenant_id: str,
    catalog_keys: List[str],
    *,
    ctx: Optional[Dict[str, Any]] = None,
) -> List[CapabilityFulfillmentPlan]:
    """Build per-capability fulfillment plan for a tenant."""
    context = ctx or get_tenant_fulfillment_context(tenant_id)
    uses_appliance = bool(context.get("uses_appliance"))
    plans: List[CapabilityFulfillmentPlan] = []

    for key in catalog_keys:
        svc_id = CATALOG_KEY_TO_SVC_ID.get(key)
        skip_cloud = uses_appliance and key in CLOUD_ENGINE_SYNC_SKIPPED_ON_APPLIANCE
        cloud_sync = not skip_cloud
        plans.append(
            CapabilityFulfillmentPlan(
                catalog_key=key,
                min_tier=CATALOG_KEY_MIN_TIER.get(key, "SILVER"),
                appliance_svc_id=svc_id,
                cloud_sync=cloud_sync,
                appliance_license=uses_appliance and bool(svc_id),
                skip_reason=(
                    "local_appliance_engine"
                    if skip_cloud
                    else None
                ),
            )
        )
    return plans


def run_cloud_control_plane_syncs(
    tenant_id: str,
    catalog_keys: List[str],
    *,
    ctx: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Run cloud-side adapter syncs per uniform fulfillment plan."""
    plans = plan_capability_fulfillment(tenant_id, catalog_keys, ctx=ctx)
    results: List[Dict[str, Any]] = []

    for plan in plans:
        key = plan["catalog_key"]
        if not plan["cloud_sync"]:
            results.append(
                {
                    "catalog_key": key,
                    "synced": False,
                    "target": "appliance_local",
                    "appliance_svc_id": plan["appliance_svc_id"],
                    "skipped": plan["skip_reason"],
                }
            )
            continue
        detail = trigger_post_enable_sync(tenant_id, key)
        detail["target"] = "cloud_control_plane"
        results.append(detail)

    return results


def push_appliance_license(
    tenant_id: str,
    *,
    catalog_key: str = "tier_sync",
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
    ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mint signed license from entitlement flags → queue apply_entitlements on appliances."""
    from app.services.appliance_entitlement_sync import enqueue_tenant_entitlement_jobs

    context = ctx or get_tenant_fulfillment_context(tenant_id)
    if not context.get("found"):
        return {"appliances": 0, "jobs_queued": 0, "skipped": "tenant_not_found"}
    if not context.get("uses_appliance"):
        return {
            "appliances": 0,
            "jobs_queued": 0,
            "skipped": "not_appliance_deployment",
            "deployment_mode": context.get("deployment_mode"),
        }

    return enqueue_tenant_entitlement_jobs(
        tenant_id=tenant_id,
        catalog_key=catalog_key,
        action="enable",
        actor_user_id=actor_user_id,
        order_number=order_number,
    )


def _clear_asset_scoped_coverage(tenant_id: str) -> int:
    """Tier SKUs cover all active assets — drop per-module asset pickers."""
    row = fetch_one(
        """
        SELECT COUNT(*)::int AS row_count
        FROM tenant_asset_service_coverage
        WHERE tenant_id = %s::uuid;
        """,
        (tenant_id,),
    )
    count = int(row.get("row_count") or 0)
    if count:
        execute(
            """
            DELETE FROM tenant_asset_service_coverage
            WHERE tenant_id = %s::uuid;
            """,
            (tenant_id,),
        )
    return count


def fulfill_tenant_capabilities(
    tenant_id: str,
    *,
    catalog_keys: List[str],
    catalog_key_label: str = "capability_sync",
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
    clear_asset_coverage: bool = False,
) -> Dict[str, Any]:
    """
    Uniform fulfillment entry point:
    - optional asset coverage reset
    - cloud control-plane syncs (deployment-aware)
    - appliance license push when deployment uses NikTiar Edge
    """
    ctx = get_tenant_fulfillment_context(tenant_id)
    plans = plan_capability_fulfillment(tenant_id, catalog_keys, ctx=ctx)

    coverage_cleared = 0
    if clear_asset_coverage:
        coverage_cleared = _clear_asset_scoped_coverage(tenant_id)

    sync_results = run_cloud_control_plane_syncs(tenant_id, catalog_keys, ctx=ctx)
    appliance_jobs: Dict[str, Any] = {"jobs_queued": 0, "appliances": 0, "skipped": "not_appliance_deployment"}
    if ctx.get("uses_appliance"):
        appliance_jobs = push_appliance_license(
            tenant_id,
            catalog_key=catalog_key_label,
            actor_user_id=actor_user_id,
            order_number=order_number,
            ctx=ctx,
        )

    cloud_synced = sum(1 for r in sync_results if r.get("synced"))
    cloud_skipped_local = sum(1 for r in sync_results if r.get("skipped") == "local_appliance_engine")

    return {
        "tenant_id": tenant_id,
        "deployment_mode": ctx.get("deployment_mode"),
        "uses_appliance": ctx.get("uses_appliance"),
        "coverage_rows_cleared": coverage_cleared,
        "fulfillment_plan": plans,
        "adapter_syncs": sync_results,
        "adapter_sync_count": len(sync_results),
        "adapter_sync_ok": cloud_synced,
        "adapter_sync_skipped_local_engine": cloud_skipped_local,
        "appliance_entitlement_push": appliance_jobs,
    }


def fulfill_tier_capabilities(
    tenant_id: str,
    *,
    target_tier: str,
    previous_tier: str,
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
    clear_asset_coverage: bool = True,
) -> Dict[str, Any]:
    """Tier rollout wrapper — standard tiers only; CUSTOM uses custom_tier_service."""
    from app.services.subscription_tier_service import is_custom_tier

    normalized_target = normalize_subscription_tier(target_tier)
    if is_custom_tier(normalized_target):
        raise ValueError("Use POST /admin/tenants/custom-tier-provision for CUSTOM tier.")
    normalized_previous = normalize_subscription_tier(previous_tier) if not is_custom_tier(previous_tier) else previous_tier
    keys = catalog_keys_for_tier(normalized_target)

    result = fulfill_tenant_capabilities(
        tenant_id,
        catalog_keys=keys,
        catalog_key_label=f"tier_{normalized_target.lower()}",
        actor_user_id=actor_user_id,
        order_number=order_number,
        clear_asset_coverage=clear_asset_coverage,
    )
    result["target_tier"] = normalized_target
    result["previous_tier"] = normalized_previous
    return result


def fulfill_tier_downgrade(
    tenant_id: str,
    *,
    target_tier: str,
    previous_tier: str,
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tier downgrade fulfillment — entitlements bundle must already be synced to target tier.
    Stops cloud schedulers for revoked modules and pushes reduced appliance license.
    """
    from app.services.asset_service_coverage import replace_coverage
    from app.services.subscription_tier_service import is_custom_tier
    from app.services.tenant_entitlement_defaults import trigger_post_disable_sync

    normalized_target = normalize_subscription_tier(target_tier)
    normalized_previous = (
        normalize_subscription_tier(previous_tier)
        if not is_custom_tier(previous_tier)
        else previous_tier
    )
    if is_custom_tier(normalized_target):
        raise ValueError("CUSTOM tier downgrades use custom tier provision, not tier rollout.")

    revoked = revoked_catalog_keys(normalized_previous, normalized_target)
    ctx = get_tenant_fulfillment_context(tenant_id)

    disable_results: List[Dict[str, Any]] = []
    coverage_cleared: List[str] = []
    for key in revoked:
        replace_coverage(
            tenant_id=tenant_id,
            service_key=key,
            asset_ids=[],
            actor_user_id=actor_user_id,
        )
        coverage_cleared.append(key)
        disable_results.append(trigger_post_disable_sync(tenant_id, key))

    appliance_jobs: Dict[str, Any] = {"jobs_queued": 0, "appliances": 0, "skipped": "not_appliance_deployment"}
    if ctx.get("uses_appliance"):
        appliance_jobs = push_appliance_license(
            tenant_id,
            catalog_key=f"tier_{normalized_target.lower()}_downgrade",
            actor_user_id=actor_user_id,
            order_number=order_number,
            ctx=ctx,
        )

    return {
        "tenant_id": tenant_id,
        "target_tier": normalized_target,
        "previous_tier": normalized_previous,
        "downgrade": True,
        "revoked_catalog_keys": revoked,
        "coverage_cleared_for": coverage_cleared,
        "disable_syncs": disable_results,
        "deployment_mode": ctx.get("deployment_mode"),
        "uses_appliance": ctx.get("uses_appliance"),
        "appliance_entitlement_push": appliance_jobs,
    }
