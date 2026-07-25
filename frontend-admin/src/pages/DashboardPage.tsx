import { Link } from "react-router-dom";
import { getDashboard } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function DashboardPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getDashboard(), []);

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>
      <p className="page-subtitle">Platform-wide security operations summary.</p>

      {status === "loading" && <div className="state-message">Loading dashboard...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view this data.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        <>
          <div className="card-grid">
            <StatCard label="Tenants" value={data.overview.total_tenants} to="/tenants" />
            <StatCard label="Active Tenants" value={data.overview.active_tenants} to="/tenants" />
            <StatCard label="Appliances" value={data.overview.total_appliances} to="/appliances" />
            <StatCard
              label="Online Appliances"
              value={data.overview.online_appliances}
              to="/appliances"
            />
            <StatCard
              label="Offline Appliances"
              value={data.overview.offline_appliances}
              to="/appliances"
            />
            <StatCard
              label="Protected Assets"
              value={data.overview.protected_assets}
              to="/appliances"
            />
            <StatCard label="Total Alerts" value={data.overview.total_alerts} to="/alerts" />
            <StatCard
              label="High/Critical Alerts"
              value={data.overview.high_or_critical_alerts}
              to="/alerts"
            />
            <StatCard label="New Alerts" value={data.overview.new_alerts} to="/alerts" />
            <StatCard label="Open Incidents" value={data.overview.open_incidents} to="/incidents" />
            <StatCard label="Open Recommendations" value={data.overview.open_recommendations} to="/recommendations" />
            <StatCard label="Notifications Sent" value={data.overview.notifications_sent} to="/notifications" />
          </div>

          <h2 className="section-title">Alert Severity Breakdown</h2>
          {data.severity_breakdown.length === 0 ? (
            <div className="state-message">No alert data yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {data.severity_breakdown.map((row) => (
                  <tr key={row.severity}>
                    <td>
                      <span className={`badge badge-${row.severity}`}>{row.severity}</span>
                    </td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  to,
}: {
  label: string;
  value: number;
  to?: string;
}) {
  const body = (
    <>
      <div className="stat-card-value">{value}</div>
      <div className="stat-card-label">{label}</div>
    </>
  );
  if (to) {
    return (
      <Link className="stat-card stat-card-link" to={to} aria-label={`Open ${label}`}>
        {body}
      </Link>
    );
  }
  return <div className="stat-card">{body}</div>;
}
