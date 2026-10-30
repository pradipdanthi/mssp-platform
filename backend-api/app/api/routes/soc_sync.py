"""KB-061/063: SOC sync ingest + instant Wazuh dual-path ingress."""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.schemas.soc_sync import SocSyncRequest, SocSyncResponse
from app.db.session import fetch_all, fetch_one
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


def detect_ingress_source_tool(raw: Dict[str, Any]) -> str:
    """
    Infer the originating sensor/integration for a Wazuh webhook payload.

    Suricata and Zeek alerts are often forwarded through Wazuh Manager; inspect
    rule groups, integration fields, decoder/location, and log text before
    defaulting to ``wazuh``.
    """
    if not isinstance(raw, dict):
        return "wazuh"

    parts: list[str] = []

    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    groups = rule.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    for group in groups:
        parts.append(str(group))

    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    for key in ("integration", "source", "type", "decoder", "program"):
        val = data.get(key)
        if val:
            parts.append(str(val))

    decoder = raw.get("decoder") if isinstance(raw.get("decoder"), dict) else {}
    decoder_name = decoder.get("name")
    if decoder_name:
        parts.append(str(decoder_name))

    for key in ("location", "full_log", "predecoder", "manager", "cluster"):
        val = raw.get(key)
        if val:
            parts.append(str(val))

    for key in ("source", "integration"):
        val = raw.get(key)
        if val:
            parts.append(str(val))

    blob = " ".join(parts).lower()
    if "suricata" in blob:
        return "suricata"
    if "zeek" in blob:
        return "zeek"
    return "wazuh"


def resolve_tenant_by_asset_ip(*ips: Optional[str]) -> Optional[Dict[str, str]]:
    """
    NDR attribution: map a network alert to the tenant that owns the monitored IP.

    A sensor watches a network segment, not a tenant, so its Wazuh agent is not
    tenant-bound. Fail-closed: an IP registered to more than one tenant (private
    ranges overlap across customers) is ambiguous and is not attributed.
    """
    for ip in ips:
        ip = (ip or "").strip()
        if not ip:
            continue
        try:
            rows = fetch_all(
                """
                SELECT DISTINCT t.short_code, p.hostname
                FROM protected_assets p
                JOIN tenants t ON t.id = p.tenant_id
                WHERE p.ip_address = %s::inet
                  AND coalesce(lower(p.status), 'active')
                      NOT IN ('retired', 'decommissioned', 'deleted');
                """,
                (ip,),
            )
        except Exception:  # noqa: BLE001
            logger.exception("NDR asset-IP tenant lookup failed ip=%s", ip)
            return None
        tenants = {str(r["short_code"]) for r in rows}
        if len(tenants) == 1:
            return {
                "tenant_short_code": tenants.pop(),
                "hostname": str(rows[0].get("hostname") or ""),
                "ip": ip,
            }
        if len(tenants) > 1:
            logger.warning("NDR asset IP %s is registered to %d tenants; not attributing", ip, len(tenants))
    return None


def is_known_noise_file_drop(raw: Dict[str, Any]) -> bool:
    """
    Phase-1 known noise: PowerShell policy-test temp scripts.
    These fire Wazuh 92213 (critical) on nearly every elevated PowerShell run.
    """
    blob = _extract_target_filename(raw).replace("\\", "/").lower()
    return "__psscriptpolicytest_" in blob


_VD_GROUPS = frozenset(
    {
        "vulnerability-detector",
        "vulnerability-detection",
        "vulnerability_detector",
    }
)
_VD_TITLE = re.compile(r"^CVE-\d{4}-\d+\s+affects\s+", re.I)


def is_vulnerability_inventory_alert(raw: Dict[str, Any]) -> bool:
    """Wazuh vulnerability-detector emits one alert per CVE.

    Those rows are inventory findings (unpatched Evaluation SKUs produce
    hundreds at once). They are not SOC detections and must not open
    incidents or fill the analyst queue.
    """
    rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
    groups = rule.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    gset = {str(g).strip().lower() for g in groups if str(g).strip()}
    if gset & _VD_GROUPS:
        return True
    try:
        rid = int(str(rule.get("id") or "0"))
    except (TypeError, ValueError):
        rid = 0
    if 23500 <= rid <= 23599:
        return True
    title = str(rule.get("description") or raw.get("title") or "").strip()
    return bool(_VD_TITLE.match(title))


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

    source_tool = detect_ingress_source_tool(raw)
    net_src: Optional[str] = None
    net_dst: Optional[str] = None
    if source_tool in ("suricata", "zeek"):
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        # Suricata eve uses src_ip/dest_ip; Zeek notices often use src/dst or id.orig_h/id.resp_h.
        net_src = (
            str(
                data.get("src_ip")
                or data.get("src")
                or data.get("id.orig_h")
                or data.get("id_orig_h")
                or ""
            ).strip()
            or None
        )
        net_dst = (
            str(
                data.get("dest_ip")
                or data.get("dst")
                or data.get("id.resp_h")
                or data.get("id_resp_h")
                or ""
            ).strip()
            or None
        )
        asset = resolve_tenant_by_asset_ip(net_src, net_dst)
        if asset:
            if not tenant_code:
                tenant_code = asset["tenant_short_code"]
            if tenant_code == asset["tenant_short_code"]:
                host = asset["hostname"] or asset["ip"]
        if net_src:
            desc_parts.append(f"src_ip={net_src}")
        if net_dst:
            desc_parts.append(f"dest_ip={net_dst}")
        description = "; ".join(desc_parts)[:4000]

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
        source_tool=source_tool,
        external_alert_id=external_id[:255],
        severity=severity,  # type: ignore[arg-type]
        alert_title=title,
        alert_description=description,
        destination_host=host,
        destination_ip=net_dst or agent_ip,
        source_ip=net_src or agent_ip,
        source_user=source_user,
        wazuh_agent_id=agent_id,
        technical_summary=_build_wazuh_technical_summary(raw),
        rule_id=str(rule.get("id") or "")[:64] or None,
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
    from app.services.shuffle_retry_queue import enqueue_shuffle_post

    enqueue_shuffle_post(
        url=url,
        body=raw_body,
        meta={"source": "wazuh_instant_ingress"},
    )

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
        "merged": bool(result.get("merged")),
        "occurrence_count": result.get("occurrence_count"),
        "message": (
            "Identical detection merged into the open alert; SLA first-seen was not reset"
            if result.get("merged")
            else "Alert already synced"
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

    if is_vulnerability_inventory_alert(raw):
        rule = raw.get("rule") if isinstance(raw.get("rule"), dict) else {}
        logger.info(
            "Wazuh ingress: skipping vulnerability-detector inventory alert rule=%s",
            rule.get("id"),
        )
        return {
            "success": True,
            "duplicate": False,
            "skipped": True,
            "reason": "vulnerability_inventory",
            "alert_id": None,
            "incident_number": None,
            "forwarded_to_shuffle": False,
            "message": "Vulnerability inventory is not a SOC detection",
        }

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

    forwarded = False
    if not result.get("merged"):
        threading.Thread(target=_forward_to_shuffle, args=(raw_body,), daemon=True).start()
        forwarded = bool(_shuffle_webhook_url())

    return {
        "success": True,
        "duplicate": duplicate,
        "merged": bool(result.get("merged")),
        "occurrence_count": result.get("occurrence_count"),
        "alert_id": result["alert_id"],
        "incident_number": result.get("incident_number"),
        "forwarded_to_shuffle": forwarded,
        "message": (
            "Identical detection merged into the open alert; SLA first-seen was not reset"
            if result.get("merged")
            else "Alert ingested instantly for SOC dashboards"
        ),
    }
