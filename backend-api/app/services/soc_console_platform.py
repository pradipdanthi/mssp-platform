"""Live platform visibility for Tia — engines, host stats, KPIs, and topic deep-dives."""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.session import fetch_all, fetch_one
from app.services.soc_console_engines import build_engine_wall
from app.services.soc_console_proxmox import gather_proxmox_inventory, wants_proxmox

logger = logging.getLogger(__name__)


def _read_meminfo() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        data = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    kv: Dict[str, int] = {}
    for line in data.splitlines():
        if ":" not in line:
            continue
        k, rest = line.split(":", 1)
        num = rest.strip().split()[0]
        try:
            kv[k] = int(num)
        except ValueError:
            continue
    total_kb = kv.get("MemTotal") or 0
    avail_kb = kv.get("MemAvailable") or kv.get("MemFree") or 0
    out["ram_total_gb"] = round(total_kb / (1024 * 1024), 2) if total_kb else None
    out["ram_available_gb"] = round(avail_kb / (1024 * 1024), 2) if avail_kb else None
    if total_kb:
        used = max(0, total_kb - avail_kb)
        out["ram_used_pct"] = round(100.0 * used / total_kb, 1)
    return out


def _read_loadavg() -> Dict[str, Any]:
    try:
        parts = Path("/proc/loadavg").read_text(encoding="utf-8").split()
        return {
            "load_1m": float(parts[0]),
            "load_5m": float(parts[1]),
            "load_15m": float(parts[2]),
        }
    except Exception:  # noqa: BLE001
        return {}


def _read_disk() -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage("/")
        total = usage.total or 1
        return {
            "disk_total_gb": round(usage.total / (1024**3), 2),
            "disk_used_gb": round(usage.used / (1024**3), 2),
            "disk_free_gb": round(usage.free / (1024**3), 2),
            "disk_used_pct": round(100.0 * usage.used / total, 1),
        }
    except Exception:  # noqa: BLE001
        return {}


def _control_plane_identity() -> Dict[str, Any]:
    return {
        "hostname": (os.getenv("HOSTNAME") or "mssp-control").strip() or "mssp-control",
        "role": "MSSP control plane (VM 100)",
        "note": (
            "Metrics are from the control-plane API runtime (container/host view). "
            "Use them for operational status questions about mssp-control."
        ),
    }


def gather_patch_gaps_detail(
    *,
    tenant_id: Optional[str] = None,
    short_code: Optional[str] = None,
    limit: int = 40,
) -> Dict[str, Any]:
    """Full SOC-usable breakdown of failed SCA / patch-gap checks."""
    limit = max(5, min(int(limit or 40), 80))
    clauses = ["upper(c.status) IN ('FAILED', 'FAIL')"]
    params: List[Any] = []
    if tenant_id:
        clauses.append("c.tenant_id = %s::uuid")
        params.append(tenant_id)
    if short_code:
        clauses.append("t.short_code = %s")
        params.append(short_code.strip().upper())
    where = " AND ".join(clauses)

    try:
        total_row = fetch_one(
            f"""
            SELECT count(*)::int AS n
            FROM sca_check_details c
            JOIN tenants t ON t.id = c.tenant_id
            WHERE {where};
            """,
            tuple(params),
        )
        by_tenant = fetch_all(
            f"""
            SELECT t.short_code, t.name AS tenant_name, count(*)::int AS gaps
            FROM sca_check_details c
            JOIN tenants t ON t.id = c.tenant_id
            WHERE {where}
            GROUP BY t.short_code, t.name
            ORDER BY gaps DESC
            LIMIT 20;
            """,
            tuple(params),
        )
        by_severity = fetch_all(
            f"""
            SELECT lower(coalesce(nullif(trim(c.severity), ''), 'medium')) AS severity,
                   count(*)::int AS n
            FROM sca_check_details c
            JOIN tenants t ON t.id = c.tenant_id
            WHERE {where}
            GROUP BY 1
            ORDER BY CASE lower(coalesce(nullif(trim(c.severity), ''), 'medium'))
              WHEN 'critical' THEN 0 WHEN 'high' THEN 1
              WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END;
            """,
            tuple(params),
        )
        by_host = fetch_all(
            f"""
            SELECT coalesce(nullif(trim(e.agent_name), ''), 'unknown') AS host,
                   t.short_code,
                   count(*)::int AS gaps
            FROM sca_check_details c
            JOIN sca_evaluations e ON e.id = c.evaluation_id
            JOIN tenants t ON t.id = c.tenant_id
            WHERE {where}
            GROUP BY 1, t.short_code
            ORDER BY gaps DESC
            LIMIT 25;
            """,
            tuple(params),
        )
        items = fetch_all(
            f"""
            SELECT
                c.id::text AS id,
                c.check_id,
                left(c.rule_title, 160) AS rule_title,
                c.status,
                lower(coalesce(c.severity, 'medium')) AS severity,
                left(coalesce(c.rationale, ''), 180) AS rationale,
                left(coalesce(c.remediation, ''), 220) AS remediation,
                e.policy_id,
                left(coalesce(e.title, ''), 120) AS policy_title,
                e.agent_name AS host,
                t.name AS tenant_name,
                t.short_code,
                (c.updated_at AT TIME ZONE 'utc')::text AS updated_at
            FROM sca_check_details c
            JOIN sca_evaluations e ON e.id = c.evaluation_id
            JOIN tenants t ON t.id = c.tenant_id
            WHERE {where}
            ORDER BY
                CASE lower(coalesce(c.severity, ''))
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
                END,
                c.updated_at DESC NULLS LAST
            LIMIT %s;
            """,
            tuple(params + [limit]),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("patch gap detail failed: %s", exc)
        return {"error": "patch_gap_query_failed", "total": 0, "items": []}

    return {
        "total": int((total_row or {}).get("n") or 0),
        "by_tenant": by_tenant or [],
        "by_severity": by_severity or [],
        "by_host": by_host or [],
        "items": items or [],
        "source": "sca_check_details (FAILED)",
        "note": (
            "These are Wazuh SCA / hardening failures (patch & config gaps), "
            "not Greenbone CVE vulns. Use items for host/rule/remediation answers."
        ),
    }


def gather_vuln_detail(
    *,
    tenant_id: Optional[str] = None,
    limit: int = 30,
) -> Dict[str, Any]:
    limit = max(5, min(int(limit or 30), 60))
    clauses = ["vf.status = 'OPEN'"]
    params: List[Any] = []
    if tenant_id:
        clauses.append("vf.tenant_id = %s::uuid")
        params.append(tenant_id)
    where = " AND ".join(clauses)
    try:
        total_row = fetch_one(
            f"SELECT count(*)::int AS n FROM tenant_vulnerability_findings vf WHERE {where};",
            tuple(params),
        )
        by_tenant = fetch_all(
            f"""
            SELECT t.short_code, t.name AS tenant_name, count(*)::int AS open_vulns
            FROM tenant_vulnerability_findings vf
            JOIN tenants t ON t.id = vf.tenant_id
            WHERE {where}
            GROUP BY t.short_code, t.name
            ORDER BY open_vulns DESC
            LIMIT 15;
            """,
            tuple(params),
        )
        items = fetch_all(
            f"""
            SELECT vf.id::text AS id,
                   left(coalesce(vf.title, ''), 160) AS title,
                   vf.cve_id,
                   lower(coalesce(vf.severity, 'medium')) AS severity,
                   vf.asset_ip_or_host AS host,
                   t.short_code,
                   t.name AS tenant_name,
                   (vf.updated_at AT TIME ZONE 'utc')::text AS updated_at
            FROM tenant_vulnerability_findings vf
            JOIN tenants t ON t.id = vf.tenant_id
            WHERE {where}
            ORDER BY
                CASE lower(coalesce(vf.severity, ''))
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 ELSE 3 END,
                vf.updated_at DESC NULLS LAST
            LIMIT %s;
            """,
            tuple(params + [limit]),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("vuln detail failed: %s", exc)
        return {"error": "vuln_query_failed", "total": 0, "items": []}
    return {
        "total": int((total_row or {}).get("n") or 0),
        "by_tenant": by_tenant or [],
        "items": items or [],
        "source": "tenant_vulnerability_findings (OPEN)",
    }


def infer_topic(question: str) -> str:
    q = (question or "").lower()
    if re.search(
        r"\b(patch\s*gap|patch\s*gaps|sca|hardening|cis\s*fail|compliance\s*fail|"
        r"failed\s*check|remediat|config\s*gap)\b",
        q,
    ):
        return "patch_gaps"
    if re.search(r"\b(vuln|cve|cves|greenbone|openvas|nuclei|vuls)\b", q):
        return "vulnerabilities"
    if re.search(
        r"\b(proxmox|hypervisor|vcpu|vcpus|vm\s*\d{2,3}|allocated\s*ram|guest\s*ram)\b",
        q,
    ):
        return "proxmox"
    if re.search(
        r"\b(wazuh|shuffle|thehive|suricata|zeek|misp|velociraptor|engine|stack\s*health|"
        r"manager\s*health|ram|memory|disk|load\s*average|mssp-control|cpu\s*core)\b",
        q,
    ):
        return "stack_health"
    if re.search(r"\b(alert|incident|ticket|critical|while i was|away|brief)\b", q):
        return "soc_briefing"
    return "general"


def gather_platform_visibility(
    *,
    question: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tenant_short_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Compact facts Tia can quote — plus topic deep-dives when the question needs them."""
    wall = build_engine_wall()
    lanes = wall.get("lanes") or []
    engine_rows: List[Dict[str, Any]] = []
    for lane in lanes:
        engine_rows.append(
            {
                "id": lane.get("id"),
                "label": lane.get("label"),
                "hostname": lane.get("hostname"),
                "vm": lane.get("vm"),
                "host": lane.get("host"),
                "port": lane.get("port"),
                "status": lane.get("status"),
                "reachable": lane.get("reachable"),
                "latency_ms": lane.get("latency_ms"),
                "tool": lane.get("tool"),
                "pulse_24h": lane.get("pulse_24h"),
            }
        )

    by_id = {str(r.get("id")): r for r in engine_rows}
    named = {
        "wazuh_manager": by_id.get("wazuh"),
        "shuffle": by_id.get("shuffle") or by_id.get("soar"),
        "thehive": by_id.get("thehive"),
        "suricata": by_id.get("suricata"),
        "control_plane": by_id.get("control_plane"),
        "greenbone": by_id.get("greenbone") or by_id.get("vuln"),
        "misp": by_id.get("misp"),
        "velociraptor": by_id.get("velociraptor"),
        "secure_edge": by_id.get("secure_edge") or by_id.get("edge"),
    }

    db: Dict[str, Any] = {}
    try:
        db = (
            fetch_one(
                """
                SELECT
                  (SELECT count(*)::int FROM tenants WHERE status = 'active') AS active_tenants,
                  (SELECT count(*)::int FROM appliances WHERE status = 'online') AS appliances_online,
                  (SELECT count(*)::int FROM appliances) AS appliances_total,
                  (SELECT count(*)::int FROM security_alerts
                     WHERE status NOT IN ('closed','false_positive')) AS open_alerts,
                  (SELECT count(*)::int FROM incidents
                     WHERE status IN ('open','in_progress','waiting_customer')) AS open_incidents,
                  (SELECT count(*)::int FROM tenant_vulnerability_findings
                     WHERE status = 'OPEN') AS open_vulns,
                  (SELECT count(*)::int FROM sca_check_details
                     WHERE upper(status) IN ('FAILED','FAIL')) AS patch_gaps;
                """
            )
            or {}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform KPI snapshot failed: %s", exc)
        db = {"error": "kpi_query_failed"}

    topic = infer_topic(question or "")
    out: Dict[str, Any] = {
        "topic": topic,
        "control_plane": {
            **_control_plane_identity(),
            **_read_meminfo(),
            **_read_loadavg(),
            **_read_disk(),
        },
        "engine_summary": wall.get("summary") or {},
        "engines": engine_rows,
        "named_engines": {k: v for k, v in named.items() if v},
        "platform_kpis": db,
        "generated_at": wall.get("generated_at"),
    }

    # Always attach a compact patch-gap rollup so follow-ups work; deepen when asked.
    try:
        if topic == "patch_gaps" or topic == "general":
            detail_limit = 50 if topic == "patch_gaps" else 15
            out["patch_gaps_detail"] = gather_patch_gaps_detail(
                tenant_id=tenant_id,
                short_code=tenant_short_code,
                limit=detail_limit,
            )
        if topic == "vulnerabilities" or (
            topic == "general" and int(db.get("open_vulns") or 0) > 0
        ):
            out["vulnerabilities_detail"] = gather_vuln_detail(
                tenant_id=tenant_id,
                limit=40 if topic == "vulnerabilities" else 12,
            )
        if topic in ("proxmox", "stack_health") or wants_proxmox(question or ""):
            out["proxmox"] = gather_proxmox_inventory(force=topic == "proxmox")
    except Exception as exc:  # noqa: BLE001
        logger.warning("topic detail attach failed: %s", exc)

    # When the question is specifically patch/vuln, shrink engine noise for the LLM.
    if topic in ("patch_gaps", "vulnerabilities"):
        out["engines"] = [
            e
            for e in engine_rows
            if e.get("id") in ("wazuh", "greenbone", "control_plane", "vuln")
        ]
        out["conversation_hint"] = (
            "Boss asked about patch/vuln detail — answer with customer, host, "
            "severity, rule/CVE, and remediation from *_detail. "
            "Do NOT dump full stack health unless they ask for it."
        )
    if topic == "proxmox" or wants_proxmox(question or ""):
        out["conversation_hint"] = (
            "Boss asked for hypervisor / VM resources. Use platform_visibility.proxmox "
            "(named.wazuh_manager, vcpus, ram_configured_gb, ram_used_gb, status). "
            "This IS a live Proxmox pull — do not say you lack hypervisor access if proxmox.vms is present."
        )

    return out


def find_engine_status(question: str, snapshot: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    _ = question
    return snapshot
