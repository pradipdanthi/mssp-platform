"""Automated triage + severity scoring + dossier creation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _base_score(sev: str) -> int:
    return {"informational": 5, "low": 20, "medium": 45, "high": 70, "critical": 90}.get(
        (sev or "medium").lower(), 45
    )


def triage(alert: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    sev = str(alert.get("severity") or "medium").lower()
    score = _base_score(sev)
    reasons: list[str] = [f"base_severity:{sev}"]

    src = enrichment.get("source_reputation") or {}
    dst = enrichment.get("destination_reputation") or {}
    mitre = enrichment.get("mitre") or []

    if src.get("classification") == "benign_local":
        score -= 25
        reasons.append("source_private_network")
    if src.get("classification") == "malicious":
        score += 30
        reasons.append("source_malicious_reputation")
    if dst and dst.get("classification") == "malicious":
        score += 25
        reasons.append("destination_malicious_reputation")
    if mitre:
        score += 10 * min(len(mitre), 3)
        reasons.append(f"mitre_hits:{len(mitre)}")

    title = str(alert.get("title") or "").lower()
    if "brute" in title and src.get("classification") == "benign_local":
        score = min(score, 15)
        reasons.append("benign_brute_force_pattern")

    score = max(0, min(100, score))
    if score >= 80:
        disposition = "escalate"
        classification = "malicious"
    elif score >= 50:
        disposition = "investigate"
        classification = "suspicious"
    elif score >= 25:
        disposition = "monitor"
        classification = "suspicious_low"
    else:
        disposition = "auto_close_benign"
        classification = "benign"

    return {
        "score": score,
        "disposition": disposition,
        "classification": classification,
        "reasons": reasons,
        "severity_in": sev,
        "mitre_ids": [m["technique_id"] for m in mitre],
    }


def write_dossier(dossier_dir: str, alert: dict, enrichment: dict, triage_result: dict) -> str:
    Path(dossier_dir).mkdir(parents=True, exist_ok=True)
    dossier_id = f"DOS-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    path = Path(dossier_dir) / f"{dossier_id}.json"
    doc = {
        "dossier_id": dossier_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "alert": alert,
        "enrichment": enrichment,
        "triage": triage_result,
        "escalation": {
            "required": triage_result["disposition"] == "escalate",
            "recommended_actions": (
                [
                    "Contain endpoint / block C2 indicators",
                    "Open case in MSSP control plane",
                    "Notify SOC manager",
                ]
                if triage_result["disposition"] == "escalate"
                else ["No escalation — auto-triage complete"]
            ),
        },
    }
    path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return dossier_id
