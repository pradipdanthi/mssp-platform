"""
Continuous Compliance & Hardening (CaaS) — normalize Wazuh SCA into PostgreSQL.

Does not touch alert ingestion or active-response paths.
Customer-facing payloads must not expose engine brand names.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from psycopg.types.json import Json

from app.db.session import execute, fetch_all, fetch_one, fetch_one_write
from app.services import wazuh_client
from app.services.wazuh_client import WazuhClientError

logger = logging.getLogger(__name__)

FRAMEWORK_ALIASES = {
    "cis": "CIS",
    "cis_csc_v7": "CIS",
    "cis_csc_v8": "CIS",
    "iso_27001": "ISO_27001",
    "iso_27001-2013": "ISO_27001",
    "iso_27001-2022": "ISO_27001",
    "pci_dss": "PCI_DSS",
    "pci_dss_v3.2.1": "PCI_DSS",
    "pci_dss_v4.0": "PCI_DSS",
    "nist": "NIST",
    "nist_800-53": "NIST",
    "nist_csf": "NIST",
    "csc": "CIS",
    "hipaa": "HIPAA",
    "hipaa_security": "HIPAA",
    "hipaa_164.312": "HIPAA",
    "164.312": "HIPAA",
    "164.308": "HIPAA",
    "164.310": "HIPAA",
    "164.314": "HIPAA",
}

CUSTOMER_FRAMEWORKS = ("CIS", "ISO_27001", "PCI_DSS", "NIST", "HIPAA")

_HIPAA_SECTION_MARKERS = ("164.312", "164.308", "164.310", "164.314")


def _blob_maps_to_hipaa(blob: str) -> bool:
    text = (blob or "").lower()
    if "hipaa" in text:
        return True
    return any(marker in text for marker in _HIPAA_SECTION_MARKERS)


def _parse_ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_frameworks(compliance_items: Any, extra_text: str = "") -> List[str]:
    found: Set[str] = set()
    if isinstance(compliance_items, list):
        for item in compliance_items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().lower()
            value = str(item.get("value") or "").strip().lower()
            blob = f"{key} {value}".strip()
            if not blob:
                continue
            mapped = FRAMEWORK_ALIASES.get(key) or FRAMEWORK_ALIASES.get(value)
            if mapped:
                found.add(mapped)
                continue
            if key.startswith("cis") or value.startswith("cis"):
                found.add("CIS")
            elif key.startswith("iso") or "iso_27001" in blob or "iso27001" in blob:
                found.add("ISO_27001")
            elif key.startswith("pci") or "pci_dss" in blob or "pci-dss" in blob:
                found.add("PCI_DSS")
            elif key.startswith("nist") or "nist" in blob:
                found.add("NIST")
            if _blob_maps_to_hipaa(blob):
                found.add("HIPAA")
    if _blob_maps_to_hipaa(extra_text):
        found.add("HIPAA")
    return sorted(found)


def _policy_frameworks(policy: Dict[str, Any], check_frameworks: Set[str]) -> List[str]:
    out = set(check_frameworks)
    pid = str(policy.get("policy_id") or "").lower()
    name = str(policy.get("name") or "").lower()
    description = str(policy.get("description") or "").lower()
    blob = f"{pid} {name} {description}"
    if "cis" in blob:
        out.add("CIS")
    if "iso" in blob:
        out.add("ISO_27001")
    if "pci" in blob:
        out.add("PCI_DSS")
    if "nist" in blob:
        out.add("NIST")
    if _blob_maps_to_hipaa(blob):
        out.add("HIPAA")
    if not out:
        out.add("CIS")
    return sorted(out)


def _result_to_status(result: Any) -> str:
    r = str(result or "").strip().lower()
    if r == "passed":
        return "PASSED"
    if r == "failed":
        return "FAILED"
    if r in ("not applicable", "not_applicable", "n/a"):
        return "NOT_APPLICABLE"
    return "UNKNOWN"


def _guess_severity(title: str, status: str) -> str:
    if status != "FAILED":
        return "info"
    t = (title or "").lower()
    if any(x in t for x in ("password", "administrator", "firewall", "remote desktop", "rdp", "smb")):
        return "high"
    if any(x in t for x in ("audit", "logging", "encryption", "bitlocker", "uac")):
        return "medium"
    return "medium"


def _tenant_agents(tenant_id: str) -> List[Dict[str, str]]:
    """Resolve endpoint agents for a tenant (asset details + engine group)."""
    by_id: Dict[str, Dict[str, str]] = {}

    assets = fetch_all(
        """
        SELECT
            hostname,
            details->>'wazuh_agent_id' AS agent_id
        FROM protected_assets
        WHERE tenant_id = %s::uuid
          AND details ? 'wazuh_agent_id'
          AND COALESCE(details->>'wazuh_agent_id', '') <> '';
        """,
        (tenant_id,),
    )
    for row in assets:
        aid = str(row.get("agent_id") or "").strip()
        if not aid or aid == "000":
            continue
        by_id[aid] = {
            "agent_id": aid,
            "agent_name": str(row.get("hostname") or aid),
        }

    binding = fetch_one(
        """
        SELECT wazuh_agent_group
        FROM tenant_engine_bindings
        WHERE tenant_id = %s::uuid
          AND COALESCE(wazuh_agent_group, '') <> '';
        """,
        (tenant_id,),
    )
    group_id = (binding or {}).get("wazuh_agent_group")
    if group_id:
        try:
            for agent in wazuh_client.list_agents_in_group(str(group_id)):
                aid = str(agent.get("id") or "").strip()
                if not aid or aid == "000":
                    continue
                by_id.setdefault(
                    aid,
                    {
                        "agent_id": aid,
                        "agent_name": str(agent.get("name") or aid),
                    },
                )
                if agent.get("name"):
                    by_id[aid]["agent_name"] = str(agent.get("name"))
        except WazuhClientError as exc:
            logger.warning("SCA group agent list failed for tenant %s: %s", tenant_id, exc)

    return list(by_id.values())


def _empty_framework_scores() -> Dict[str, Dict[str, Any]]:
    return {
        fw: {
            "score_percentage": 0.0,
            "passed_checks": 0,
            "failed_checks": 0,
            "total_checks": 0,
        }
        for fw in CUSTOMER_FRAMEWORKS
    }


def _upsert_summary(
    tenant_id: str,
    *,
    score: float,
    passed: int,
    failed: int,
    total: int,
    agent_count: int,
    policy_count: int,
    framework_scores: Dict[str, Any],
    last_evaluated_at: Optional[str],
    sync_status: str,
    sync_error: Optional[str] = None,
) -> None:
    execute(
        """
        INSERT INTO tenant_compliance_summaries (
            tenant_id, overall_score_percentage, passed_checks, failed_checks,
            total_checks, agent_count, policy_count, framework_scores,
            last_evaluated_at, last_synced_at, sync_status, sync_error
        ) VALUES (
            %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb,
            %s::timestamptz, now(), %s, %s
        )
        ON CONFLICT (tenant_id) DO UPDATE SET
            overall_score_percentage = EXCLUDED.overall_score_percentage,
            passed_checks = EXCLUDED.passed_checks,
            failed_checks = EXCLUDED.failed_checks,
            total_checks = EXCLUDED.total_checks,
            agent_count = EXCLUDED.agent_count,
            policy_count = EXCLUDED.policy_count,
            framework_scores = EXCLUDED.framework_scores,
            last_evaluated_at = EXCLUDED.last_evaluated_at,
            last_synced_at = now(),
            sync_status = EXCLUDED.sync_status,
            sync_error = EXCLUDED.sync_error,
            updated_at = now();
        """,
        (
            tenant_id,
            round(float(score), 2),
            int(passed),
            int(failed),
            int(total),
            int(agent_count),
            int(policy_count),
            Json(framework_scores),
            last_evaluated_at,
            sync_status,
            sync_error,
        ),
    )


def _enable_entitlement_if_data(tenant_id: str) -> None:
    """Mark Continuous Compliance contracted when SCA data exists."""
    execute(
        """
        INSERT INTO tenant_entitlements (tenant_id, continuous_compliance_enabled)
        VALUES (%s::uuid, TRUE)
        ON CONFLICT (tenant_id) DO UPDATE SET
            continuous_compliance_enabled = TRUE,
            updated_at = now();
        """,
        (tenant_id,),
    )


def sync_tenant_sca(tenant_id: str) -> Dict[str, Any]:
    """
    Pull SCA policies/checks for all known tenant agents and refresh summaries.

    Graceful on empty/missing SCA: writes 0% empty summary, never raises for
    per-agent gaps.
    """
    tid = str(tenant_id).strip()
    if not tid:
        raise ValueError("tenant_id is required")

    agents = _tenant_agents(tid)
    if not agents:
        _upsert_summary(
            tid,
            score=0.0,
            passed=0,
            failed=0,
            total=0,
            agent_count=0,
            policy_count=0,
            framework_scores=_empty_framework_scores(),
            last_evaluated_at=None,
            sync_status="empty",
            sync_error="No endpoint agents mapped for compliance scans",
        )
        return {
            "tenant_id": tid,
            "sync_status": "empty",
            "agent_count": 0,
            "policy_count": 0,
            "overall_score_percentage": 0.0,
            "message": "0% - No Policy Scans Recorded",
        }

    fw_pass: Dict[str, int] = {fw: 0 for fw in CUSTOMER_FRAMEWORKS}
    fw_fail: Dict[str, int] = {fw: 0 for fw in CUSTOMER_FRAMEWORKS}
    total_pass = 0
    total_fail = 0
    total_checks = 0
    policy_count = 0
    agents_with_policies = 0
    last_eval: Optional[datetime] = None
    errors: List[str] = []
    seen_eval_ids: List[str] = []

    for agent in agents:
        aid = agent["agent_id"]
        aname = agent.get("agent_name") or aid
        try:
            policies = wazuh_client.list_sca_policies(aid)
        except Exception as exc:  # noqa: BLE001 — isolate per-agent failures
            errors.append(f"agent {aid}: {exc}")
            continue
        if not policies:
            continue
        agents_with_policies += 1

        for policy in policies:
            policy_id = str(policy.get("policy_id") or "").strip()
            if not policy_id:
                continue
            policy_count += 1
            pass_count = int(policy.get("pass") or 0)
            fail_count = int(policy.get("fail") or 0)
            invalid_count = int(policy.get("invalid") or 0)
            checks_total = int(policy.get("total_checks") or (pass_count + fail_count + invalid_count))
            score = float(policy.get("score") or 0)
            end_scan = _parse_ts(policy.get("end_scan") or policy.get("start_scan"))

            # Page failed checks for remediation store + framework tagging.
            offset = 0
            failed_rows: List[Dict[str, Any]] = []
            check_fw: Set[str] = set()
            while True:
                items, total_failed = wazuh_client.list_sca_checks(
                    aid, policy_id, result="failed", limit=200, offset=offset
                )
                if not items:
                    break
                for item in items:
                    status = _result_to_status(item.get("result"))
                    title = str(item.get("title") or item.get("description") or "Configuration check")
                    frameworks = _normalize_frameworks(
                        item.get("compliance"),
                        extra_text=f"{title} {item.get('rationale') or ''} {item.get('remediation') or ''}",
                    )
                    check_fw.update(frameworks)
                    for fw in frameworks:
                        if fw in fw_fail:
                            fw_fail[fw] += 1
                    failed_rows.append(
                        {
                            "check_id": str(item.get("id") or ""),
                            "rule_title": title[:500],
                            "status": status if status != "UNKNOWN" else "FAILED",
                            "severity": _guess_severity(title, "FAILED"),
                            "rationale": str(item.get("rationale") or "")[:4000],
                            "remediation": str(item.get("remediation") or "")[:4000],
                            "compliance_refs": frameworks,
                        }
                    )
                offset += len(items)
                if offset >= total_failed or len(items) < 200:
                    break

            # Estimate passed per framework from policy totals when tags sparse.
            frameworks = _policy_frameworks(policy, check_fw)
            # Attribute policy pass/fail to listed frameworks (equal split if multiple).
            share = max(1, len(frameworks))
            for fw in frameworks:
                if fw in fw_pass:
                    fw_pass[fw] += pass_count // share
                    # failed already counted from tagged checks; top up if untagged
            if fail_count and not failed_rows:
                for fw in frameworks:
                    if fw in fw_fail:
                        fw_fail[fw] += fail_count // share

            total_pass += pass_count
            total_fail += fail_count
            total_checks += checks_total

            if end_scan:
                try:
                    ts = datetime.fromisoformat(end_scan.replace("Z", "+00:00"))
                    if last_eval is None or ts > last_eval:
                        last_eval = ts
                except ValueError:
                    pass

            eval_row = fetch_one_write(
                """
                INSERT INTO sca_evaluations (
                    tenant_id, agent_id, agent_name, policy_id, title, description,
                    pass_count, fail_count, invalid_count, total_checks, score,
                    compliance_frameworks, end_scan_at, raw_policy
                ) VALUES (
                    %s::uuid, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s::jsonb, %s::timestamptz, %s::jsonb
                )
                ON CONFLICT (tenant_id, agent_id, policy_id) DO UPDATE SET
                    agent_name = EXCLUDED.agent_name,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    pass_count = EXCLUDED.pass_count,
                    fail_count = EXCLUDED.fail_count,
                    invalid_count = EXCLUDED.invalid_count,
                    total_checks = EXCLUDED.total_checks,
                    score = EXCLUDED.score,
                    compliance_frameworks = EXCLUDED.compliance_frameworks,
                    end_scan_at = EXCLUDED.end_scan_at,
                    raw_policy = EXCLUDED.raw_policy,
                    updated_at = now()
                RETURNING id::text;
                """,
                (
                    tid,
                    aid,
                    aname[:200],
                    policy_id[:120],
                    str(policy.get("name") or policy_id)[:500],
                    str(policy.get("description") or "")[:4000],
                    pass_count,
                    fail_count,
                    invalid_count,
                    checks_total,
                    round(score, 2),
                    Json(frameworks),
                    end_scan,
                    Json(
                        {
                            "policy_id": policy_id,
                            "score": score,
                            "pass": pass_count,
                            "fail": fail_count,
                            "total_checks": checks_total,
                            "end_scan": end_scan,
                        }
                    ),
                ),
            )
            evaluation_id = (eval_row or {}).get("id")
            if not evaluation_id:
                continue
            seen_eval_ids.append(str(evaluation_id))

            execute(
                "DELETE FROM sca_check_details WHERE evaluation_id = %s::uuid;",
                (evaluation_id,),
            )
            for row in failed_rows:
                if not row["check_id"]:
                    continue
                execute(
                    """
                    INSERT INTO sca_check_details (
                        evaluation_id, tenant_id, check_id, rule_title, status,
                        severity, rationale, remediation, compliance_refs
                    ) VALUES (
                        %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (evaluation_id, check_id) DO UPDATE SET
                        rule_title = EXCLUDED.rule_title,
                        status = EXCLUDED.status,
                        severity = EXCLUDED.severity,
                        rationale = EXCLUDED.rationale,
                        remediation = EXCLUDED.remediation,
                        compliance_refs = EXCLUDED.compliance_refs,
                        updated_at = now();
                    """,
                    (
                        evaluation_id,
                        tid,
                        str(row["check_id"])[:64],
                        row["rule_title"],
                        row["status"],
                        row["severity"],
                        row["rationale"],
                        row["remediation"],
                        Json(row["compliance_refs"]),
                    ),
                )

    # Drop stale evaluations for this tenant (agents removed / policies gone).
    if seen_eval_ids:
        execute(
            """
            DELETE FROM sca_evaluations
            WHERE tenant_id = %s::uuid
              AND id <> ALL(%s::uuid[]);
            """,
            (tid, seen_eval_ids),
        )
    else:
        execute("DELETE FROM sca_evaluations WHERE tenant_id = %s::uuid;", (tid,))

    framework_scores = _empty_framework_scores()
    for fw in CUSTOMER_FRAMEWORKS:
        p = fw_pass[fw]
        f = fw_fail[fw]
        # If we only tracked fails from tags, estimate pass from overall ratio.
        if p == 0 and f > 0 and total_checks > 0 and total_pass > 0:
            p = max(0, int(round((total_pass / max(total_checks, 1)) * (p + f))))
        tot = p + f
        pct = round((100.0 * p / tot), 2) if tot else 0.0
        framework_scores[fw] = {
            "score_percentage": pct,
            "passed_checks": p,
            "failed_checks": f,
            "total_checks": tot,
        }

    overall = (
        round(100.0 * total_pass / total_checks, 2)
        if total_checks > 0
        else 0.0
    )
    sync_status = "ok"
    sync_error = None
    if errors and policy_count:
        sync_status = "partial"
        sync_error = "; ".join(errors)[:1000]
    elif not policy_count:
        sync_status = "empty"
        sync_error = "0% - No Policy Scans Recorded"
    elif errors:
        sync_status = "error"
        sync_error = "; ".join(errors)[:1000]

    last_eval_iso = last_eval.astimezone(timezone.utc).isoformat() if last_eval else None
    _upsert_summary(
        tid,
        score=overall,
        passed=total_pass,
        failed=total_fail,
        total=total_checks,
        agent_count=agents_with_policies,
        policy_count=policy_count,
        framework_scores=framework_scores,
        last_evaluated_at=last_eval_iso,
        sync_status=sync_status,
        sync_error=sync_error,
    )
    if policy_count > 0:
        _enable_entitlement_if_data(tid)

    return {
        "tenant_id": tid,
        "sync_status": sync_status,
        "agent_count": agents_with_policies,
        "policy_count": policy_count,
        "overall_score_percentage": overall,
        "passed_checks": total_pass,
        "failed_checks": total_fail,
        "total_checks": total_checks,
        "message": sync_error if sync_status == "empty" else "Compliance data refreshed",
        "errors": errors[:5],
    }


def maybe_refresh_tenant(tenant_id: str, *, max_age_seconds: int = 3600) -> Optional[Dict[str, Any]]:
    """Sync when summary missing or last sync older than max_age_seconds."""
    row = fetch_one(
        """
        SELECT last_synced_at, sync_status, total_checks
        FROM tenant_compliance_summaries
        WHERE tenant_id = %s::uuid;
        """,
        (str(tenant_id),),
    )
    if not row:
        return sync_tenant_sca(str(tenant_id))
    last = row.get("last_synced_at")
    if last is None:
        return sync_tenant_sca(str(tenant_id))
    try:
        if hasattr(last, "timestamp"):
            age = datetime.now(timezone.utc).timestamp() - last.replace(tzinfo=timezone.utc).timestamp()
        else:
            age = max_age_seconds + 1
    except Exception:  # noqa: BLE001
        age = max_age_seconds + 1
    if age >= max_age_seconds:
        return sync_tenant_sca(str(tenant_id))
    return None


def get_summary(tenant_id: str) -> Dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            overall_score_percentage::float AS overall_score_percentage,
            passed_checks,
            failed_checks,
            total_checks,
            agent_count,
            policy_count,
            framework_scores,
            last_evaluated_at::text,
            last_synced_at::text,
            sync_status,
            sync_error
        FROM tenant_compliance_summaries
        WHERE tenant_id = %s::uuid;
        """,
        (str(tenant_id),),
    )
    if not row:
        return {
            "overall_score_percentage": 0.0,
            "passed_checks": 0,
            "failed_checks": 0,
            "total_checks": 0,
            "agent_count": 0,
            "policy_count": 0,
            "framework_scores": _empty_framework_scores(),
            "last_evaluated_at": None,
            "last_synced_at": None,
            "sync_status": "never",
            "sync_error": None,
            "message": "0% - No Policy Scans Recorded",
            "has_data": False,
        }
    total = int(row.get("total_checks") or 0)
    return {
        **row,
        "overall_score_percentage": float(row.get("overall_score_percentage") or 0),
        "framework_scores": row.get("framework_scores") or _empty_framework_scores(),
        "message": (
            "0% - No Policy Scans Recorded"
            if total == 0
            else None
        ),
        "has_data": total > 0,
    }


def list_evaluations(tenant_id: str) -> List[Dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            id::text,
            agent_id,
            agent_name,
            policy_id,
            title,
            description,
            pass_count,
            fail_count,
            total_checks,
            score::float AS score,
            compliance_frameworks,
            end_scan_at::text,
            updated_at::text
        FROM sca_evaluations
        WHERE tenant_id = %s::uuid
        ORDER BY score ASC, title ASC;
        """,
        (str(tenant_id),),
    )
    return rows or []


def list_checks(
    tenant_id: str,
    *,
    status: Optional[str] = "FAILED",
    framework: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Dict[str, Any]], int]:
    clauses = ["c.tenant_id = %s::uuid"]
    params: List[Any] = [str(tenant_id)]
    st = (status or "").strip().upper()
    if st:
        clauses.append("c.status = %s")
        params.append(st)
    fw = (framework or "").strip().upper()
    if fw:
        clauses.append("c.compliance_refs @> %s::jsonb")
        params.append(Json([fw]))
    where = " AND ".join(clauses)
    count_row = fetch_one(
        f"SELECT count(*)::int AS n FROM sca_check_details c WHERE {where};",
        tuple(params),
    )
    total = int((count_row or {}).get("n") or 0)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    offset = (page - 1) * page_size
    rows = fetch_all(
        f"""
        SELECT
            c.id::text,
            c.check_id,
            c.rule_title,
            c.status,
            c.severity,
            c.rationale,
            c.remediation,
            c.compliance_refs,
            e.policy_id,
            e.title AS policy_title,
            e.agent_name,
            c.updated_at::text
        FROM sca_check_details c
        JOIN sca_evaluations e ON e.id = c.evaluation_id
        WHERE {where}
        ORDER BY
            CASE c.severity
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            c.rule_title ASC
        LIMIT %s OFFSET %s;
        """,
        tuple(params + [page_size, offset]),
    )
    return rows or [], total


def tenant_has_compliance_data(tenant_id: str) -> bool:
    row = fetch_one(
        """
        SELECT 1 AS ok
        FROM tenant_compliance_summaries
        WHERE tenant_id = %s::uuid
          AND total_checks > 0
        LIMIT 1;
        """,
        (str(tenant_id),),
    )
    return bool(row)
