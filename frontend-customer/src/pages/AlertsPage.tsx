import { Link, useSearchParams } from "react-router-dom";
import { getCustomerAlerts } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import SeverityPill from "../components/SeverityPill";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

function matchesSeverityFilter(severity: string, filter: string | null): boolean {
  if (!filter) return true;
  const s = severity.toLowerCase();
  const f = filter.toLowerCase();
  if (f === "urgent" || f === "high_critical" || f === "high,critical") {
    return s === "high" || s === "critical";
  }
  return s === f;
}

export default function AlertsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [params] = useSearchParams();
  const severityFilter = params.get("severity");
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

  const alerts =
    status === "success" && data
      ? data.alerts.filter((a) => matchesSeverityFilter(a.severity, severityFilter))
      : [];

  const filterLabel =
    severityFilter === "urgent"
      ? "High + Critical"
      : severityFilter
        ? severityFilter
        : null;

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-subtitle">
        Read-only customer-visible alerts for your organization. Internal SOC-only alerts are not
        shown here.
        {filterLabel ? (
          <>
            {" "}
            Filtered by severity: <strong style={{ textTransform: "capitalize" }}>{filterLabel}</strong>
            {" · "}
            <Link to="/alerts">Clear filter</Link>
          </>
        ) : null}
      </p>

      {status === "loading" && <div className="state-message">Loading alerts...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        alerts.length === 0 ? (
          <div className="state-message">
            No customer-visible alerts{filterLabel ? ` matching “${filterLabel}”` : ""} right now.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Detection</th>
                <th>Summary</th>
                <th>Hostname</th>
                <th>Detected</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.alert_id}>
                  <td>
                    <Link to={`/alerts/${encodeURIComponent(alert.alert_id)}`}>{alert.title}</Link>
                  </td>
                  <td>
                    <SeverityPill value={alert.severity} filterBase="/alerts" />
                  </td>
                  <td>
                    <SeverityPill value={alert.status} kind="status" filterBase="/alerts" />
                  </td>
                  <td className="cell-mono">{alert.source}</td>
                  <td>{alert.summary ?? alert.description ?? "—"}</td>
                  <td className="cell-mono">{alert.hostname ?? "—"}</td>
                  <td className="cell-mono">{alert.detected_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
