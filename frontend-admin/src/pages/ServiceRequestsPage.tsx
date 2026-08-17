import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  ConsultationRequest,
  ConsultationRequestStatus,
  listConsultationRequests,
  patchConsultationRequest,
} from "../api/admin";
import { formatScopeSummary } from "../data/serviceCatalog";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import { useCustomerScope } from "../hooks/useCustomerScope";

const STATUS_OPTIONS: ConsultationRequestStatus[] = [
  "PENDING_CONSULTATION",
  "UNDER_REVIEW",
  "APPROVED",
  "PROVISIONED",
  "DECLINED",
  "CLOSED",
];

export default function ServiceRequestsPage() {
  const { tenantId } = useCustomerScope();
  const [params] = useSearchParams();
  const highlightId = params.get("id");
  const serviceKeyFilter = params.get("service_key") || "";
  const [rows, setRows] = useState<ConsultationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState(params.get("status") || "");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notesDraft, setNotesDraft] = useState<Record<string, string>>({});

  function refresh() {
    setLoading(true);
    listConsultationRequests(statusFilter || undefined, serviceKeyFilter || undefined, tenantId)
      .then((res) => {
        setRows(res.requests || []);
        setError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
        else setError("Could not load service requests.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, serviceKeyFilter, tenantId]);

  const sorted = useMemo(() => {
    if (!highlightId) return rows;
    return [...rows].sort((a, b) => Number(b.id === highlightId) - Number(a.id === highlightId));
  }, [rows, highlightId]);

  async function updateStatus(id: string, status: ConsultationRequestStatus) {
    setBusyId(id);
    try {
      const updated = await patchConsultationRequest(id, {
        status,
        admin_notes: notesDraft[id] ?? undefined,
      });
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
      else setError("Could not update request.");
    } finally {
      setBusyId(null);
    }
  }

  async function saveNotes(id: string) {
    setBusyId(id);
    try {
      const updated = await patchConsultationRequest(id, {
        admin_notes: notesDraft[id] || "",
      });
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
      else setError("Could not save notes.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <h1 className="page-title">Service Request Management</h1>
      <CustomerScopeBanner />
      <p className="page-subtitle">
        Cross-tenant consultation and upgrade requests. Catalog view:{" "}
        <Link to="/services">Service Catalog</Link>.
        {serviceKeyFilter ? (
          <>
            {" "}
            Filtered by service <strong>{serviceKeyFilter}</strong>.{" "}
            <Link to="/service-requests">Clear filter</Link>.
          </>
        ) : null}
      </p>

      <div className="form-grid" style={{ maxWidth: 280, marginBottom: "1rem" }}>
        <label className="form-label">
          Status filter
          <select
            className="form-input"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <div className="state-message">Loading…</div>}
      {error && <div className="state-message state-error">{error}</div>}

      {!loading && !error && sorted.length === 0 && (
        <div className="state-message">No service requests match this filter.</div>
      )}

      {!loading && sorted.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Tenant</th>
              <th>Requested Service</th>
              <th>Estimated Scope</th>
              <th>Pricing Tier</th>
              <th>Contact</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.id}
                className={highlightId === r.id ? "row-highlight" : undefined}
                id={`req-${r.id}`}
              >
                <td>
                  <div>{r.tenant_name || "—"}</div>
                  <div className="cell-mono">
                    {r.short_code ? (
                      <Link to={`/tenants?q=${encodeURIComponent(r.short_code)}`}>
                        {r.short_code}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </div>
                </td>
                <td>
                  <div>{r.service_name}</div>
                  <div className="cell-mono" style={{ fontSize: "0.75rem" }}>
                    {r.id.slice(0, 8)}…
                  </div>
                </td>
                <td>{formatScopeSummary(r)}</td>
                <td>{r.pricing_tier || "—"}</td>
                <td>
                  <div>{r.contact_name || r.requested_by_name || "—"}</div>
                  <div className="cell-mono" style={{ fontSize: "0.75rem" }}>
                    {r.contact_email || "—"}
                  </div>
                </td>
                <td>
                  <span className={"pill-status pill-status--" + r.status.toLowerCase()}>
                    {r.status}
                  </span>
                </td>
                <td style={{ minWidth: 260 }}>
                  <select
                    className="form-input"
                    value={r.status}
                    disabled={busyId === r.id}
                    onChange={(e) =>
                      updateStatus(r.id, e.target.value as ConsultationRequestStatus)
                    }
                  >
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <textarea
                    className="form-input"
                    rows={2}
                    style={{ marginTop: 6 }}
                    placeholder="Admin notes"
                    value={notesDraft[r.id] ?? r.admin_notes ?? ""}
                    onChange={(e) =>
                      setNotesDraft((prev) => ({ ...prev, [r.id]: e.target.value }))
                    }
                  />
                  <button
                    className="btn btn-ghost"
                    type="button"
                    style={{ marginTop: 4 }}
                    disabled={busyId === r.id}
                    onClick={() => saveNotes(r.id)}
                  >
                    Save notes
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
