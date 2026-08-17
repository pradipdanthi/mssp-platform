import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getIncidents } from "../api/admin";
import ListToolbar from "../components/ListToolbar";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import RowActionsMenu from "../components/RowActionsMenu";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useCustomerScope } from "../hooks/useCustomerScope";

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
  const navigate = useNavigate();
  const { tenantFilter } = useCustomerScope();
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

  const { status, data, errorMessage } = useAdminQuery(
    () =>
      getIncidents({
        page,
        page_size: pageSize,
        ...tenantFilter,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    [tenantFilter, statusFilter, severityFilter, qFilter, page, pageSize]
  );

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
      <CustomerScopeBanner />
      <p className="page-subtitle">
        Open and historical incidents across all tenants. Search by number, title, or tenant; use
        filters and pagination when queues grow large. Use the ⋯ menu to open the investigation
        workspace.
      </p>

      <ListToolbar
        searchPlaceholder="Search number, title, tenant, summary…"
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
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view incidents.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        incidents.length === 0 ? (
          <div className="state-message">
            No incidents{statusFilter ? ` matching “${statusFilter}”` : ""} in this view.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Incident #</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Assigned To</th>
                <th>Opened</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((incident) => (
                <tr key={incident.id}>
                  <td>{incident.tenant_name}</td>
                  <td className="cell-mono">
                    <Link to={`/incidents/${incident.id}`}>{incident.incident_number}</Link>
                  </td>
                  <td>{incident.title}</td>
                  <td>
                    <SeverityPill value={incident.severity} filterBase="/incidents" />
                  </td>
                  <td>
                    <SeverityPill value={incident.status} kind="status" filterBase="/incidents" />
                  </td>
                  <td>{incident.assigned_to ?? "Unassigned"}</td>
                  <td className="cell-mono">{incident.opened_at ?? "—"}</td>
                  <td>
                    <RowActionsMenu
                      actions={[
                        {
                          id: "open",
                          label: "Open detail",
                          onClick: () => navigate(`/incidents/${incident.id}`),
                        },
                        {
                          id: "alerts",
                          label: "Related alerts",
                          onClick: () =>
                            navigate(`/alerts?severity=${encodeURIComponent(incident.severity)}`),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
