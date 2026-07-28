"""KB-083: MITRE ATT&CK extraction from Wazuh / Sysmon / Sigma metadata."""

from __future__ import annotations

from typing import Any, Dict, List


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def mitre_from_wazuh_alert(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Build mitre_mapping JSON for security_alerts / API responses."""
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    mitre = rule.get("mitre") if isinstance(rule.get("mitre"), dict) else {}
    tactics = _as_list(mitre.get("tactic")) or _as_list(mitre.get("tactics"))
    technique_ids = _as_list(mitre.get("id")) or _as_list(mitre.get("technique_id"))
    technique_names = _as_list(mitre.get("technique")) or _as_list(mitre.get("techniques"))

    techniques: List[Dict[str, str]] = []
    for idx, tid in enumerate(technique_ids):
        name = technique_names[idx] if idx < len(technique_names) else ""
        techniques.append({"id": tid, "name": name})

    if not techniques and rule.get("id"):
        techniques.append({"id": str(rule.get("id")), "name": str(rule.get("description") or "")[:200]})

    tags = _as_list(rule.get("groups"))
    for tag in tags:
        if tag.lower().startswith("attack.t"):
            techniques.append({"id": tag.split(".")[-1].upper(), "name": tag})

    return {
        "tactics": tactics,
        "techniques": techniques,
        "source": "wazuh_rule",
    }


def customer_safe_mitre(mapping: Any) -> Dict[str, Any]:
    """Strip internal noise; keep tactic/technique labels for customer UI."""
    if not isinstance(mapping, dict):
        return {"tactics": [], "techniques": []}
    tactics = [str(t) for t in (mapping.get("tactics") or []) if t][:20]
    techniques: List[Dict[str, str]] = []
    for item in mapping.get("techniques") or []:
        if isinstance(item, dict):
            techniques.append(
                {
                    "id": str(item.get("id") or "")[:32],
                    "name": str(item.get("name") or "")[:200],
                }
            )
    return {"tactics": tactics, "techniques": techniques[:30]}
