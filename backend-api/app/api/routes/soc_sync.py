"""KB-061/063: SOC sync ingest + instant Wazuh dual-path ingress."""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.schemas.soc_sync import SocSyncRequest, SocSyncResponse
from app.db.session import fetch_one
from app.services.soc_sync_service import TenantNotFoundError, sync_soc_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/soc", tags=["soc-sync"])


def _read_secret_file(*candidates: str) -> str:
    for candidate in candidates:
        try:
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            continue
    return ""


def _configured_sync_key() -> str:
    """Prefer env; fall back to gitignored file paths."""
    direct = (os.getenv("SOC_SYNC_API_KEY") or "").strip()
    if direct:
        return direct
    key_file = (os.getenv("SOC_SYNC_API_KEY_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/soc_sync_api_key",
        "/opt/mssp-control/.secrets/soc_sync_api_key",
    )


def _wazuh_ingress_token() -> str:
    env = (os.getenv("WAZUH_INGRESS_TOKEN") or "").strip()
    if env:
        return env
    key_file = (os.getenv("WAZUH_INGRESS_TOKEN_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/wazuh_ingress_token",
        "/opt/mssp-control/.secrets/wazuh_ingress_token",
    )


def _shuffle_webhook_url() -> str:
    env = (os.getenv("SHUFFLE_WEBHOOK_URL") or "").strip()
    if env:
        return env
    key_file = (os.getenv("SHUFFLE_WEBHOOK_URL_FILE") or "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return _read_secret_file(
        "/run/secrets/shuffle_webhook_url",
        "/opt/mssp-control/.secrets/shuffle_webhook_url",
    )


def _require_sync_key(provided: Optional[str]) -> None:
    expected = _configured_sync_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SOC sync is not configured",
        )
    if not provided or not hmac.compare_digest(provided.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SOC sync credentials",
        )


def _level_to_severity(level: int) -> str:
    if level >= 15:
        return "critical"
    if level >= 10:
        return "high"
    if level >= 7:
        return "medium"
    return "low"


def _normalize_wazuh_alert(raw: Dict[str, Any]) -> SocSyncRequest:
    from app.services.tenant_engine_provisioner import resolve_short_code_by_wazuh_group

    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    try:
        level = int(rule.get("level", 10))
    except (TypeError, ValueError):
        level = 10
    severity = _level_to_severity(level)
    title = str(rule.get("description") or raw.get("title") or "Wazuh alert")[:500]
    external_id = str(raw.get("id") or raw.get("uuid") or rule.get("id") or "")
    if not external_id:
        external_id = f"wazuh-{rule.get('id', 'unknown')}-{agent.get('id', 'na')}-{level}"
    host = str(agent.get("name") or raw.get("hostname") or "")[:255] or None
    desc_parts = [
        f"Wazuh rule {rule.get('id', 'n/a')} level {level}",
        f"agent={agent.get('name', 'n/a')}",
    ]
    description = "; ".join(desc_parts)[:4000]

    # Resolve tenant from Wazuh agent group binding (KB-072).
    # Fail-closed: no DEMO fallback. Optional env override only when explicitly set.
    # Shuffle/Wazuh hook payloads often omit agent.group — look up via Manager API.
    env_default = (os.getenv("WAZUH_DEFAULT_TENANT_SHORT_CODE") or "").strip().upper()
    tenant_code: Optional[str] = env_default or None
    groups = agent.get("groups") or agent.get("group") or []
    if isinstance(groups, str):
        groups = [groups]
    labels = agent.get("labels") if isinstance(agent.get("labels"), dict) else {}
    candidates = [str(g) for g in groups if g]
    for key, val in labels.items():
        if str(key).lower() in ("group", "tenant_group", "wazuh_group"):
            candidates.append(str(val))
        if str(val).startswith("tenant_"):
            candidates.append(str(val))
    if not any(str(g).startswith("tenant_") for g in candidates):
        agent_id = str(agent.get("id") or "").strip()
        if agent_id:
            try:
                from app.services import wazuh_client

                if wazuh_client.credentials_configured():
                    candidates.extend(wazuh_client.get_agent_groups(agent_id))
            except Exception:
                logger.exception(
                    "Wazuh agent group lookup failed for agent_id=%s", agent_id
                )
    for g in candidates:
        mapped = resolve_short_code_by_wazuh_group(g)
        if mapped:
            tenant_code = mapped
            break
        if g.startswith("tenant_"):
            # Convention fallback: tenant_ACME → ACME
            tenant_code = g[len("tenant_") :].upper()
            break

    if not tenant_code:
        raise ValueError(
            "Unmapped Wazuh agent: no tenant group binding and no WAZUH_DEFAULT_TENANT_SHORT_CODE"
        )

    return SocSyncRequest(
        source_tool="wazuh",
        external_alert_id=external_id[:255],
        severity=severity,  # type: ignore[arg-type]
        alert_title=title,
        alert_description=description,
        destination_host=host,
        tenant_short_code=tenant_code,
        create_incident=level >= 10,
        customer_visible_summary=f"SOC is reviewing: {title}"[:4000],
        business_impact=(
            "Under SOC investigation. Details appear when approved for customer view."
        ),
    )


def _forward_to_shuffle(raw_body: bytes) -> None:
    url = _shuffle_webhook_url()
    if not url:
        logger.warning("Shuffle webhook URL not configured; skip forward")
        return
    req = urllib.request.Request(
        url,
        data=raw_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
            logger.info(
                "Forwarded Wazuh alert to Shuffle webhook status=%s",
                getattr(resp, "status", "?"),
            )
    except Exception:
        logger.exception("Failed forwarding Wazuh alert to Shuffle webhook")


@router.post(
    "/sync",
    response_model=SocSyncResponse,
    status_code=status.HTTP_201_CREATED,
)
def sync_from_soc(
    payload: SocSyncRequest,
    response: Response,
    x_soc_sync_key: Optional[str] = Header(default=None, alias="X-SOC-Sync-Key"),
) -> Dict[str, Any]:
    """Accept one normalized SOC alert; never customer-visible by default."""
    _require_sync_key(x_soc_sync_key)

    try:
        result, duplicate = sync_soc_alert(payload)
    except TenantNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    except Exception:
        logger.exception("Unexpected error during SOC sync")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SOC sync failed due to an internal error",
        )

    if duplicate:
        response.status_code = status.HTTP_200_OK

    return {
        "alert_id": result["alert_id"],
        "incident_id": result.get("incident_id"),
        "incident_number": result.get("incident_number"),
        "duplicate": duplicate,
        "customer_visible": result["customer_visible"],
        "status": result["status"],
        "message": (
            "Alert already synced"
            if duplicate
            else "Alert synced for SOC triage"
        ),
    }


@router.post("/hooks/wazuh/{token}")
async def wazuh_instant_ingress(token: str, request: Request) -> Dict[str, Any]:
    """
    Instant path for SOC SLA:
    1) Normalize + store in control plane immediately
    2) Forward original JSON to Shuffle (TheHive ticket path) in background
    """
    expected = _wazuh_ingress_token()
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    raw_body = await request.body()
    try:
        raw = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid alert payload")

    try:
        payload = _normalize_wazuh_alert(raw)
        result, duplicate = sync_soc_alert(payload)
        tenant_row = fetch_one(
            "SELECT id::text AS id FROM tenants WHERE short_code = %s;",
            (payload.tenant_short_code.upper(),),
        )
        if tenant_row and result.get("alert_id"):
            from app.services.edr_ingress import persist_wazuh_alert_enrichment

            persist_wazuh_alert_enrichment(
                result["alert_id"],
                tenant_row["id"],
                raw,
            )
    except ValueError as exc:
        logger.warning("Wazuh ingress rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Alert tenant could not be resolved",
        )
    except TenantNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    except Exception:
        logger.exception("Instant Wazuh ingress failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ingress failed due to an internal error",
        )

    threading.Thread(target=_forward_to_shuffle, args=(raw_body,), daemon=True).start()

    return {
        "success": True,
        "duplicate": duplicate,
        "alert_id": result["alert_id"],
        "incident_number": result.get("incident_number"),
        "forwarded_to_shuffle": bool(_shuffle_webhook_url()),
        "message": "Alert ingested instantly for SOC dashboards",
    }
