"""Subscription tier enforcement for tenant-scoped API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status

from app.services.subscription_tier_service import (
    SubscriptionTier,
    get_tenant_subscription_tier,
    tier_meets_minimum,
)

_TIER_LABELS = {
    SubscriptionTier.SILVER: "SILVER",
    SubscriptionTier.GOLD: "GOLD",
    SubscriptionTier.PLATINUM: "PLATINUM",
}


def tier_forbidden_detail(min_tier: SubscriptionTier) -> str:
    if min_tier == SubscriptionTier.GOLD:
        return "This capability requires a GOLD or PLATINUM subscription tier."
    if min_tier == SubscriptionTier.PLATINUM:
        return "This capability requires a PLATINUM subscription tier."
    return "This capability requires a SILVER, GOLD, or PLATINUM subscription tier."


def enforce_tenant_subscription_tier(
    tenant_id: Optional[str],
    min_tier: SubscriptionTier,
) -> None:
    """Raise 403 when the tenant subscription tier is below ``min_tier``."""
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=tier_forbidden_detail(min_tier),
        )
    current = get_tenant_subscription_tier(str(tenant_id))
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
