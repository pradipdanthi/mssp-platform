"""
Default tenant entitlements for onboarding.

New tenants start core-only (log monitoring + incident response).
Add-on services stay AVAILABLE until Admin approves a consulting request.
Demo tenant ALPHAWINCORP-6VS2 keeps the full 10-service catalog for testing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

from app.db.session import fetch_one

logger = logging.getLogger("uvicorn.error")

# Customer short_code(s) that always receive the full demo catalog.
DEMO_FULL_ENTITLEMENT_SHORT_CODES: Set[str] = {"ALPHAWINCORP-6VS2"}

# Core MSSP package — enabled at tenant create (INCLUDED).
# Maps to catalog: log_monitoring + incident_response only.
CORE_ONLY_CREATE_ENTITLEMENTS: Dict[str, Any] = {
    "wazuh_siem": True,
    "wazuh_retention_days": 90,
    "thehive_mode": "full",
    "greenbone_enabled": False,
    "greenbone_cadence": "monthly",
    "shuffle_mode": "off",
    "zeek_enabled": False,
    "misp_enabled": False,
    "velociraptor_enabled": False,
    "continuous_compliance_enabled": False,
    "external_attack_surface_enabled": False,
    "cloud_identity_protection_enabled": False,
    "roadmap_notes": None,
}

# Full 10-card catalog for Alpha-Win / demos (all ACTIVE / INCLUDED).
DEMO_FULL_ENTITLEMENTS: Dict[str, Any] = {
    "wazuh_siem": True,
    "wazuh_retention_days": 90,
    "thehive_mode": "full",
    "greenbone_enabled": True,
    "greenbone_cadence": "monthly",
    "shuffle_mode": "standard",
    "zeek_enabled": True,
    "misp_enabled": True,
    "velociraptor_enabled": True,
    "continuous_compliance_enabled": True,
    "external_attack_surface_enabled": True,
    "cloud_identity_protection_enabled": True,
    "roadmap_notes": "Demo / QA tenant — full Service Catalog entitlements",
}

# service_catalog.key → entitlement column updates when consulting is APPROVED
CATALOG_KEY_TO_ENTITLEMENT_UPDATES: Dict[str, Dict[str, Any]] = {
    "security_automation": {"shuffle_mode": "standard"},
    "vulnerability_management": {"greenbone_enabled": True},
    "continuous_compliance": {"continuous_compliance_enabled": True},
    "external_attack_surface": {"external_attack_surface_enabled": True},
    "cloud_identity_protection": {"cloud_identity_protection_enabled": True},
    "network_detection_response": {"zeek_enabled": True},
    "network_traffic_analysis": {"zeek_enabled": True},
    "threat_intelligence": {"misp_enabled": True},
    "endpoint_forensics_deception": {"velociraptor_enabled": True},
    "endpoint_forensics": {"velociraptor_enabled": True},
}


def is_demo_full_entitlement_tenant(short_code: Optional[str]) -> bool:
    if not short_code:
        return False
    return short_code.strip().upper() in DEMO_FULL_ENTITLEMENT_SHORT_CODES


def entitlements_for_new_tenant(short_code: Optional[str]) -> Dict[str, Any]:
    """Initial entitlements payload for tenant create / registration."""
    if is_demo_full_entitlement_tenant(short_code):
        return dict(DEMO_FULL_ENTITLEMENTS)
    return dict(CORE_ONLY_CREATE_ENTITLEMENTS)


def ensure_demo_tenant_full_entitlements(tenant_id: str, short_code: Optional[str] = None) -> bool:
    """
    Force-upsert full entitlements for Alpha-Win (and other demo short codes).
    Returns True when this tenant was treated as a demo-full tenant.
    """
    code = (short_code or "").strip().upper()
    if not code:
        row = fetch_one(
            "SELECT short_code FROM tenants WHERE id = %s::uuid LIMIT 1;",
            (tenant_id,),
        )
        code = (row.get("short_code") if row else "") or ""
        code = str(code).strip().upper()

    if not is_demo_full_entitlement_tenant(code):
        return False

    from app.api.routes.entitlements import upsert_tenant_entitlements

    upsert_tenant_entitlements(tenant_id, DEMO_FULL_ENTITLEMENTS)
    logger.info("Ensured full demo entitlements for tenant %s (%s)", tenant_id, code)
    return True


def enable_entitlement_for_catalog_key(tenant_id: str, catalog_key: str) -> Optional[Dict[str, Any]]:
    """Flip the matching entitlement flag(s) when sales approves a consulting request."""
    updates = CATALOG_KEY_TO_ENTITLEMENT_UPDATES.get(catalog_key)
    if not updates:
        return None
    from app.api.routes.entitlements import DEFAULTS, upsert_tenant_entitlements
    from uuid import UUID

    from app.api.routes.entitlements import _fetch_entitlements

    current = _fetch_entitlements(UUID(tenant_id)) or {}
    merged = {
        **DEFAULTS,
        **{k: current.get(k) for k in DEFAULTS if k in current},
        **updates,
    }
    return upsert_tenant_entitlements(tenant_id, merged)


def trigger_post_enable_sync(tenant_id: str, catalog_key: str) -> Dict[str, Any]:
    """Best-effort data sync after an add-on entitlement is enabled."""
    result: Dict[str, Any] = {"catalog_key": catalog_key, "synced": False}
    try:
        if catalog_key == "vulnerability_management":
            from app.services import vmaas_service as vmaas

            result["detail"] = vmaas.run_tenant_vmaas_sync(tenant_id)
            result["synced"] = True
        elif catalog_key == "continuous_compliance":
            from app.services.sca_compliance_service import sync_tenant_sca

            result["detail"] = sync_tenant_sca(tenant_id)
            result["synced"] = True
        elif catalog_key == "external_attack_surface":
            from app.services import easm_service as easm

            result["detail"] = easm.run_tenant_scan(tenant_id)
            result["synced"] = True
        elif catalog_key == "cloud_identity_protection":
            from app.services import itdr_service as itdr

            result["detail"] = itdr.sync_tenant_itdr(tenant_id)
            result["synced"] = True
        elif catalog_key in ("network_detection_response", "network_traffic_analysis"):
            from app.services import ndr_service as ndr

            result["detail"] = ndr.sync_tenant_ndr(tenant_id)
            result["synced"] = True
        elif catalog_key == "threat_intelligence":
            from app.services import threat_intel_service as ti

            result["detail"] = ti.sync_tenant_threat_intel(tenant_id)
            result["synced"] = True
        elif catalog_key in ("endpoint_forensics_deception", "endpoint_forensics"):
            from app.services import endpoint_forensics_service as forensics

            result["detail"] = forensics.sync_tenant_forensics(tenant_id)
            result["synced"] = True
        elif catalog_key == "security_automation":
            # Shuffle entitlement alone unlocks the portal; workflows sync via existing adapters.
            result["synced"] = True
            result["detail"] = {"note": "security_automation entitlement enabled"}
    except Exception as exc:
        logger.warning(
            "Post-enable sync failed for tenant %s key %s: %s",
            tenant_id,
            catalog_key,
            exc,
        )
        result["error"] = str(exc)
    return result


CATALOG_KEY_TO_SVC_ID: Dict[str, str] = {
    "log_event_monitoring": "svc-01",
    "incident_response": "svc-02",
    "security_automation": "svc-03",
    "vulnerability_management": "svc-04",
    "continuous_compliance": "svc-05",
    "network_detection_response": "svc-06",
    "network_traffic_analysis": "svc-06",
    "threat_intelligence": "svc-07",
    "endpoint_forensics_deception": "svc-08",
    "endpoint_forensics": "svc-08",
    "external_attack_surface": "svc-09",
    "cloud_identity_protection": "svc-10",
}

CATALOG_KEY_TO_DISABLE_UPDATES: Dict[str, Dict[str, Any]] = {
    "security_automation": {"shuffle_mode": "off"},
    "vulnerability_management": {"greenbone_enabled": False},
    "continuous_compliance": {"continuous_compliance_enabled": False},
    "external_attack_surface": {"external_attack_surface_enabled": False},
    "cloud_identity_protection": {"cloud_identity_protection_enabled": False},
    "network_detection_response": {"zeek_enabled": False},
    "network_traffic_analysis": {"zeek_enabled": False},
    "threat_intelligence": {"misp_enabled": False},
    "endpoint_forensics_deception": {"velociraptor_enabled": False},
    "endpoint_forensics": {"velociraptor_enabled": False},
}


def disable_entitlement_for_catalog_key(tenant_id: str, catalog_key: str) -> Optional[Dict[str, Any]]:
    updates = CATALOG_KEY_TO_DISABLE_UPDATES.get(catalog_key)
    if not updates:
        return None
    from uuid import UUID

    from app.api.routes.entitlements import DEFAULTS, _fetch_entitlements, upsert_tenant_entitlements

    current = _fetch_entitlements(UUID(tenant_id)) or {}
    merged = {
        **DEFAULTS,
        **{k: current.get(k) for k in DEFAULTS if k in current},
        **updates,
    }
    return upsert_tenant_entitlements(tenant_id, merged)


def entitlements_to_service_ids(row: Optional[Dict[str, Any]]) -> list[str]:
    """Map tenant_entitlements flags to appliance catalogue svc-01..10."""
    data = row or {}
    ids: list[str] = []
    if data.get("wazuh_siem", True):
        ids.append("svc-01")
    hive = str(data.get("thehive_mode") or "").strip().lower()
    if hive and hive not in ("off", "none", "disabled"):
        ids.append("svc-02")
    shuffle = str(data.get("shuffle_mode") or "").strip().lower()
    if shuffle and shuffle not in ("off", "none", "disabled"):
        ids.append("svc-03")
    if data.get("greenbone_enabled"):
        ids.append("svc-04")
    if data.get("continuous_compliance_enabled"):
        ids.append("svc-05")
    if data.get("zeek_enabled"):
        ids.append("svc-06")
    if data.get("misp_enabled"):
        ids.append("svc-07")
    if data.get("velociraptor_enabled"):
        ids.append("svc-08")
    if data.get("external_attack_surface_enabled"):
        ids.append("svc-09")
    if data.get("cloud_identity_protection_enabled"):
        ids.append("svc-10")
    if "svc-01" not in ids:
        ids.insert(0, "svc-01")
    return ids


def current_tenant_service_ids(tenant_id: str) -> list[str]:
    from uuid import UUID

    from app.api.routes.entitlements import _fetch_entitlements

    return entitlements_to_service_ids(_fetch_entitlements(UUID(tenant_id)))
