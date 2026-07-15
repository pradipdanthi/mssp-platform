import { getIncidents } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function IncidentsPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getIncidents(), []);

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">Open and historical incidents across all tenants (latest 100).</p>

      {status === "loading" && <div className="state-message">Loading incidents...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view incidents.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.incidents.length === 0 ? (
          <div className="state-message">No incidents yet.</div>
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
              </tr>
            </thead>
            <tbody>
              {data.incidents.map((incident) => (
                <tr key={incident.id}>
                  <td>{incident.tenant_name}</td>
                  <td>{incident.incident_number}</td>
                  <td>{incident.title}</td>
                  <td>
                    <span className={`badge badge-${incident.severity}`}>{incident.severity}</span>
                  </td>
                  <td>
                    <span className={`badge badge-${incident.status}`}>{incident.status}</span>
                  </td>
                  <td>{incident.assigned_to ?? "Unassigned"}</td>
                  <td>{incident.opened_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
