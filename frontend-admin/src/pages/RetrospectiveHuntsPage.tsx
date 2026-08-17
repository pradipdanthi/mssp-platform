import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getRetrospectiveHunts,
  type RetrospectiveHuntJob,
} from "../api/admin";
import { ApiError } from "../api/client";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import { useCustomerScope } from "../hooks/useCustomerScope";

/**
 * Global Retrospective Monitor — cross-tenant hunt jobs (appliance + cloud).
 */
export default function RetrospectiveHuntsPage() {
  const { tenantId } = useCustomerScope();
  const [jobs, setJobs] = useState<RetrospectiveHuntJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  function load() {
    setLoading(true);
    setError(null);
    getRetrospectiveHunts({
      status: status || undefined,
      page_size: 100,
      ...(tenantId ? { tenant_id: tenantId } : {}),
    })
      .then((res) => setJobs(res.jobs || []))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load retrospective hunts.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, tenantId]);

  return (
    <div className="page">
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1 className="page-title">Retrospective hunts</h1>
      <CustomerScopeBanner />
      <p className="page-subtitle">
        Kevantic Retrospective Engine jobs across all tenants — LOCAL_APPLIANCE (Modes 2/4) and
        CLOUD_SOC (Modes 1/3).
      </p>

      <div className="command-chip-row" style={{ marginBottom: "1rem" }}>
        {["", "PENDING", "RUNNING", "COMPLETED", "FAILED"].map((s) => (
          <button
            key={s || "all"}
            type="button"
            className={"command-chip" + (status === s ? " is-active" : "")}
            onClick={() => setStatus(s)}
          >
            {s || "All"}
          </button>
        ))}
        <button type="button" className="command-chip" onClick={load}>
          Refresh
        </button>
      </div>

      {loading && <div className="state-message">Loading hunts…</div>}
      {error && <div className="state-message state-error">{error}</div>}

      {!loading && !error && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Tenant</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Matches</th>
              <th>Lookback</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 ? (
              <tr>
                <td colSpan={7}>No hunt jobs yet.</td>
              </tr>
            ) : (
              jobs.map((j) => (
                <tr key={j.id}>
                  <td className="cell-mono">{j.created_at ?? "—"}</td>
                  <td>
                    {j.tenant_name ?? "—"}{" "}
                    <span className="muted cell-mono">{j.short_code}</span>
                  </td>
                  <td>{j.execution_mode}</td>
                  <td>{j.status}</td>
                  <td>{j.matches_count ?? 0}</td>
                  <td>{j.lookback_days ?? 90}d</td>
                  <td>{j.source ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
