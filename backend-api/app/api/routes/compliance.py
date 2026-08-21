"""
Continuous Compliance & Hardening (CaaS) — customer + admin APIs.

Customer paths never expose third-party engine brand names.
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.dependencies import get_current_user, require_roles, require_tenant_match
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.db.session import fetch_all, fetch_one
from app.services import sca_compliance_service as sca

router = APIRouter(tags=["continuous-compliance-sca"])


def _resolve_tenant(short_code: str) -> Dict[str, Any]:
    tenant = fetch_one(
        """
        SELECT id::text, name, short_code, status
        FROM tenants
        WHERE short_code = %s;
        """,
        (short_code.upper(),),
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("/customer/compliance/{short_code}/summary")
def customer_compliance_summary(
    short_code: str,
    refresh: bool = Query(default=False),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    if refresh:
        try:
            sca.sync_tenant_sca(tenant["id"])
        except Exception:  # noqa: BLE001 — never 500 on sync gaps
            pass
    else:
        try:
            sca.maybe_refresh_tenant(tenant["id"])
        except Exception:  # noqa: BLE001
            pass
    summary = sca.get_summary(tenant["id"])
    return {
        "tenant": {
            "short_code": tenant["short_code"],
            "name": tenant["name"],
        },
        "overall_score_percentage": summary["overall_score_percentage"],
        "passed_checks": summary["passed_checks"],
        "failed_checks": summary["failed_checks"],
        "total_checks": summary["total_checks"],
        "agent_count": summary["agent_count"],
        "policy_count": summary["policy_count"],
        "framework_scores": summary["framework_scores"],
        "last_evaluated_at": summary.get("last_evaluated_at"),
        "last_synced_at": summary.get("last_synced_at"),
        "sync_status": summary.get("sync_status"),
        "has_data": summary.get("has_data", False),
        "message": summary.get("message"),
    }


@router.get("/customer/compliance/{short_code}/evaluations")
def customer_compliance_evaluations(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    try:
        sca.maybe_refresh_tenant(tenant["id"])
    except Exception:  # noqa: BLE001
        pass
    items = sca.list_evaluations(tenant["id"])
    # Customer-safe: drop internal agent_id raw if desired — keep host label only.
    safe = []
    for row in items:
        safe.append(
            {
                "id": row["id"],
                "endpoint_name": row.get("agent_name") or "Endpoint",
                "policy_id": row.get("policy_id"),
                "title": row.get("title"),
                "description": row.get("description"),
                "pass_count": row.get("pass_count"),
                "fail_count": row.get("fail_count"),
                "total_checks": row.get("total_checks"),
                "score": row.get("score"),
                "compliance_frameworks": row.get("compliance_frameworks") or [],
                "last_evaluated_at": row.get("end_scan_at"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"tenant": {"short_code": tenant["short_code"], "name": tenant["name"]}, "evaluations": safe}


@router.get("/customer/compliance/{short_code}/checks")
def customer_compliance_checks(
    short_code: str,
    status: Optional[str] = Query(default="FAILED", max_length=32),
    framework: Optional[str] = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    rows, total = sca.list_checks(
        tenant["id"],
        status=status,
        framework=framework,
        page=page,
        page_size=page_size,
    )
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "check_id": row["check_id"],
                "rule_title": row["rule_title"],
                "status": row["status"],
                "severity": row["severity"],
                "rationale": row.get("rationale") or "",
                "remediation": row.get("remediation") or "",
                "compliance_frameworks": row.get("compliance_refs") or [],
                "policy_title": row.get("policy_title"),
                "endpoint_name": row.get("agent_name"),
                "updated_at": row.get("updated_at"),
            }
        )
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return {
        "tenant": {"short_code": tenant["short_code"], "name": tenant["name"]},
        "checks": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": pages,
        },
    }


@router.get("/customer/compliance/{short_code}/report")
def customer_compliance_report(
    short_code: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    """HTML audit pack — print / Save as PDF from the browser."""
    tenant = _resolve_tenant(short_code)
    require_tenant_match(tenant["id"], current_user)
    summary = sca.get_summary(tenant["id"])
    evaluations = sca.list_evaluations(tenant["id"])
    failed, _ = sca.list_checks(tenant["id"], status="FAILED", page=1, page_size=100)

    fw_rows = ""
    scores = summary.get("framework_scores") or {}
    for key in ("CIS", "ISO_27001", "PCI_DSS", "NIST", "HIPAA"):
        block = scores.get(key) or {}
        label = {
            "CIS": "CIS Benchmarks",
            "ISO_27001": "ISO 27001",
            "PCI_DSS": "PCI-DSS",
            "NIST": "NIST CSF",
            "HIPAA": "HIPAA §164.312 Technical Safeguards Indicator",
        }[key]
        fw_rows += (
            f"<tr><td>{escape(label)}</td>"
            f"<td>{float(block.get('score_percentage') or 0):.1f}%</td>"
            f"<td>{int(block.get('passed_checks') or 0)}</td>"
            f"<td>{int(block.get('failed_checks') or 0)}</td></tr>"
        )

    eval_rows = ""
    for ev in evaluations:
        eval_rows += (
            f"<tr><td>{escape(str(ev.get('agent_name') or ''))}</td>"
            f"<td>{escape(str(ev.get('title') or ''))}</td>"
            f"<td>{float(ev.get('score') or 0):.1f}%</td>"
            f"<td>{int(ev.get('pass_count') or 0)} / {int(ev.get('fail_count') or 0)}</td></tr>"
        )

    fail_rows = ""
    for ch in failed:
        fail_rows += (
            f"<tr><td>{escape(str(ch.get('severity') or ''))}</td>"
            f"<td>{escape(str(ch.get('rule_title') or ''))}</td>"
            f"<td>{escape(str(ch.get('remediation') or '')[:500])}</td></tr>"
        )

    overall = float(summary.get("overall_score_percentage") or 0)
    msg = summary.get("message") or ""
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<title>Compliance Audit Report — {escape(tenant['name'])}</title>
<style>
body {{ font-family: Georgia, serif; margin: 40px; color: #111; }}
h1 {{ font-size: 22px; }} h2 {{ font-size: 16px; margin-top: 28px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ background: #f3f3f3; }}
.meta {{ color: #444; font-size: 13px; margin-bottom: 18px; }}
.score {{ font-size: 36px; font-weight: bold; }}
@media print {{ button {{ display: none; }} }}
</style></head><body>
<button onclick="window.print()">Print / Save as PDF</button>
<h1>Compliance Audit Report</h1>
<p class="meta">{escape(tenant['name'])} ({escape(tenant['short_code'])}) ·
Generated for customer portal download</p>
<p class="score">{overall:.1f}%</p>
<p>Overall compliance readiness score
{"— " + escape(msg) if msg else ""}</p>
<p>Endpoints assessed: {int(summary.get('agent_count') or 0)} ·
Policies: {int(summary.get('policy_count') or 0)} ·
Passed: {int(summary.get('passed_checks') or 0)} ·
Failed: {int(summary.get('failed_checks') or 0)}</p>
<h2>Framework breakdown</h2>
<table><thead><tr><th>Framework</th><th>Score</th><th>Passed</th><th>Failed</th></tr></thead>
<tbody>{fw_rows or "<tr><td colspan='4'>No framework data</td></tr>"}</tbody></table>
<h2>Policy evaluations</h2>
<table><thead><tr><th>Endpoint</th><th>Policy</th><th>Score</th><th>Pass / Fail</th></tr></thead>
<tbody>{eval_rows or "<tr><td colspan='4'>No policy evaluations</td></tr>"}</tbody></table>
<h2>Failed checks (sample)</h2>
<table><thead><tr><th>Severity</th><th>Check</th><th>Remediation</th></tr></thead>
<tbody>{fail_rows or "<tr><td colspan='3'>No failed checks recorded</td></tr>"}</tbody></table>
</body></html>"""
    filename = f"compliance-audit-{tenant['short_code']}.html"
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/compliance/{short_code}/sync")
def admin_compliance_sync(
    short_code: str,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    tenant = _resolve_tenant(short_code)
    try:
        result = sca.sync_tenant_sca(tenant["id"])
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception(
            "compliance sync failed tenant=%s", tenant.get("short_code")
        )
        raise HTTPException(status_code=502, detail="Compliance sync failed") from exc
    return {"tenant": {"short_code": tenant["short_code"], "name": tenant["name"]}, **result}


@router.get("/admin/compliance/summary")
def admin_compliance_summary(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            t.short_code,
            t.name AS tenant_name,
            COALESCE(s.overall_score_percentage, 0)::float AS overall_score_percentage,
            COALESCE(s.passed_checks, 0) AS passed_checks,
            COALESCE(s.failed_checks, 0) AS failed_checks,
            COALESCE(s.total_checks, 0) AS total_checks,
            COALESCE(s.agent_count, 0) AS agent_count,
            COALESCE(s.policy_count, 0) AS policy_count,
            COALESCE(s.framework_scores, '{}'::jsonb) AS framework_scores,
            s.last_evaluated_at::text,
            s.last_synced_at::text,
            COALESCE(s.sync_status, 'never') AS sync_status
        FROM tenants t
        LEFT JOIN tenant_compliance_summaries s ON s.tenant_id = t.id
        WHERE t.status = 'active'
        ORDER BY t.name ASC;
        """
    )
    return {"tenants": rows or []}
