import { FormEvent, Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  VmaasFinding,
  VmaasSummary,
  createServiceUpgradeRequest,
  getCustomerEntitlements,
  getVmaasFindings,
  getVmaasSummary,
  listServiceUpgradeRequests,
  requestVmaasScan,
  ServiceUpgradeRequest,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import RadialGauge from "../components/RadialGauge";

const SEV_FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

const SCAN_SCOPE_OPTIONS = [
  { value: "external_perimeter", label: "External / internet-facing systems" },
  { value: "internal_network", label: "Internal network hosts" },
  { value: "authenticated_hosts", label: "Authenticated / credentialed host scans" },
  { value: "cloud_workloads", label: "Cloud workloads (IaaS / VMs)" },
  { value: "web_applications", label: "Web applications" },
];

const ENVIRONMENT_OPTIONS = [
  { value: "production", label: "Production" },
  { value: "non_production", label: "Non-production / staging" },
  { value: "remote_workforce", label: "Remote workforce endpoints" },
  { value: "ot_ics", label: "OT / ICS environments" },
];

const COMPLIANCE_OPTIONS = [
  { value: "iso27001", label: "ISO 27001" },
  { value: "soc2", label: "SOC 2" },
  { value: "pci_dss", label: "PCI DSS" },
  { value: "hipaa", label: "HIPAA" },
  { value: "gdpr", label: "GDPR / privacy" },
  { value: "other", label: "Other / internal policy" },
];

type FormState = {
  preferred_cadence: "weekly" | "monthly" | "quarterly" | "unsure";
  scan_scope: string[];
  approximate_assets: string;
  environments: string[];
  urgency: "exploring" | "planning" | "needed_soon" | "urgent";
  compliance_drivers: string[];
  requirements_summary: string;
  preferred_contact: "email" | "phone" | "either";
  contact_phone: string;
};

const EMPTY_FORM: FormState = {
  preferred_cadence: "monthly",
  scan_scope: [],
  approximate_assets: "",
  environments: ["production"],
  urgency: "planning",
  compliance_drivers: [],
  requirements_summary: "",
  preferred_contact: "email",
  contact_phone: "",
};

function toggleList(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * Vulnerability Management (VMaaS) — findings dashboard when active;
 * upgrade request form when not contracted.
 */
export default function VulnerabilitiesPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const isAdmin = user?.role === "customer_admin";
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<VmaasSummary | null>(null);
  const [findings, setFindings] = useState<VmaasFinding[]>([]);
  const [severity, setSeverity] = useState("ALL");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showScanModal, setShowScanModal] = useState(false);
  const [targetRange, setTargetRange] = useState("");
  const [scanning, setScanning] = useState(false);

  // Upgrade-request state (inactive tenants)
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [existing, setExisting] = useState<ServiceUpgradeRequest[]>([]);

  function loadActive() {
    if (!shortCode) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getCustomerEntitlements(shortCode),
      getVmaasSummary(shortCode),
      getVmaasFindings(shortCode, { status: "OPEN", page_size: 100 }),
    ])
      .then(([ent, sum, findRes]) => {
        const on = Boolean(ent.vulnerability_management_enabled || sum.has_data);
        setEnabled(on);
        setSummary(sum);
        setFindings(findRes.findings || []);
        if (!on) {
          listServiceUpgradeRequests(shortCode)
            .then((res) => setExisting(res.requests || []))
            .catch(() => undefined);
        }
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load vulnerability data.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing from session.");
      return;
    }
    loadActive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getVmaasFindings(shortCode, {
      status: "OPEN",
      severity: severity === "ALL" ? undefined : severity,
      page_size: 100,
    })
      .then((res) => setFindings(res.findings || []))
      .catch(() => undefined);
  }, [shortCode, severity, enabled]);

  async function onScan(e: FormEvent) {
    e.preventDefault();
    if (!shortCode) return;
    setScanning(true);
    setError(null);
    try {
      await requestVmaasScan(shortCode, {
        target_range: targetRange.trim() || undefined,
      });
      setShowScanModal(false);
      setTargetRange("");
      loadActive();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start vulnerability scan.");
    } finally {
      setScanning(false);
    }
  }

  async function onUpgradeSubmit(e: FormEvent) {
    e.preventDefault();
    if (!shortCode) return;
    setSubmitting(true);
    setFormError(null);
    setSuccess(null);
    try {
      await createServiceUpgradeRequest(shortCode, {
        service_key: "vulnerability_management",
        preferred_cadence: form.preferred_cadence,
        scan_scope: form.scan_scope,
        approximate_assets: form.approximate_assets
          ? Number(form.approximate_assets)
          : null,
        environments: form.environments,
        urgency: form.urgency,
        compliance_drivers: form.compliance_drivers,
        requirements_summary: form.requirements_summary,
        preferred_contact: form.preferred_contact,
        contact_phone: form.contact_phone || null,
      });
      setSuccess(
        "Thank you. Your Vulnerability Management upgrade request was sent to your MSSP team."
      );
      setShowForm(false);
      setForm(EMPTY_FORM);
      listServiceUpgradeRequests(shortCode)
        .then((res) => setExisting(res.requests || []))
        .catch(() => undefined);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Vulnerability Management</h1>
        <p className="muted">Loading vulnerability posture…</p>
      </div>
    );
  }

  if (!enabled) {
    return (
      <div className="page">
        <h1 className="page-title">Vulnerability Management</h1>
        <p className="page-lead">
          Prioritized CVE findings and remediation guidance from the{" "}
          {summary?.scanner_label || "MSSP Internal Vulnerability Scanner"}.
        </p>
        {error && <p className="form-error">{error}</p>}
        {success && <p className="form-success">{success}</p>}
        <div className="panel">
          <p>
            Vulnerability Management is not active for your organization yet. Request an upgrade
            from your <Link to="/services">Service Portfolio</Link>, or use the form below.
          </p>
          {isAdmin && (
            <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
              Request Vulnerability Management
            </button>
          )}
        </div>
        {existing.length > 0 && (
          <div className="panel">
            <h2 className="panel-title">Your requests</h2>
            <ul>
              {existing.map((r) => (
                <li key={r.id}>
                  {r.service_key} · {r.status} · {r.preferred_cadence}
                </li>
              ))}
            </ul>
          </div>
        )}
        {showForm && (
          <div className="modal-backdrop" role="dialog" aria-modal="true">
            <div className="modal-panel">
              <h2 className="panel-title">Request Vulnerability Management</h2>
              {formError && <p className="form-error">{formError}</p>}
              <form onSubmit={onUpgradeSubmit} className="form-stack">
                <label>
                  Preferred cadence
                  <select
                    value={form.preferred_cadence}
                    onChange={(ev) =>
                      setForm({
                        ...form,
                        preferred_cadence: ev.target.value as FormState["preferred_cadence"],
                      })
                    }
                  >
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="unsure">Unsure</option>
                  </select>
                </label>
                <fieldset>
                  <legend>Scan scope</legend>
                  {SCAN_SCOPE_OPTIONS.map((o) => (
                    <label key={o.value} className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={form.scan_scope.includes(o.value)}
                        onChange={() =>
                          setForm({ ...form, scan_scope: toggleList(form.scan_scope, o.value) })
                        }
                      />
                      {o.label}
                    </label>
                  ))}
                </fieldset>
                <fieldset>
                  <legend>Environments</legend>
                  {ENVIRONMENT_OPTIONS.map((o) => (
                    <label key={o.value} className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={form.environments.includes(o.value)}
                        onChange={() =>
                          setForm({
                            ...form,
                            environments: toggleList(form.environments, o.value),
                          })
                        }
                      />
                      {o.label}
                    </label>
                  ))}
                </fieldset>
                <fieldset>
                  <legend>Compliance drivers</legend>
                  {COMPLIANCE_OPTIONS.map((o) => (
                    <label key={o.value} className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={form.compliance_drivers.includes(o.value)}
                        onChange={() =>
                          setForm({
                            ...form,
                            compliance_drivers: toggleList(form.compliance_drivers, o.value),
                          })
                        }
                      />
                      {o.label}
                    </label>
                  ))}
                </fieldset>
                <label>
                  Approximate assets
                  <input
                    value={form.approximate_assets}
                    onChange={(ev) => setForm({ ...form, approximate_assets: ev.target.value })}
                  />
                </label>
                <label>
                  Requirements summary
                  <textarea
                    required
                    rows={4}
                    value={form.requirements_summary}
                    onChange={(ev) =>
                      setForm({ ...form, requirements_summary: ev.target.value })
                    }
                  />
                </label>
                <div className="page-header-actions">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setShowForm(false)}
                    disabled={submitting}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? "Sending…" : "Submit request"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    );
  }

  const posture = Math.round(Number(summary?.posture_score || 0));

  return (
    <div className="page vmaas-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Vulnerability Management</h1>
          <p className="page-lead">
            Prioritized findings from the {summary?.scanner_label || "MSSP Internal Vulnerability Scanner"}.
          </p>
        </div>
        {isAdmin && (
          <button type="button" className="btn btn-primary" onClick={() => setShowScanModal(true)}>
            Schedule Internal Scan
          </button>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      <section className="compliance-hero panel">
        <div className="compliance-hero-gauge">
          <RadialGauge percent={posture} label="Vuln posture" size={110} />
          <div>
            <div className="compliance-hero-label">Vulnerability posture</div>
            <div className="compliance-hero-score">{posture}%</div>
            <p className="muted">
              Avg CVSS {summary?.average_cvss_score ?? 0} · {summary?.open_findings ?? 0} open findings
            </p>
          </div>
        </div>
      </section>

      <section className="easm-kpi-grid">
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Critical CVEs</div>
          <div className="easm-kpi-value">{summary?.critical_cves ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">High risk</div>
          <div className="easm-kpi-value">{summary?.high_risk_vulnerabilities ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Unpatched assets</div>
          <div className="easm-kpi-value">{summary?.unpatched_assets ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Average CVSS</div>
          <div className="easm-kpi-value">{summary?.average_cvss_score ?? 0}</div>
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Detected vulnerabilities</h2>
        <div className="tab-row">
          {SEV_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              className={"tab-btn" + (severity === s ? " active" : "")}
              onClick={() => setSeverity(s)}
            >
              {s === "ALL" ? "All severities" : s}
            </button>
          ))}
        </div>
        {findings.length === 0 ? (
          <p className="muted">No open findings for this filter.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>CVE</th>
                  <th>Finding</th>
                  <th>Asset</th>
                  <th>CVSS</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f) => {
                  const open = expanded === f.id;
                  return (
                    <Fragment key={f.id}>
                      <tr
                        className="clickable-row"
                        onClick={() => setExpanded(open ? null : f.id)}
                      >
                        <td>
                          <span className={`severity-pill severity-${f.severity.toLowerCase()}`}>
                            {f.severity}
                          </span>
                        </td>
                        <td>{f.cve_id || "—"}</td>
                        <td>{f.title}</td>
                        <td>{f.asset_host}</td>
                        <td>{f.cvss_score != null ? f.cvss_score.toFixed(1) : "—"}</td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={5}>
                            <div className="compliance-remediation">
                              {f.vulnerable_package_or_port && (
                                <>
                                  <strong>Affected component</strong>
                                  <p>{f.vulnerable_package_or_port}</p>
                                </>
                              )}
                              <strong>Details</strong>
                              <p>{f.description}</p>
                              <strong>Remediation</strong>
                              <p>{f.remediation}</p>
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

      <p className="muted">
        Published remediation items also appear under{" "}
        <Link to="/recommendations">Recommendations</Link>.
      </p>

      {showScanModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-panel">
            <h2 className="panel-title">Schedule Internal Scan</h2>
            <p className="muted">
              Specify a target subnet or host list. Leave blank to assess registered endpoints.
            </p>
            <form onSubmit={onScan} className="form-stack">
              <label>
                Target range / hosts
                <input
                  value={targetRange}
                  onChange={(ev) => setTargetRange(ev.target.value)}
                  placeholder="192.168.1.0/24 or host1, host2"
                />
              </label>
              <div className="page-header-actions">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowScanModal(false)}
                  disabled={scanning}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={scanning}>
                  {scanning ? "Scanning…" : "Run assessment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
