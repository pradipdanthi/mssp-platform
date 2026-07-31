import { FormEvent, Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  EasmAsset,
  EasmFinding,
  EasmSummary,
  getCustomerEntitlements,
  getEasmAssets,
  getEasmFindings,
  getEasmSummary,
  registerEasmDomain,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const SEV_FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

/**
 * External Attack Surface Management — customer perimeter view.
 * Capability labels only (MSSP External Surface Scanner).
 */
export default function EasmPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const isAdmin = user?.role === "customer_admin";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [summary, setSummary] = useState<EasmSummary | null>(null);
  const [assets, setAssets] = useState<EasmAsset[]>([]);
  const [findings, setFindings] = useState<EasmFinding[]>([]);
  const [severity, setSeverity] = useState("ALL");
  const [showModal, setShowModal] = useState(false);
  const [domainInput, setDomainInput] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  function loadAll() {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing from session.");
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      getCustomerEntitlements(shortCode),
      getEasmSummary(shortCode),
      getEasmAssets(shortCode),
      getEasmFindings(shortCode, { page_size: 100 }),
    ])
      .then(([ent, sum, assetRes, findingRes]) => {
        setEnabled(Boolean(ent.external_attack_surface_enabled || sum.has_data));
        setSummary(sum);
        setAssets(assetRes.assets || []);
        setFindings(findingRes.findings || []);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load attack surface data.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getEasmFindings(shortCode, {
      severity: severity === "ALL" ? undefined : severity,
      page_size: 100,
    })
      .then((res) => setFindings(res.findings || []))
      .catch(() => undefined);
  }, [shortCode, severity, enabled]);

  async function onRegister(e: FormEvent) {
    e.preventDefault();
    if (!shortCode || !domainInput.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await registerEasmDomain(shortCode, {
        domain_or_ip: domainInput.trim(),
        notes: notes.trim() || undefined,
        start_scan: true,
      });
      setShowModal(false);
      setDomainInput("");
      setNotes("");
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register domain.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">External Attack Surface</h1>
        <p className="muted">Loading perimeter discovery…</p>
      </div>
    );
  }

  if (!enabled && !summary?.has_data) {
    return (
      <div className="page">
        <h1 className="page-title">External Attack Surface</h1>
        <p className="page-lead">
          Monitor public domains, subdomains, open ports, and TLS exposure from an
          attacker&apos;s perspective.
        </p>
        {error && <p className="form-error">{error}</p>}
        <div className="panel">
          <p>
            No external assets are registered yet.{" "}
            {isAdmin ? (
              <>
                Use <strong>Register New Domain</strong> below, or request the service from your{" "}
                <Link to="/services">Service Portfolio</Link>.
              </>
            ) : (
              <>
                Ask a customer admin to register a primary domain, or request the service from{" "}
                <Link to="/services">Service Portfolio</Link>.
              </>
            )}
          </p>
          {isAdmin && (
            <button type="button" className="btn btn-primary" onClick={() => setShowModal(true)}>
              Register New Domain
            </button>
          )}
        </div>
        {showModal && renderModal()}
      </div>
    );
  }

  function renderModal() {
    return (
      <div className="modal-backdrop" role="dialog" aria-modal="true">
        <div className="modal-panel">
          <h2 className="panel-title">Register New Domain</h2>
          <p className="muted">
            Add a primary public domain or IPv4 address for perimeter monitoring by the{" "}
            {summary?.scanner_label || "MSSP External Surface Scanner"}.
          </p>
          <form onSubmit={onRegister} className="form-stack">
            <label>
              Domain or public IP
              <input
                value={domainInput}
                onChange={(ev) => setDomainInput(ev.target.value)}
                placeholder="example.com"
                required
                autoFocus
              />
            </label>
            <label>
              Notes (optional)
              <textarea
                value={notes}
                onChange={(ev) => setNotes(ev.target.value)}
                rows={3}
                placeholder="Business unit, owner, change window…"
              />
            </label>
            <div className="page-header-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setShowModal(false)}
                disabled={submitting}
              >
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? "Scanning…" : "Register & scan"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="page easm-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">External Attack Surface</h1>
          <p className="page-lead">
            Perimeter assets discovered by the {summary?.scanner_label || "MSSP External Surface Scanner"}.
          </p>
        </div>
        {isAdmin && (
          <button type="button" className="btn btn-primary" onClick={() => setShowModal(true)}>
            Register New Domain
          </button>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      <section className="easm-kpi-grid">
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">External assets</div>
          <div className="easm-kpi-value">{summary?.total_external_assets ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Open public ports</div>
          <div className="easm-kpi-value">{summary?.open_public_ports ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Expiring / expired SSL</div>
          <div className="easm-kpi-value">{summary?.expiring_ssl_certificates ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Perimeter vulnerabilities</div>
          <div className="easm-kpi-value">{summary?.perimeter_vulnerabilities ?? 0}</div>
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Discovered assets</h2>
        {assets.length === 0 ? (
          <p className="muted">No assets yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Type</th>
                  <th>Source</th>
                  <th>Last seen</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((a) => (
                  <tr key={a.id}>
                    <td>{a.domain_or_ip}</td>
                    <td>{a.asset_type.replace(/_/g, " ")}</td>
                    <td>{a.discovery_source_label}</td>
                    <td>{a.last_seen || "—"}</td>
                    <td>{a.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header-row">
          <h2 className="panel-title">Perimeter findings</h2>
        </div>
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
                  <th>Finding</th>
                  <th>Asset</th>
                  <th>Type</th>
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
                        <td>{f.title}</td>
                        <td>{f.asset_name}</td>
                        <td>{f.finding_type.replace(/_/g, " ")}</td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={4}>
                            <div className="compliance-remediation">
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

      {showModal && renderModal()}
    </div>
  );
}
