import { useState } from "react";
import {
  AdminVulnerability,
  getVulnerabilities,
  getVulnerabilityDetail,
  promoteVulnerabilityRecommendation,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) {
      return "Access denied. platform_admin or soc_manager can promote findings.";
    }
  }
  return fallback;
}

export default function VulnerabilitiesPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin" || user?.role === "soc_manager";
  const { status, data, errorMessage, refetch } = useAdminQuery(() => getVulnerabilities(), []);

  const [selected, setSelected] = useState<AdminVulnerability | null>(null);
  const [detailNotes, setDetailNotes] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [makeVisible, setMakeVisible] = useState(false);

  async function openDetail(row: AdminVulnerability) {
    setActionError(null);
    setSuccessMessage(null);
    setSelected(row);
    setDetailNotes(null);
    try {
      const detail = await getVulnerabilityDetail(row.id);
      setSelected(detail);
      const bits = [
        detail.customer_safe_summary,
        detail.remediation_summary,
        detail.internal_notes ? `Internal notes: ${detail.internal_notes}` : null,
        detail.nvt_oid ? `NVT OID: ${detail.nvt_oid}` : null,
      ].filter(Boolean);
      setDetailNotes(bits.join("\n\n") || "No extra detail.");
    } catch (err) {
      setActionError(apiErrorMessage(err, "Could not load vulnerability detail."));
    }
  }

  async function handlePromote() {
    if (!selected || !canWrite) return;
    setPromoting(true);
    setActionError(null);
    setSuccessMessage(null);
    try {
      const result = await promoteVulnerabilityRecommendation(selected.id, {
        customer_visible: makeVisible,
      });
      setSuccessMessage(
        result.created
          ? `Recommendation created (${result.recommendation_id}). Customer visible: ${
              result.customer_visible ? "yes" : "no"
            }.`
          : `Already linked to recommendation ${result.recommendation_id}.`
      );
      await refetch();
      const refreshed = await getVulnerabilityDetail(selected.id);
      setSelected(refreshed);
    } catch (err) {
      setActionError(apiErrorMessage(err, "Promote failed."));
    } finally {
      setPromoting(false);
    }
  }

  const rows = data?.vulnerabilities ?? [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Vulnerabilities</h1>
          <p className="page-subtitle">
            Greenbone findings normalized into the control plane. Customers never see raw scan
            output — promote high/critical items to recommendations when ready.
          </p>
        </div>
        <button className="btn btn-ghost" type="button" onClick={() => refetch()}>
          Refresh
        </button>
      </div>

      {status === "loading" && <p className="muted">Loading vulnerabilities…</p>}
      {status === "error" && <p className="form-error">{errorMessage}</p>}
      {successMessage && <p className="form-success">{successMessage}</p>}
      {actionError && <p className="form-error">{actionError}</p>}

      {status === "ready" && rows.length === 0 && (
        <p className="muted">No vulnerability findings yet. Ingest via Greenbone sync when ready.</p>
      )}

      {status === "ready" && rows.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Title</th>
                <th>CVE</th>
                <th>Customer</th>
                <th>Asset</th>
                <th>Status</th>
                <th>Recommendation</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span className={`badge severity-${row.severity}`}>{row.severity}</span>
                  </td>
                  <td>{row.title}</td>
                  <td>{row.cve_id || "—"}</td>
                  <td>
                    {row.tenant_name} ({row.short_code})
                  </td>
                  <td>{row.asset_hostname || "—"}</td>
                  <td>{row.status}</td>
                  <td>{row.recommendation_id ? "Linked" : "—"}</td>
                  <td>
                    <button className="btn btn-ghost" type="button" onClick={() => openDetail(row)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="panel" style={{ marginTop: "1.5rem" }}>
          <h2>{selected.title}</h2>
          <p className="muted">
            {selected.severity.toUpperCase()}
            {selected.cve_id ? ` · ${selected.cve_id}` : ""} · {selected.short_code} ·{" "}
            {selected.source_platform}
          </p>
          <pre className="code-block" style={{ whiteSpace: "pre-wrap" }}>
            {detailNotes || "Loading…"}
          </pre>
          {canWrite && !selected.recommendation_id && (
            <div className="form-row" style={{ marginTop: "1rem" }}>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={makeVisible}
                  onChange={(e) => setMakeVisible(e.target.checked)}
                />
                Make recommendation customer-visible immediately
              </label>
              <button
                className="btn btn-primary"
                type="button"
                disabled={promoting}
                onClick={handlePromote}
              >
                {promoting ? "Creating…" : "Promote to recommendation"}
              </button>
            </div>
          )}
          {selected.recommendation_id && (
            <p className="muted">
              Linked recommendation ID: <code>{selected.recommendation_id}</code>
            </p>
          )}
          <button className="btn btn-ghost" type="button" onClick={() => setSelected(null)}>
            Close
          </button>
        </div>
      )}
    </div>
  );
}
