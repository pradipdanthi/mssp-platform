"""
KB-082: All-device SOC alert taxonomy (derived at read time — no schema change).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# Stable API slugs (query param asset_category)
TAXONOMY_SLUGS = (
    "all",
    "uncategorized",
    "endpoints_windows",
    "endpoints_linux",
    "endpoints_vm_container",
    "network_ids_sensors",
    "network_hardware",
    "security_edge_appliances",
    "databases_storage",
    "identity_access",
    "iot_ot",
    "vuln_web_app",
    "vuln_infrastructure",
)

TAXONOMY_LABELS: Dict[str, str] = {
    "all": "All Devices",
    "uncategorized": "Uncategorized",
    "endpoints_windows": "Windows Systems",
    "endpoints_linux": "Linux & Unix Systems",
    "endpoints_vm_container": "Virtual Machines & Containers",
    "network_ids_sensors": "Network IDS / Sensors",
    "network_hardware": "Network Hardware",
    "security_edge_appliances": "Firewalls, WAFs, VPN & EDR Controllers",
    "databases_storage": "Databases & Storage Infrastructure",
    "identity_access": "Identity, Access & Management",
    "iot_ot": "IoT, OT & Peripheral Devices",
    "vuln_web_app": "Web Application & API Security",
    "vuln_infrastructure": "Infrastructure CVE Assessment",
}

# UI tree (parent slug -> child slugs); "all" is virtual root
TAXONOMY_TREE: List[Dict[str, Any]] = [
    {
        "slug": "endpoints",
        "label": "Endpoints & Workloads",
        "children": [
            "endpoints_windows",
            "endpoints_linux",
            "endpoints_vm_container",
        ],
    },
    {
        "slug": "network",
        "label": "Network & Connectivity",
        "children": ["network_ids_sensors", "network_hardware"],
    },
    {
        "slug": "security_edge",
        "label": "Security & Edge Appliances",
        "children": ["security_edge_appliances"],
    },
    {
        "slug": "data",
        "label": "Databases & Storage Infrastructure",
        "children": ["databases_storage"],
    },
    {
        "slug": "identity",
        "label": "Identity, Access & Management",
        "children": ["identity_access"],
    },
    {
        "slug": "iot",
        "label": "IoT, OT & Peripheral Devices",
        "children": ["iot_ot"],
    },
    {
        "slug": "posture",
        "label": "Vulnerabilities & Security Posture",
        "children": ["vuln_web_app", "vuln_infrastructure"],
    },
]


def _text_blob(row: Dict[str, Any]) -> str:
    parts = [
        str(row.get("source_tool") or ""),
        str(row.get("alert_title") or ""),
        str(row.get("alert_description") or ""),
        str(row.get("destination_host") or ""),
        str(row.get("source_user") or ""),
    ]
    raw = row.get("raw_event")
    if isinstance(raw, dict):
        try:
            parts.append(json.dumps(raw).lower())
        except (TypeError, ValueError):
            pass
    elif raw:
        parts.append(str(raw).lower())
    return " ".join(parts).lower()


def _agent_os(raw: Dict[str, Any]) -> str:
    agent = raw.get("agent")
    if isinstance(agent, dict):
        os_info = agent.get("os") or agent.get("os_name")
        if isinstance(os_info, dict):
            return str(os_info.get("name") or os_info.get("platform") or "").lower()
        return str(os_info or "").lower()
    return ""


def derive_asset_category(row: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns (asset_category slug, device_type short label).
    Never raises — unknown inputs map to uncategorized.
    """
    tool = (row.get("source_tool") or "").strip().lower()
    blob = _text_blob(row)
    raw = row.get("raw_event") if isinstance(row.get("raw_event"), dict) else {}
    host = str(row.get("destination_host") or row.get("asset_hostname") or "").lower()
    asset_os = str(row.get("asset_os_name") or row.get("asset_type") or "").lower()

    # Linked inventory OS/type is authoritative when present.
    if "windows" in asset_os or host.startswith("win-"):
        return "endpoints_windows", "windows_host"
    if any(x in asset_os for x in ("linux", "ubuntu", "debian", "rhel", "centos", "unix")):
        return "endpoints_linux", "linux_host"

    # Explicit network appliance ingest (syslog from firewall/switch — no endpoint agent id).
    if tool in ("network_appliance", "firewall", "syslog_network") or (
        isinstance(raw.get("decoder"), dict)
        and str((raw.get("decoder") or {}).get("name") or "").lower()
        in ("fortigate-firewall", "pfsense", "vyos", "opnsense", "cisco-ios")
    ):
        return "security_edge_appliances", "network_appliance"

    if tool in ("suricata", "zeek"):
        return "network_ids_sensors", tool or "network_sensor"
    if tool == "nuclei":
        return "vuln_web_app", "web_scanner"
    if tool in ("vuls", "greenbone", "openvas"):
        return "vuln_infrastructure", tool

    if tool == "wazuh" or tool in ("shuffle", "thehive") or not tool:
        os_name = _agent_os(raw) or asset_os
        if "windows" in os_name or "win" in os_name.split() or host.startswith("win-"):
            return "endpoints_windows", "windows_host"
        if any(x in os_name for x in ("linux", "ubuntu", "debian", "rhel", "centos", "unix")):
            if any(k in blob for k in ("docker", "kubernetes", "k8s", "container", "pod", "ecs", "eks")):
                return "endpoints_vm_container", "container_workload"
            return "endpoints_linux", "linux_host"

        if any(k in blob for k in ("docker", "kubernetes", "k8s", "containerd", "pod ", " kube")):
            return "endpoints_vm_container", "container_workload"

        if any(
            k in blob
            for k in (
                "firewall",
                "palo alto",
                "fortinet",
                "fortigate",
                "pfsense",
                "vyos",
                "opnsense",
                "network_appliance",
                "syslog",
                "filterlog",
                " waf",
                "vpn",
                "edr",
                "crowdstrike",
                "sentinelone",
            )
        ):
            # Prefer explicit network appliance label for firewall/switch syslog.
            if any(
                k in blob
                for k in (
                    "fortigate",
                    "pfsense",
                    "vyos",
                    "opnsense",
                    "filterlog",
                    "network_appliance",
                )
            ):
                return "security_edge_appliances", "network_appliance"
            return "security_edge_appliances", "security_appliance"

        if any(
            k in blob
            for k in (
                "mysql",
                "postgres",
                "postgresql",
                "mongodb",
                "oracle db",
                "mssql",
                "sql server",
                "redis",
                "nas ",
                " san ",
                "s3 bucket",
                "blob storage",
            )
        ):
            return "databases_storage", "data_store"

        if any(
            k in blob
            for k in (
                "active directory",
                "ad ds",
                "ldap",
                "keycloak",
                " okta",
                " azure ad",
                "entra",
                "iam",
                "kerberos",
            )
        ):
            return "identity_access", "identity_system"

        if any(
            k in blob
            for k in (
                "printer",
                "cctv",
                "camera",
                "iot",
                " scada",
                " plc",
                "modbus",
                "embedded",
                "smart sensor",
            )
        ):
            return "iot_ot", "iot_ot_device"

        if any(
            k in blob
            for k in (
                "cisco",
                "switch",
                "router",
                "juniper",
                "arista",
                "load balancer",
                " f5",
                "access point",
                " wlan",
                "snmp",
            )
        ):
            return "network_hardware", "network_device"

        if any(k in blob for k in ("suricata", "eve.json", "zeek", "notice.log")):
            return "network_ids_sensors", "network_sensor"

        if any(k in blob for k in ("cve-", "cvss", "nuclei", "openvas", "vuls")):
            if "http" in blob or "url" in blob or "web" in blob:
                return "vuln_web_app", "web_scanner"
            return "vuln_infrastructure", "cve_scan"

        if tool == "wazuh":
            if "windows" in blob or host.startswith("win-"):
                return "endpoints_windows", "windows_host"
            if any(x in blob for x in ("linux", "sshd", "sudo", "/var/log/auth")):
                return "endpoints_linux", "linux_host"

    return "uncategorized", "unknown"


def enrich_alert_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Attach taxonomy fields without mutating raw_event."""
    from app.services.soc_alert_synthesis import apply_soc_enrichment

    out = dict(row)
    cat, device = derive_asset_category(out)
    out["asset_category"] = cat
    out["device_type"] = device
    out["asset_category_label"] = TAXONOMY_LABELS.get(cat, cat)
    out["contextual"] = build_contextual_fields(out, cat)
    return apply_soc_enrichment(out)


def build_contextual_fields(row: Dict[str, Any], category: str) -> Dict[str, Any]:
    """Customer-safe SOC display helpers for dynamic table columns."""
    ctx: Dict[str, Any] = {}
    if category.startswith("endpoints") or category == "uncategorized":
        ctx["hostname"] = row.get("destination_host") or row.get("asset_hostname")
        ctx["source_ip"] = row.get("source_ip")
        ctx["user"] = row.get("source_user")
        ctx["os_hint"] = row.get("device_type")
        ctx["rule_or_process"] = row.get("alert_title")
    elif category in ("network_ids_sensors", "network_hardware", "security_edge_appliances"):
        ctx["source_endpoint"] = _format_ip_port(row.get("source_ip"), None)
        ctx["dest_endpoint"] = _format_ip_port(row.get("destination_ip"), row.get("destination_host"))
        ctx["protocol"] = _extract_protocol(row)
        ctx["action"] = _extract_action(row)
    elif category == "databases_storage":
        ctx["resource_name"] = row.get("destination_host") or row.get("alert_title")
        ctx["user_or_role"] = row.get("source_user")
        ctx["access_event"] = row.get("alert_title")
    elif category.startswith("vuln_"):
        ctx["cve_id"] = _extract_cve(row)
        ctx["target"] = row.get("destination_host") or row.get("destination_ip")
        ctx["remediation_hint"] = row.get("ai_recommended_action") or row.get("ai_plain_summary")
    else:
        ctx["summary"] = row.get("ai_plain_summary") or row.get("alert_title")
    return ctx


def _format_ip_port(ip: Any, host: Any) -> str:
    if host and ip:
        return f"{host} ({ip})"
    return str(host or ip or "—")


def _extract_protocol(row: Dict[str, Any]) -> Optional[str]:
    raw = row.get("raw_event")
    if isinstance(raw, dict):
        for key in ("proto", "protocol", "app_proto"):
            if raw.get(key):
                return str(raw[key])
        data = raw.get("data")
        if isinstance(data, dict) and data.get("proto"):
            return str(data["proto"])
    return None


def _extract_action(row: Dict[str, Any]) -> Optional[str]:
    blob = _text_blob(row)
    for action in ("drop", "reject", "alert", "pass", "allow"):
        if action in blob:
            return action
    return None


def _extract_cve(row: Dict[str, Any]) -> Optional[str]:
    import re

    blob = f"{row.get('alert_title') or ''} {row.get('alert_description') or ''}"
    m = re.search(r"CVE-\d{4}-\d+", blob, re.I)
    return m.group(0).upper() if m else None


def filter_by_asset_category(rows: List[Dict[str, Any]], asset_category: Optional[str]) -> List[Dict[str, Any]]:
    if not asset_category or asset_category == "all":
        return rows
    return [r for r in rows if r.get("asset_category") == asset_category]


def taxonomy_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {slug: 0 for slug in TAXONOMY_SLUGS if slug != "all"}
    counts["all"] = len(rows)
    for row in rows:
        cat = row.get("asset_category") or "uncategorized"
        counts[cat] = counts.get(cat, 0) + 1
    return counts
