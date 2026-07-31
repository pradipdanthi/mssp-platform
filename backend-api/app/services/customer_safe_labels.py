"""Customer-portal-safe labels — no third-party engine or product names."""

from __future__ import annotations

from typing import Any, Dict, Optional


def customer_safe_alert_source(source_tool: Optional[str]) -> str:
    """Map internal source_tool values to customer-facing detection labels."""
    key = (source_tool or "").strip().lower()
    mapping = {
        "wazuh": "Endpoint monitoring",
        "suricata": "Network monitoring",
        "zeek": "Network traffic analysis",
        "nuclei": "Vulnerability assessment",
        "vuls": "Vulnerability assessment",
        "greenbone": "Vulnerability assessment",
        "openvas": "Vulnerability assessment",
        "shuffle": "Security automation",
        "thehive": "Incident response",
        "misp": "Threat intelligence",
        "velociraptor": "Endpoint forensics",
    }
    if key in mapping:
        return mapping[key]
    if not key:
        return "Managed detection"
    if key in ("manual", "platform", "mssp_control"):
        return "Managed detection"
    # Unknown adapter: generic label (never echo raw tool id to customers).
    return "Managed detection"


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


def entitlements_row_to_customer_public(row: Dict[str, Any]) -> Dict[str, Any]:
    """Build customer API entitlements payload without engine brand field names."""
    return {
        "tenant_id": row["tenant_id"],
        "log_monitoring_enabled": bool(row.get("wazuh_siem", True)),
        "log_retention_days": int(row.get("wazuh_retention_days") or 30),
        "incident_response": customer_safe_incident_response_mode(row.get("thehive_mode")),
        "vulnerability_management_enabled": bool(row.get("greenbone_enabled")),
        "vulnerability_scan_cadence": row.get("greenbone_cadence") or "monthly",
        "continuous_compliance_enabled": bool(
            row.get("continuous_compliance_enabled")
            or row.get("has_compliance_data")
        ),
        "security_automation": customer_safe_automation_mode(row.get("shuffle_mode")),
        "network_traffic_analysis_enabled": bool(row.get("zeek_enabled")),
        "threat_intelligence_enabled": bool(row.get("misp_enabled")),
        "endpoint_forensics_enabled": bool(row.get("velociraptor_enabled")),
        "updated_at": row.get("updated_at"),
    }
