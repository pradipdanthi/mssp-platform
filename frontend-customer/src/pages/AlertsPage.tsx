import { getCustomerAlerts } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function AlertsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerAlerts(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Alerts</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so alert data cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-subtitle">
        Read-only customer-visible alerts for your organization. Internal SOC-only alerts are not
        shown here.
      </p>

      {status === "loading" && <div className="state-message">Loading alerts...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.alerts.length === 0 ? (
          <div className="state-message">
            No customer-visible alerts right now. Your SOC team may still be reviewing events that
            are not yet shared with your organization.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Source</th>
                <th>Summary</th>
                <th>Hostname</th>
                <th>Detected</th>
              </tr>
            </thead>
            <tbody>
              {data.alerts.map((alert) => (
                <tr key={alert.alert_id}>
                  <td>{alert.title}</td>
                  <td>
                    <span className={`badge badge-${alert.severity}`}>{alert.severity}</span>
                  </td>
                  <td>{alert.status}</td>
                  <td>{alert.source}</td>
                  <td>{alert.summary ?? alert.description ?? "—"}</td>
                  <td>{alert.hostname ?? "—"}</td>
                  <td>{alert.detected_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
