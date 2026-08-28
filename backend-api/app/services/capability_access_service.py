"""Tenant capability access — tier rank for standard SKUs, entitlement flags for CUSTOM."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from app.api.routes.entitlements import DEFAULTS, _fetch_entitlements
from app.services.subscription_tier_service import (
    SubscriptionTier,
    get_tenant_subscription_tier,
    is_custom_tier,
    tier_meets_minimum,
)
from app.services.tenant_entitlement_defaults import CATALOG_KEY_TO_DISABLE_UPDATES

# Minimum standard tier per sync-eligible catalog key.
CATALOG_KEY_MIN_TIER: Dict[str, str] = {
    "cloud_identity_protection": "SILVER",
    "security_automation": "GOLD",
    "vulnerability_management": "GOLD",
    "external_attack_surface": "GOLD",
    "continuous_compliance": "PLATINUM",
    "network_detection_response": "PLATINUM",
    "network_traffic_analysis": "PLATINUM",
    "threat_intelligence": "PLATINUM",
    "endpoint_forensics_deception": "PLATINUM",
    "endpoint_forensics": "PLATINUM",
}

MIN_TIER_TO_CATALOG_KEY: Dict[SubscriptionTier, str] = {
    SubscriptionTier.SILVER: "cloud_identity_protection",
    SubscriptionTier.GOLD: "vulnerability_management",
    SubscriptionTier.PLATINUM: "continuous_compliance",
}


def _entitlement_row(tenant_id: str) -> Dict[str, Any]:
    row = _fetch_entitlements(UUID(tenant_id)) or {}
    return {**DEFAULTS, **{k: row.get(k) for k in DEFAULTS if k in row}}


def catalog_key_enabled_in_entitlements(catalog_key: str, ent: Dict[str, Any]) -> bool:
    """True when entitlement flags reflect an enabled catalog module."""
    key = catalog_key.strip().lower()
    if key in ("cloud_identity_protection",):
        return bool(ent.get("cloud_identity_protection_enabled"))
    if key == "security_automation":
        return str(ent.get("shuffle_mode") or "off").lower() not in ("off", "none", "disabled")
    if key == "vulnerability_management":
        return bool(ent.get("greenbone_enabled"))
    if key == "external_attack_surface":
        return bool(ent.get("external_attack_surface_enabled"))
    if key == "continuous_compliance":
        return bool(ent.get("continuous_compliance_enabled"))
    if key in ("network_detection_response", "network_traffic_analysis"):
        return bool(ent.get("zeek_enabled"))
    if key == "threat_intelligence":
        return bool(ent.get("misp_enabled"))
    if key in ("endpoint_forensics_deception", "endpoint_forensics"):
        return bool(ent.get("velociraptor_enabled"))
    if key in ("log_event_monitoring",):
        return bool(ent.get("wazuh_siem", True))
    if key == "incident_response":
        mode = str(ent.get("thehive_mode") or "").lower()
        return mode not in ("off", "none", "disabled", "")
    return False


def tenant_has_catalog_capability(tenant_id: str, catalog_key: str) -> bool:
    ent = _entitlement_row(tenant_id)
    return catalog_key_enabled_in_entitlements(catalog_key, ent)


def tenant_has_capability_for_min_tier(
    tenant_id: str,
    min_tier: SubscriptionTier,
    *,
    catalog_key: Optional[str] = None,
) -> bool:
    """Standard tiers: rank check. CUSTOM: entitlement flag for catalog_key."""
    current = get_tenant_subscription_tier(tenant_id)
    if is_custom_tier(current):
        resolved_key = catalog_key or MIN_TIER_TO_CATALOG_KEY.get(min_tier)
        if not resolved_key:
            return False
        return tenant_has_catalog_capability(tenant_id, resolved_key)
    return tier_meets_minimum(current, min_tier)


def enabled_catalog_keys_for_tenant(tenant_id: str) -> list[str]:
    ent = _entitlement_row(tenant_id)
    keys = []
    for key in CATALOG_KEY_MIN_TIER:
        if catalog_key_enabled_in_entitlements(key, ent):
            keys.append(key)
    if catalog_key_enabled_in_entitlements("security_automation", ent):
        if "security_automation" not in keys:
            keys.append("security_automation")
    return sorted(set(keys))


def disable_updates_for_unselected(selected: set[str]) -> Dict[str, Any]:
    """Disable flags for unselected modules; alias keys share the same entitlement field."""
    alias_groups = [
        {"network_detection_response", "network_traffic_analysis"},
        {"endpoint_forensics_deception", "endpoint_forensics"},
    ]
    merged: Dict[str, Any] = {}
    for key, updates in CATALOG_KEY_TO_DISABLE_UPDATES.items():
        if key not in selected:
            if any(key in group and selected.intersection(group) for group in alias_groups):
                continue
            merged.update(updates)
    return merged
