"""Subscription tier enforcement for tenant-scoped API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status

from app.services.capability_access_service import tenant_has_capability_for_min_tier
from app.services.subscription_tier_service import (
    SubscriptionTier,
    get_tenant_subscription_tier,
    is_custom_tier,
    tier_meets_minimum,
)


def tier_forbidden_detail(min_tier: SubscriptionTier, *, custom: bool = False) -> str:
    if custom:
        return "This capability is not included in your custom subscription agreement."
    if min_tier == SubscriptionTier.GOLD:
        return "This capability requires a GOLD or PLATINUM subscription tier."
    if min_tier == SubscriptionTier.PLATINUM:
        return "This capability requires a PLATINUM subscription tier."
    return "This capability requires a SILVER, GOLD, or PLATINUM subscription tier."


def enforce_tenant_subscription_tier(
    tenant_id: Optional[str],
    min_tier: SubscriptionTier,
    *,
    catalog_key: Optional[str] = None,
) -> None:
    """
    Raise 403 when the tenant cannot access a capability.

    Standard tiers: subscription rank vs min_tier.
    CUSTOM tier: entitlement flags for catalog_key (required for CUSTOM tenants).
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=tier_forbidden_detail(min_tier),
        )
    current = get_tenant_subscription_tier(str(tenant_id))
    if is_custom_tier(current):
        if not tenant_has_capability_for_min_tier(
            str(tenant_id), min_tier, catalog_key=catalog_key
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=tier_forbidden_detail(min_tier, custom=True),
            )
        return

    if not tier_meets_minimum(current, min_tier):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=tier_forbidden_detail(min_tier),
        )


def require_subscription_tier(min_tier: SubscriptionTier):
    """
    Dependency factory for routes that resolve ``tenant_id`` before invocation.

    Usage::

        _tier = Depends(require_subscription_tier(SubscriptionTier.GOLD))

    Call ``enforce_tenant_subscription_tier(tenant_id, min_tier)`` inside handlers
    when tenant resolution is route-specific (short_code, payload, appliance).
    """

    def _dependency() -> SubscriptionTier:
        return min_tier

    return _dependency
