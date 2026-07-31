import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ComplianceCheckItem,
  ComplianceEvaluation,
  ComplianceSummary,
  getComplianceChecks,
  getComplianceEvaluations,
  getComplianceReportUrl,
  getComplianceSummary,
  getCustomerEntitlements,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import RadialGauge from "../components/RadialGauge";

const FRAMEWORK_TABS: { id: string | null; label: string }[] = [
  { id: null, label: "All frameworks" },
  { id: "CIS", label: "CIS Benchmarks" },
  { id: "ISO_27001", label: "ISO 27001" },
  { id: "PCI_DSS", label: "PCI-DSS" },
  { id: "NIST", label: "NIST CSF" },
];

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

/**
 * Continuous Compliance & Hardening (CaaS) — executive readiness view.
 * Capability labels only (no third-party engine names).
 */
export default function CompliancePage() {
  const { user, token } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [summary, setSummary] = useState<ComplianceSummary | null>(null);
  const [evaluations, setEvaluations] = useState<ComplianceEvaluation[]>([]);
  const [checks, setChecks] = useState<ComplianceCheckItem[]>([]);
  const [framework, setFramework] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  function loadAll(forceRefresh = false) {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing from session.");
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      getCustomerEntitlements(shortCode),
      getComplianceSummary(shortCode, forceRefresh),
      getComplianceEvaluations(shortCode),
      getComplianceChecks(shortCode, { status: "FAILED", page_size: 50 }),
    ])
      .then(([ent, sum, evals, checkRes]) => {
        setEnabled(Boolean(ent.continuous_compliance_enabled || sum.has_data));
        setSummary(sum);
        setEvaluations(evals.evaluations || []);
        setChecks(checkRes.checks || []);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load compliance data.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadAll(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getComplianceChecks(shortCode, {
      status: "FAILED",
      framework: framework || undefined,
      page_size: 50,
    })
      .then((res) => setChecks(res.checks || []))
      .catch(() => undefined);
  }, [shortCode, framework, enabled]);

  const filteredChecks = useMemo(() => {
    return [...checks].sort(
      (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
    );
  }, [checks]);

  async function onRefresh() {
    setRefreshing(true);
    try {
      loadAll(true);
    } finally {
      setTimeout(() => setRefreshing(false), 800);
    }
  }

  function onDownloadReport(e: FormEvent) {
    e.preventDefault();
    if (!shortCode || !token) return;
    const url = getComplianceReportUrl(shortCode);
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) throw new Error("Report download failed");
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objectUrl;
        a.download = `compliance-audit-${shortCode}.html`;
        a.click();
        URL.revokeObjectURL(objectUrl);
      })
      .catch(() => setError("Could not download the compliance audit report."));
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Compliance & Hardening</h1>
        <p className="muted">Loading compliance readiness…</p>
      </div>
    );
  }

  if (!enabled && !summary?.has_data) {
    return (
      <div className="page">
        <h1 className="page-title">Compliance & Hardening</h1>
        <p className="page-lead">
          Continuous configuration assessment against CIS, ISO 27001, PCI-DSS, and NIST
          benchmarks is available as an add-on service.
        </p>
        {error && <p className="form-error">{error}</p>}
        <div className="panel">
          <p>
            This service is not active for your organization yet. Request Continuous Compliance
            &amp; Hardening from your{" "}
            <Link to="/services">Service Portfolio</Link> to enable executive scorecards and
            remediation guidance.
          </p>
        </div>
      </div>
    );
  }

  const score = Math.round(Number(summary?.overall_score_percentage || 0));
  const fw = summary?.framework_scores || {};

  return (
    <div className="page compliance-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Compliance & Hardening</h1>
          <p className="page-lead">
            Executive readiness score across configuration benchmarks and regulatory frameworks.
          </p>
        </div>
        <div className="page-header-actions">
          <button type="button" className="btn btn-ghost" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" className="btn btn-primary" onClick={onDownloadReport}>
            Download Compliance Audit Report (PDF)
          </button>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}
      {summary?.message && !summary.has_data && (
        <p className="muted">{summary.message}</p>
      )}

      <section className="compliance-hero panel">
        <div className="compliance-hero-gauge">
          <RadialGauge percent={score} label="Compliance" size={120} />
          <div>
            <div className="compliance-hero-label">Overall Compliance Readiness</div>
            <div className="compliance-hero-score">{score}%</div>
            <p className="muted">
              {summary?.passed_checks ?? 0} passed · {summary?.failed_checks ?? 0} failed ·{" "}
              {summary?.agent_count ?? 0} endpoints · {summary?.policy_count ?? 0} policies
            </p>
            {summary?.last_evaluated_at && (
              <p className="muted">Last evaluated: {summary.last_evaluated_at}</p>
            )}
          </div>
        </div>
        <div className="compliance-fw-grid">
          {FRAMEWORK_TABS.filter((t) => t.id).map((tab) => {
            const block = fw[tab.id as string] || {};
            const pct = Math.round(Number(block.score_percentage || 0));
            return (
              <button
                key={tab.id}
                type="button"
                className={
                  "compliance-fw-card" + (framework === tab.id ? " active" : "")
                }
                onClick={() => setFramework(framework === tab.id ? null : tab.id)}
              >
                <span className="compliance-fw-name">{tab.label}</span>
                <span className="compliance-fw-pct">{pct}%</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header-row">
          <h2 className="panel-title">Framework filter</h2>
        </div>
        <div className="tab-row">
          {FRAMEWORK_TABS.map((tab) => (
            <button
              key={tab.label}
              type="button"
              className={"tab-btn" + (framework === tab.id ? " active" : "")}
              onClick={() => setFramework(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {evaluations.length > 0 && (
        <section className="panel">
          <h2 className="panel-title">Active policies</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Endpoint</th>
                  <th>Policy</th>
                  <th>Score</th>
                  <th>Pass / Fail</th>
                  <th>Frameworks</th>
                </tr>
              </thead>
              <tbody>
                {evaluations.map((ev) => (
                  <tr key={ev.id}>
                    <td>{ev.endpoint_name}</td>
                    <td>{ev.title}</td>
                    <td>{Math.round(Number(ev.score))}%</td>
                    <td>
                      {ev.pass_count} / {ev.fail_count}
                    </td>
                    <td>{(ev.compliance_frameworks || []).join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel">
        <h2 className="panel-title">Failed policy checks</h2>
        <p className="muted">Sorted by severity. Expand a row for remediation guidance.</p>
        {filteredChecks.length === 0 ? (
          <p className="muted">No failed checks for this filter.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Check</th>
                  <th>Endpoint</th>
                  <th>Frameworks</th>
                </tr>
              </thead>
              <tbody>
                {filteredChecks.map((ch) => {
                  const open = expanded === ch.id;
                  return (
                    <Fragment key={ch.id}>
                      <tr
                        className="clickable-row"
                        onClick={() => setExpanded(open ? null : ch.id)}
                      >
                        <td>
                          <span className={`severity-pill severity-${ch.severity}`}>
                            {ch.severity}
                          </span>
                        </td>
                        <td>{ch.rule_title}</td>
                        <td>{ch.endpoint_name || "—"}</td>
                        <td>{(ch.compliance_frameworks || []).join(", ") || "—"}</td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={4}>
                            <div className="compliance-remediation">
                              {ch.rationale && (
                                <>
                                  <strong>Why it matters</strong>
                                  <p>{ch.rationale}</p>
                                </>
                              )}
                              <strong>Remediation</strong>
                              <p>
                                {ch.remediation ||
                                  "Follow your MSSP hardening runbook for this control."}
                              </p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
