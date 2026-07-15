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
            <StatCard label="Tenants" value={data.overview.total_tenants} />
            <StatCard label="Active Tenants" value={data.overview.active_tenants} />
            <StatCard label="Appliances" value={data.overview.total_appliances} />
            <StatCard label="Online Appliances" value={data.overview.online_appliances} />
            <StatCard label="Offline Appliances" value={data.overview.offline_appliances} />
            <StatCard label="Protected Assets" value={data.overview.protected_assets} />
            <StatCard label="Total Alerts" value={data.overview.total_alerts} />
            <StatCard label="High/Critical Alerts" value={data.overview.high_or_critical_alerts} />
            <StatCard label="New Alerts" value={data.overview.new_alerts} />
            <StatCard label="Open Incidents" value={data.overview.open_incidents} />
            <StatCard label="Open Recommendations" value={data.overview.open_recommendations} />
            <StatCard label="Notifications Sent" value={data.overview.notifications_sent} />
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

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat-card">
      <div className="stat-card-value">{value}</div>
      <div className="stat-card-label">{label}</div>
    </div>
  );
}
