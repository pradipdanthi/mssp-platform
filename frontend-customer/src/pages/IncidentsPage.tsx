import { Link, useSearchParams } from "react-router-dom";
import { getCustomerIncidents } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import SeverityPill from "../components/SeverityPill";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

const STATUS_OPTIONS = [
  { value: "open", label: "Open (active)" },
  { value: "in_progress", label: "In progress" },
  { value: "waiting_customer", label: "Waiting customer" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const SEVERITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "urgent", label: "High + Critical" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export default function IncidentsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status") ?? "";
  const severityFilter = params.get("severity") ?? "";
  const qFilter = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;

  function patchParams(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  const { status, data, errorMessage } = useCustomerQuery(
    () =>
      getCustomerIncidents(shortCode as string, {
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    Boolean(shortCode),
    [shortCode, statusFilter, severityFilter, qFilter, page, pageSize]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Incidents</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so incident data cannot be loaded.
        </div>
      </div>
    );
  }

  const incidents = status === "success" && data ? data.incidents : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? incidents.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">
        Read-only customer-visible incidents for your organization. Search and paginate when many
        tickets are open.
      </p>

      <ListToolbar
        searchPlaceholder="Search number, title, host, or summary…"
        searchValue={qFilter}
        onSearchChange={(q) => patchParams({ q, page: "1" })}
        statusOptions={STATUS_OPTIONS}
        statusValue={statusFilter}
        onStatusChange={(status) => patchParams({ status, page: "1" })}
        severityOptions={SEVERITY_OPTIONS}
        severityValue={severityFilter}
        onSeverityChange={(severity) => patchParams({ severity, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {status === "loading" && <div className="state-message">Loading incidents...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        incidents.length === 0 ? (
          <div className="state-message">
            No incidents{statusFilter ? ` matching “${statusFilter}”` : ""} in this view.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Incident</th>
                <th>Title</th>
                <th>Asset</th>
                <th>Device</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Summary</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => (
                <tr key={inc.incident_number}>
                  <td className="cell-mono">
                    <Link to={`/incidents/${encodeURIComponent(inc.incident_number)}`}>
                      {inc.incident_number}
                    </Link>
                  </td>
                  <td>
                    <Link to={`/incidents/${encodeURIComponent(inc.incident_number)}`}>
                      {inc.title}
                    </Link>
                  </td>
                  <td className="cell-mono">{inc.hostname ?? "—"}</td>
                  <td>{inc.device_type ?? "—"}</td>
                  <td>
                    <SeverityPill value={inc.severity} />
                  </td>
                  <td>
                    <SeverityPill value={inc.status} kind="status" />
                  </td>
                  <td>{inc.customer_visible_summary ?? "—"}</td>
                  <td className="cell-mono">{inc.opened_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
