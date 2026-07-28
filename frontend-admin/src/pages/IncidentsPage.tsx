import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getIncidents } from "../api/admin";
import RowActionsMenu from "../components/RowActionsMenu";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";

function isOpenStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s === "open" || s === "investigating" || s === "in_progress" || s === "new";
}

export default function IncidentsPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const statusFilter = params.get("status");
  const severityFilter = params.get("severity");
  const { status, data, errorMessage } = useAdminQuery(
    () =>
      getIncidents(
        statusFilter && statusFilter !== "open"
          ? { status: statusFilter, ...(severityFilter ? { severity: severityFilter } : {}) }
          : severityFilter
            ? { severity: severityFilter }
            : undefined
      ),
    [statusFilter, severityFilter]
  );

  const incidents =
    status === "success" && data
      ? data.incidents.filter((i) => {
          if (statusFilter === "open") {
            if (!isOpenStatus(i.status)) return false;
          } else if (statusFilter && i.status.toLowerCase() !== statusFilter.toLowerCase()) {
            return false;
          }
          if (severityFilter && i.severity.toLowerCase() !== severityFilter.toLowerCase()) {
            return false;
          }
          return true;
        })
      : [];

  const filterBits = [
    statusFilter ? `status=${statusFilter}` : null,
    severityFilter ? `severity=${severityFilter}` : null,
  ].filter(Boolean);

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">
        Open and historical incidents across all tenants (latest 100). Use the ⋯ menu to open the
        investigation workspace.
        {filterBits.length ? (
          <>
            {" "}
            Filtered by <strong>{filterBits.join(" · ")}</strong>
            {" · "}
            <Link to="/incidents">Clear filter</Link>
          </>
        ) : null}
      </p>

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
            No incidents{statusFilter ? ` matching “${statusFilter}”` : ""} yet.
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
