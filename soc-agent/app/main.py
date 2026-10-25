from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.audit import audit
from app.config import settings
from app.enrichment import enrich_alert
from app.triage import triage, write_dossier

app = FastAPI(
    title="MSSP SOC Analyst Agent",
    description="Autonomous alert ingestion, enrichment, triage, and escalation dossiers.",
    version="1.0.0",
)

# In-memory recent cases for health demos (also audited to disk)
_RECENT: list[dict[str, Any]] = []


class AlertIn(BaseModel):
    title: str
    severity: str = "medium"
    description: str | None = None
    source_ip: str | None = None
    destination_ip: str | None = None
    domain: str | None = None
    hostname: str | None = None
    tenant: str | None = None
    source_platform: str | None = "synthetic"
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


def require_token(x_soc_agent_token: str | None = Header(default=None)) -> None:
    expected = settings()["ingest_token"]
    if not x_soc_agent_token or not secrets.compare_digest(x_soc_agent_token, expected):
        raise HTTPException(401, "Invalid or missing X-Soc-Agent-Token")


@app.get("/health")
def health() -> dict:
    audit_path = Path(settings()["audit_log"])
    return {
        "status": "ok",
        "service": settings()["agent_name"],
        "version": "1.0.0",
        "recent_cases": len(_RECENT),
        "audit_log_exists": audit_path.is_file(),
        "audit_bytes": audit_path.stat().st_size if audit_path.is_file() else 0,
    }


@app.get("/api/cases")
def list_cases(_: None = Depends(require_token)) -> dict:
    return {"count": len(_RECENT), "cases": list(reversed(_RECENT[-50:]))}


@app.post("/api/v1/ingest")
def ingest(alert: AlertIn, _: None = Depends(require_token)) -> dict:
    cfg = settings()
    payload = alert.model_dump()
    audit(cfg["audit_log"], "ingest.received", {"title": alert.title, "severity": alert.severity})

    enrichment = enrich_alert(payload)
    audit(
        cfg["audit_log"],
        "enrichment.done",
        {
            "title": alert.title,
            "src_class": enrichment["source_reputation"]["classification"],
            "mitre": enrichment["mitre"],
        },
    )

    result = triage(payload, enrichment)
    dossier_id = None
    if result["disposition"] in ("escalate", "investigate"):
        dossier_id = write_dossier(cfg["dossier_dir"], payload, enrichment, result)
        audit(
            cfg["audit_log"],
            "dossier.created",
            {"dossier_id": dossier_id, "disposition": result["disposition"]},
        )

    case = {
        "title": alert.title,
        "tenant": alert.tenant,
        "triage": result,
        "enrichment": enrichment,
        "dossier_id": dossier_id,
    }
    _RECENT.append(case)
    if len(_RECENT) > 200:
        del _RECENT[:-200]

    audit(
        cfg["audit_log"],
        "triage.complete",
        {
            "title": alert.title,
            "score": result["score"],
            "disposition": result["disposition"],
            "classification": result["classification"],
            "dossier_id": dossier_id,
        },
    )

    return {
        "ok": True,
        "triage": result,
        "enrichment": {
            "source_reputation": enrichment["source_reputation"],
            "destination_reputation": enrichment["destination_reputation"],
            "mitre": enrichment["mitre"],
        },
        "dossier_id": dossier_id,
    }
