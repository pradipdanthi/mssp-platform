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


def unwrap_wazuh_ingress_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize live Wazuh → control-plane webhook body shapes.

    Wazuh's stock Shuffle integration does NOT POST the raw alert JSON.
    It wraps the original alert under ``all_fields`` and adds Shuffle fields
    (severity/pretext/title/...). Accept both shapes so ingress never silently
    422s on a production integration that is "configured but wrong shape".
    """
    if not isinstance(raw, dict):
        return {}
    wrapped = raw.get("all_fields")
    if isinstance(wrapped, dict) and (
        isinstance(wrapped.get("rule"), dict) or isinstance(wrapped.get("agent"), dict)
    ):
        return wrapped
    return raw


def _extract_target_filename(raw: Dict[str, Any]) -> str:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    for key in ("targetFilename", "TargetFilename", "targetfilename"):
        val = eventdata.get(key)
        if val:
            return str(val)
    # Fallback: scan message text (Sysmon FileCreate)
    system = win.get("system") if isinstance(win.get("system"), dict) else {}
    msg = str(system.get("message") or "")
    return msg


def _extract_source_user(raw: Dict[str, Any]) -> Optional[str]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    for key in ("User", "user", "srcuser", "destinationUserName", "SubjectUserName"):
        val = eventdata.get(key) or data.get(key)
        if val:
            return str(val)[:255]
    return None


def _build_wazuh_technical_summary(raw: Dict[str, Any]) -> str:
    """Deterministic SOC evidence string from Wazuh fields (not AI)."""
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    win = data.get("win") if isinstance(data.get("win"), dict) else {}
    eventdata = win.get("eventdata") if isinstance(win.get("eventdata"), dict) else {}
    groups = rule.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    parts = [
        f"Wazuh rule {rule.get('id', 'n/a')} level {rule.get('level', 'n/a')}",
        str(rule.get("description") or "").strip(),
        f"agent={agent.get('name') or 'n/a'} id={agent.get('id') or 'n/a'} ip={agent.get('ip') or 'n/a'}",
    ]
    if groups:
        parts.append("groups=" + ",".join(str(g) for g in groups[:12]))
    target = _extract_target_filename(raw)
    if target:
        parts.append(f"target_file={target[:500]}")
    image = eventdata.get("Image") or eventdata.get("image")
    if image:
        parts.append(f"image={str(image)[:400]}")
    user = _extract_source_user(raw)
    if user:
        parts.append(f"user={user}")
    cmd = eventdata.get("CommandLine") or eventdata.get("commandLine")
    if cmd:
        parts.append(f"cmdline={str(cmd)[:600]}")
    return "; ".join(p for p in parts if p)[:4000]


def is_known_noise_file_drop(raw: Dict[str, Any]) -> bool:
    """
    Phase-1 known noise: PowerShell policy-test temp scripts.
    These fire Wazuh 92213 (critical) on nearly every elevated PowerShell run.
    """
    blob = _extract_target_filename(raw).replace("\\", "/").lower()
    return "__psscriptpolicytest_" in blob


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
    agent_ip = str(agent.get("ip") or "").strip() or None
    agent_id = str(agent.get("id") or "").strip() or None
    source_user = _extract_source_user(raw)
    target = _extract_target_filename(raw)
    desc_parts = [
        f"Wazuh rule {rule.get('id', 'n/a')} level {level}",
        f"agent={agent.get('name', 'n/a')}",
    ]
    if agent_ip:
        desc_parts.append(f"agent_ip={agent_ip}")
    if source_user:
        desc_parts.append(f"user={source_user}")
    if target:
        desc_parts.append(f"target={target[:300]}")
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

    # Phase-1: known PowerShell Temp policy-test noise must not open incidents.
    create_incident = level >= 10
    if is_known_noise_file_drop(raw):
        create_incident = False
        logger.info(
            "Wazuh ingress: suppressing auto-incident for known noise file drop "
            "(rule=%s agent=%s)",
            rule.get("id"),
            agent.get("name"),
        )

    return SocSyncRequest(
        source_tool="wazuh",
        external_alert_id=external_id[:255],
        severity=severity,  # type: ignore[arg-type]
        alert_title=title,
        alert_description=description,
        destination_host=host,
        destination_ip=agent_ip,
        source_ip=agent_ip,
        source_user=source_user,
        wazuh_agent_id=agent_id,
        technical_summary=_build_wazuh_technical_summary(raw),
        tenant_short_code=tenant_code,
        create_incident=create_incident,
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

    raw = unwrap_wazuh_ingress_payload(raw)

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
