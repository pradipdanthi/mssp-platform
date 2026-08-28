"""Customer-portal-safe labels — no third-party engine or product names."""

from __future__ import annotations

from typing import Any, Dict, Optional


def customer_safe_alert_source(source_tool: Optional[str]) -> str:
    """Map internal source_tool values to customer-facing detection labels."""
    key = (source_tool or "").strip().lower()
    mapping = {
        "wazuh": "NikTiar™ Core Telemetry",
        "fluentbit": "NikTiar™ Core Telemetry",
        "fluent-bit": "NikTiar™ Core Telemetry",
        "fluent_bit": "NikTiar™ Core Telemetry",
        "suricata": "NikTiar™ DeepSight NDR",
        "zeek": "NikTiar™ DeepSight NDR",
        "nuclei": "NikTiar™ Aegis Scanning",
        "vuls": "NikTiar™ Aegis Scanning",
        "greenbone": "NikTiar™ Aegis Scanning",
        "openvas": "NikTiar™ Aegis Scanning",
        "shuffle": "NikTiar™ Apex Orchestrator",
        "thehive": "NikTiar™ Apex Orchestrator",
        "misp": "NikTiar™ Threat Intelligence",
        "velociraptor": "NikTiar™ Spectre Forensics",
        "endpoint_kernel": "NikTiar™ Core Telemetry",
        "endpoint_audit_exec": "NikTiar™ Core Telemetry",
        "endpoint_process_create": "NikTiar™ Core Telemetry",
    }
    if key in mapping:
        return mapping[key]
    if not key:
        return "NikTiar™ Managed Detection"
    if key in ("manual", "platform", "mssp_control"):
        return "NikTiar™ Managed Detection"
    # Unknown adapter: generic branded label (never echo raw tool id to customers).
    return "NikTiar™ Managed Detection"


def customer_safe_incident_response_mode(mode: Optional[str]) -> str:
    m = (mode or "off").strip().lower()
    if m == "full":
        return "included"
    if m == "read_only":
        return "view_only"
    return "not_included"


def customer_safe_automation_mode(mode: Optional[str]) -> str:
    m = (mode or "off").strip().lower()
    if m in ("standard", "custom"):
        return "included"
    return "not_included"


def customer_service_delivery_label(deployment_mode: Optional[str], subscription_tier: Optional[str] = None) -> str:
    """
    Customer-safe description of how NikTiar delivers the contracted tier.
    Same Silver/Gold/Platinum modules — different telemetry path when Edge is used.
    """
    if (subscription_tier or "").strip().upper() == "CUSTOM":
        return (
            "Custom enterprise agreement — your contracted capabilities are listed below. "
            "Contact your account manager to change modules or upgrade to a standard tier."
        )
    mode = (deployment_mode or "cloud").strip().lower()
    if mode in ("on_prem_appliance", "cloud_appliance"):
        return (
            "NikTiar Edge — detection runs locally; raw logs stay on your network. "
            "High-fidelity alerts reach our SOC over an encrypted channel."
        )
    if mode == "hybrid":
        return (
            "Hybrid delivery — cloud SOC for cloud workloads plus NikTiar Edge where deployed. "
            "Same subscription tier and portal modules across both paths."
        )
    if mode == "on_prem_direct":
        return (
            "Cloud SOC — endpoints report to NikTiar managed infrastructure. "
            "Same subscription tier and portal modules as Edge customers."
        )
    return (
        "Cloud SOC — workloads connect to NikTiar managed infrastructure. "
        "Same subscription tier and portal modules as Edge customers."
    )


def entitlements_row_to_customer_public(row: Dict[str, Any]) -> Dict[str, Any]:
    """Build customer API entitlements payload without engine brand field names."""
    return {
        "tenant_id": row["tenant_id"],
        "subscription_tier": row.get("subscription_tier") or "SILVER",
        "service_delivery_label": customer_service_delivery_label(
            row.get("deployment_mode"),
            row.get("subscription_tier"),
        ),
        "log_monitoring_enabled": bool(row.get("wazuh_siem", True)),
        "log_retention_days": int(row.get("wazuh_retention_days") or 30),
        "incident_response": customer_safe_incident_response_mode(row.get("thehive_mode")),
        "vulnerability_management_enabled": bool(
            row.get("greenbone_enabled") or row.get("has_vmaas_data")
        ),
        "vulnerability_scan_cadence": row.get("greenbone_cadence") or "monthly",
        "continuous_compliance_enabled": bool(
            row.get("continuous_compliance_enabled")
            or row.get("has_compliance_data")
        ),
        "external_attack_surface_enabled": bool(
            row.get("external_attack_surface_enabled")
            or row.get("has_easm_data")
        ),
        "cloud_identity_protection_enabled": bool(
            row.get("cloud_identity_protection_enabled")
            or row.get("has_itdr_data")
        ),
        "security_automation": customer_safe_automation_mode(row.get("shuffle_mode")),
        "network_traffic_analysis_enabled": bool(
            row.get("zeek_enabled") or row.get("has_ndr_data")
        ),
        "threat_intelligence_enabled": bool(
            row.get("misp_enabled") or row.get("has_threat_intel_data")
        ),
        "endpoint_forensics_enabled": bool(
            row.get("velociraptor_enabled") or row.get("has_forensics_data")
        ),
        "updated_at": row.get("updated_at"),
    }
