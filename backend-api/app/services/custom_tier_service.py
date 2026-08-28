"""Admin-only CUSTOM tier — pick capabilities à la carte, same fulfillment router."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.api.routes.entitlements import DEFAULTS, upsert_tenant_entitlements
from app.services.capability_access_service import (
    CATALOG_KEY_MIN_TIER,
    disable_updates_for_unselected,
)
from app.services.capability_fulfillment_service import fulfill_tenant_capabilities
from app.services.subscription_tier_service import is_custom_tier, set_tenant_subscription_tier
from app.services.tenant_entitlement_defaults import CATALOG_KEY_TO_ENTITLEMENT_UPDATES

# Core MSSP baseline always included for CUSTOM contracts.
CUSTOM_BASELINE_ENTITLEMENTS: Dict[str, Any] = {
    "wazuh_siem": True,
    "wazuh_retention_days": 90,
    "thehive_mode": "full",
    "greenbone_enabled": False,
    "greenbone_cadence": "off",
    "shuffle_mode": "off",
    "zeek_enabled": False,
    "misp_enabled": False,
    "velociraptor_enabled": False,
    "continuous_compliance_enabled": False,
    "external_attack_surface_enabled": False,
    "cloud_identity_protection_enabled": False,
    "roadmap_notes": "CUSTOM tier — admin-provisioned capability bundle",
}

SELECTABLE_CATALOG_KEYS: List[str] = sorted(
    set(CATALOG_KEY_MIN_TIER.keys()) | {"security_automation"}
)


def normalize_custom_catalog_keys(keys: List[str]) -> List[str]:
    normalized = []
    for raw in keys:
        key = (raw or "").strip().lower()
        if key in SELECTABLE_CATALOG_KEYS and key not in normalized:
            normalized.append(key)
    return normalized


def entitlements_for_custom_selection(catalog_keys: List[str]) -> Dict[str, Any]:
    """Build entitlement payload from selected catalog modules."""
    selected = set(normalize_custom_catalog_keys(catalog_keys))
    if not selected:
        raise ValueError("At least one capability module must be selected for CUSTOM tier.")

    merged = dict(CUSTOM_BASELINE_ENTITLEMENTS)
    for key in selected:
        updates = CATALOG_KEY_TO_ENTITLEMENT_UPDATES.get(key)
        if updates:
            merged.update(updates)

    merged.update(disable_updates_for_unselected(selected))
    merged["roadmap_notes"] = (
        f"CUSTOM tier — selected modules: {', '.join(sorted(selected))}"
    )
    return merged


def provision_custom_tier(
    tenant_id: str,
    *,
    catalog_keys: List[str],
    actor_user_id: Optional[str] = None,
    order_number: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set CUSTOM tier, apply selected entitlement flags, run uniform fulfillment.
    Does not overwrite flags via standard tier bundle sync.
    """
    keys = normalize_custom_catalog_keys(catalog_keys)
    bundle = entitlements_for_custom_selection(keys)

    set_tenant_subscription_tier(
        tenant_id,
        "CUSTOM",
        sync_entitlements=False,
        actor_user_id=actor_user_id,
    )
    upsert_tenant_entitlements(tenant_id, bundle, actor_user_id=actor_user_id)

    fulfillment = fulfill_tenant_capabilities(
        tenant_id,
        catalog_keys=keys,
        catalog_key_label="tier_custom",
        actor_user_id=actor_user_id,
        order_number=order_number,
        clear_asset_coverage=True,
    )

    return {
        "tenant_id": tenant_id,
        "subscription_tier": "CUSTOM",
        "selected_catalog_keys": keys,
        "entitlements": {**DEFAULTS, **bundle},
        "fulfillment": fulfillment,
    }


def custom_tier_catalog_metadata() -> List[Dict[str, Any]]:
    """Admin UI metadata for capability picker."""
    return [
        {
            "catalog_key": key,
            "min_standard_tier": CATALOG_KEY_MIN_TIER.get(key, "SILVER"),
        }
        for key in SELECTABLE_CATALOG_KEYS
    ]
