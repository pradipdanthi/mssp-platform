"""Tier rollout — delegates to uniform capability fulfillment router."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.capability_fulfillment_service import (
    CATALOG_KEY_MIN_TIER,
    SYNC_CATALOG_KEYS,
    catalog_keys_for_tier,
    fulfill_tier_capabilities,
    fulfill_tier_downgrade,
    is_tier_downgrade,
    newly_unlocked_catalog_keys,
    push_appliance_license,
    run_cloud_control_plane_syncs,
)

# Re-export for tests and callers expecting tier_rollout_service symbols.
__all__ = [
    "CATALOG_KEY_MIN_TIER",
    "SYNC_CATALOG_KEYS",
    "catalog_keys_for_tier",
    "newly_unlocked_catalog_keys",
    "fulfill_tier_rollout",
    "fulfill_tier_change",
    "push_tier_to_appliances",
    "run_tier_adapter_syncs",
]


def run_tier_adapter_syncs(
    tenant_id: str,
    *,
    target_tier: str,
    previous_tier: Optional[str] = None,
    sync_all_included: bool = True,
) -> List[Dict[str, Any]]:
    """Back-compat alias — uses deployment-aware cloud sync routing."""
    if sync_all_included:
        keys = catalog_keys_for_tier(target_tier)
    else:
        keys = newly_unlocked_catalog_keys(previous_tier or "SILVER", target_tier)
    return run_cloud_control_plane_syncs(tenant_id, keys)


def push_tier_to_appliances(
    tenant_id: str,
    *,
    target_tier: str,
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Back-compat alias — license derived from same entitlement flags as cloud."""
    from app.services.subscription_tier_service import normalize_subscription_tier

    catalog_key = f"tier_{normalize_subscription_tier(target_tier).lower()}"
    return push_appliance_license(
        tenant_id,
        catalog_key=catalog_key,
        actor_user_id=actor_user_id,
        order_number=order_number,
    )


def fulfill_tier_rollout(
    tenant_id: str,
    *,
    target_tier: str,
    previous_tier: str,
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
    clear_asset_coverage: bool = True,
) -> Dict[str, Any]:
    """Post-entitlement-sync tier fulfillment via uniform capability router."""
    return fulfill_tier_change(
        tenant_id,
        target_tier=target_tier,
        previous_tier=previous_tier,
        actor_user_id=actor_user_id,
        order_number=order_number,
        clear_asset_coverage=clear_asset_coverage,
    )


def fulfill_tier_change(
    tenant_id: str,
    *,
    target_tier: str,
    previous_tier: str,
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
    clear_asset_coverage: bool = True,
) -> Dict[str, Any]:
    """Route upgrade vs downgrade fulfillment after entitlement bundle sync."""
    if is_tier_downgrade(previous_tier, target_tier):
        return fulfill_tier_downgrade(
            tenant_id,
            target_tier=target_tier,
            previous_tier=previous_tier,
            actor_user_id=actor_user_id,
            order_number=order_number,
        )
    return fulfill_tier_capabilities(
        tenant_id,
        target_tier=target_tier,
        previous_tier=previous_tier,
        actor_user_id=actor_user_id,
        order_number=order_number,
        clear_asset_coverage=clear_asset_coverage,
    )
