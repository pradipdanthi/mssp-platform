import { getAlerts } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function AlertsPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getAlerts(), []);

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-subtitle">Most recent security alerts across all tenants (latest 100).</p>

      {status === "loading" && <div className="state-message">Loading alerts...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view alerts.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.alerts.length === 0 ? (
          <div className="state-message">No alerts yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Severity</th>
                <th>Title</th>
                <th>Source</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.alerts.map((alert) => (
                <tr key={alert.id}>
                  <td>{alert.tenant_name}</td>
                  <td>
                    <span className={`badge badge-${alert.severity}`}>{alert.severity}</span>
                  </td>
                  <td>{alert.alert_title}</td>
                  <td>{alert.source_tool ?? "—"}</td>
                  <td>
                    <span className={`badge badge-${alert.status}`}>{alert.status}</span>
                  </td>
                  <td>{alert.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
