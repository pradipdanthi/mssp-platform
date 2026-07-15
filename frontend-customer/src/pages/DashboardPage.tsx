import { getCustomerDashboard } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function DashboardPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerDashboard(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Dashboard</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so the customer portal cannot load
          tenant-scoped data. Sign in with a customer account that has a tenant assigned.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>
      <p className="page-subtitle">Read-only security posture summary for your organization.</p>

      {status === "loading" && <div className="state-message">Loading dashboard...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        <>
          <div className="card-grid">
            <StatCard label="Appliances" value={data.security_summary.appliances} />
            <StatCard label="Online" value={data.security_summary.online_appliances} />
            <StatCard label="Open Incidents" value={data.security_summary.open_incidents} />
            <StatCard
              label="High/Critical Open"
              value={data.security_summary.high_or_critical_open_incidents}
            />
            <StatCard
              label="Open Recommendations"
              value={data.security_summary.open_recommendations}
            />
          </div>

          <h2 className="section-title">Open Incidents</h2>
          {data.open_incidents.length === 0 ? (
            <div className="state-message">No open incidents.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Incident</th>
                  <th>Title</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Action Required</th>
                </tr>
              </thead>
              <tbody>
                {data.open_incidents.map((inc) => (
                  <tr key={inc.incident_number}>
                    <td>{inc.incident_number}</td>
                    <td>{inc.title}</td>
                    <td>
                      <span className={`badge badge-${inc.severity}`}>{inc.severity}</span>
                    </td>
                    <td>{inc.status}</td>
                    <td>{inc.customer_action_required ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="section-title">Recommendations</h2>
          {data.recommendations.length === 0 ? (
            <div className="state-message">No open recommendations.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Due</th>
                </tr>
              </thead>
              <tbody>
                {data.recommendations.map((rec) => (
                  <tr key={`${rec.title}-${rec.due_at ?? "none"}`}>
                    <td>{rec.title}</td>
                    <td>{rec.priority}</td>
                    <td>{rec.status}</td>
                    <td>{rec.due_at ?? "—"}</td>
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
