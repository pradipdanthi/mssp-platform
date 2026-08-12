"""Service Catalog pricing defaults + entitlement adoption helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Mirrors frontend SERVICE_CATALOG defaults (seed / fallback when DB empty).
CATALOG_DEFAULTS: List[Dict[str, Any]] = [
    {
        "service_key": "log_event_monitoring",
        "service_name": "Log & Event Monitoring",
        "pricing_display": "Included in Core Plan",
        "competitor_value": "Competitor value: ~$4.00 / endpoint / month",
        "is_core": True,
        "requestable": False,
        "sort_order": 10,
    },
    {
        "service_key": "incident_response",
        "service_name": "Incident Response & Casework",
        "pricing_display": "Included in Core Plan",
        "competitor_value": "Competitor value: ~$1,500 / month SOC retainer",
        "is_core": True,
        "requestable": False,
        "sort_order": 20,
    },
    {
        "service_key": "security_automation",
        "service_name": "Security Automation & Containment",
        "pricing_display": "Available — request consulting",
        "competitor_value": "Competitor value: ~$2,000 / month SOAR engine",
        "is_core": False,
        "requestable": True,
        "sort_order": 30,
    },
    {
        "service_key": "vulnerability_management",
        "service_name": "Vulnerability Management (VMaaS)",
        "pricing_display": "$4.00 / device / month",
        "competitor_value": "Competitor avg: $6.50–$9.00 / device / month",
        "is_core": False,
        "requestable": True,
        "sort_order": 40,
    },
    {
        "service_key": "continuous_compliance",
        "service_name": "Continuous Compliance & Hardening (CaaS)",
        "pricing_display": "$3.50 / device / month",
        "competitor_value": "Competitor avg: $5.00–$8.00 / device / month",
        "is_core": False,
        "requestable": True,
        "sort_order": 50,
    },
    {
        "service_key": "network_detection_response",
        "service_name": "Network Detection & Response (NDR)",
        "pricing_display": "$250.00 / network sensor / month",
        "competitor_value": "Uncapped data ingestion — no per-GB fees",
        "is_core": False,
        "requestable": True,
        "sort_order": 60,
    },
    {
        "service_key": "threat_intelligence",
        "service_name": "Threat Intelligence & Enrichment",
        "pricing_display": "$150.00 / tenant / month",
        "competitor_value": "Flat tenant fee",
        "is_core": False,
        "requestable": True,
        "sort_order": 70,
    },
    {
        "service_key": "endpoint_forensics_deception",
        "service_name": "Endpoint Forensics & Deception Hunting",
        "pricing_display": "$5.00 / endpoint / month",
        "competitor_value": "Per-endpoint advanced response",
        "is_core": False,
        "requestable": True,
        "sort_order": 80,
    },
    {
        "service_key": "external_attack_surface",
        "service_name": "External Attack Surface Management (EASM)",
        "pricing_display": "$199.00 / primary domain / month",
        "competitor_value": "Zero agents required",
        "is_core": False,
        "requestable": True,
        "sort_order": 90,
    },
    {
        "service_key": "cloud_identity_protection",
        "service_name": "Cloud & Identity Protection (ITDR)",
        "pricing_display": "$3.00 / user seat / month",
        "competitor_value": "Microsoft 365 / Entra ID / AWS",
        "is_core": False,
        "requestable": True,
        "sort_order": 100,
    },
]

# SQL predicate fragment for "service is active for tenant" adoption counts.
ADOPTION_SQL: Dict[str, Tuple[str, Tuple[Any, ...]]] = {
    "log_event_monitoring": ("COALESCE(e.wazuh_siem, FALSE) = TRUE", ()),
    "incident_response": ("COALESCE(e.thehive_mode, 'off') <> 'off'", ()),
    "security_automation": ("COALESCE(e.shuffle_mode, 'off') <> 'off'", ()),
    "vulnerability_management": ("COALESCE(e.greenbone_enabled, FALSE) = TRUE", ()),
    "continuous_compliance": ("COALESCE(e.continuous_compliance_enabled, FALSE) = TRUE", ()),
    "network_detection_response": ("COALESCE(e.zeek_enabled, FALSE) = TRUE", ()),
    "threat_intelligence": ("COALESCE(e.misp_enabled, FALSE) = TRUE", ()),
    "endpoint_forensics_deception": ("COALESCE(e.velociraptor_enabled, FALSE) = TRUE", ()),
    "external_attack_surface": ("COALESCE(e.external_attack_surface_enabled, FALSE) = TRUE", ()),
    "cloud_identity_protection": ("COALESCE(e.cloud_identity_protection_enabled, FALSE) = TRUE", ()),
}


def default_for(service_key: str) -> Optional[Dict[str, Any]]:
    for row in CATALOG_DEFAULTS:
        if row["service_key"] == service_key:
            return dict(row)
    return None
