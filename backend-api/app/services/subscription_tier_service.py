"""Subscription tier definitions and entitlement bundle sync."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from app.api.routes.entitlements import DEFAULTS, upsert_tenant_entitlements
from app.db.session import execute, fetch_one

TIER_RANK: Dict[str, int] = {
    "SILVER": 1,
    "GOLD": 2,
    "PLATINUM": 3,
}

SILVER_ENTITLEMENTS: Dict[str, Any] = {
    "wazuh_siem": True,
    "wazuh_retention_days": 90,
    "thehive_mode": "read_only",
    "greenbone_enabled": False,
    "greenbone_cadence": "off",
    "shuffle_mode": "off",
    "zeek_enabled": False,
    "misp_enabled": False,
    "velociraptor_enabled": False,
    "continuous_compliance_enabled": False,
    "external_attack_surface_enabled": False,
    "cloud_identity_protection_enabled": True,
    "roadmap_notes": "SILVER tier — Cloud & Identity (ITDR)",
}

GOLD_ENTITLEMENTS: Dict[str, Any] = {
    **SILVER_ENTITLEMENTS,
    "thehive_mode": "full",
    "shuffle_mode": "standard",
    "greenbone_enabled": True,
    "greenbone_cadence": "weekly",
    "external_attack_surface_enabled": True,
    "roadmap_notes": "GOLD tier — MDR, EDR containment, EASM, vulnerability ingestion",
}

PLATINUM_ENTITLEMENTS: Dict[str, Any] = {
    **GOLD_ENTITLEMENTS,
    "greenbone_cadence": "daily",
    "zeek_enabled": True,
    "misp_enabled": True,
    "velociraptor_enabled": True,
    "continuous_compliance_enabled": True,
    "roadmap_notes": "PLATINUM tier — Full MXDR, NDR, DFIR, retrospective hunts, OLAP",
}

TIER_ENTITLEMENT_BUNDLES: Dict[str, Dict[str, Any]] = {
    "SILVER": SILVER_ENTITLEMENTS,
    "GOLD": GOLD_ENTITLEMENTS,
    "PLATINUM": PLATINUM_ENTITLEMENTS,
}


class SubscriptionTier(str, Enum):
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


def normalize_subscription_tier(value: Optional[str]) -> str:
    tier = (value or "SILVER").strip().upper()
    if tier not in TIER_RANK:
        raise ValueError(f"Invalid subscription_tier: {value}")
    return tier


def tier_rank(tier: str) -> int:
    return TIER_RANK.get(normalize_subscription_tier(tier), 0)


def entitlements_for_tier(tier: str) -> Dict[str, Any]:
    return dict(TIER_ENTITLEMENT_BUNDLES[normalize_subscription_tier(tier)])


def get_tenant_subscription_tier(tenant_id: str) -> str:
    row = fetch_one(
        "SELECT subscription_tier::text AS subscription_tier FROM tenants WHERE id = %s::uuid;",
        (tenant_id,),
    )
    if not row:
        return SubscriptionTier.SILVER.value
    return normalize_subscription_tier(row.get("subscription_tier"))


def get_tenant_id_from_short_code(short_code: str) -> Optional[str]:
    row = fetch_one(
        "SELECT id::text FROM tenants WHERE upper(short_code) = upper(%s);",
        (short_code,),
    )
    return row["id"] if row else None


def set_tenant_subscription_tier(
    tenant_id: str,
    tier: str,
    *,
    sync_entitlements: bool = True,
    actor_user_id: Optional[str] = None,
) -> str:
    normalized = normalize_subscription_tier(tier)
    execute(
        """
        UPDATE tenants
        SET subscription_tier = %s::subscription_tier, updated_at = now()
        WHERE id = %s::uuid;
        """,
        (normalized, tenant_id),
    )
    if sync_entitlements:
        sync_entitlements_for_tier(tenant_id, normalized, actor_user_id=actor_user_id)
    return normalized


def sync_entitlements_for_tier(
    tenant_id: str,
    tier: Optional[str] = None,
    *,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply the entitlement bundle for a tenant tier."""
    resolved = normalize_subscription_tier(tier or get_tenant_subscription_tier(tenant_id))
    bundle = entitlements_for_tier(resolved)
    upsert_tenant_entitlements(tenant_id, bundle, actor_user_id=actor_user_id)
    return {**DEFAULTS, **bundle, "tenant_id": tenant_id, "subscription_tier": resolved}


def tier_meets_minimum(tenant_tier: str, min_tier: SubscriptionTier) -> bool:
    return tier_rank(tenant_tier) >= tier_rank(min_tier.value)
