import { Link } from "react-router-dom";
import { getCustomerDashboardV2 } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function DashboardPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerDashboardV2(shortCode as string),
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
      <p className="page-subtitle">
        Read-only security posture overview for your organization. All sections use your own
        tenant data only.
      </p>

      {status === "loading" && <div className="state-message">Loading dashboard...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        <>
          <section className="dashboard-welcome">
            <div className="dashboard-welcome-text">
              <h2 className="dashboard-welcome-title">
                {user?.full_name ? `Welcome, ${user.full_name}` : "Welcome"}
              </h2>
              <p className="dashboard-welcome-meta">
                {data.tenant.name}
                <span className="dashboard-welcome-sep">·</span>
                {data.tenant.short_code}
              </p>
            </div>
          </section>

          <div className="card-grid dashboard-kpi-grid">
            <StatCard label="Open incidents" value={data.kpis.open_incidents} />
            <StatCard label="High/critical alerts" value={data.kpis.high_critical_alerts} />
            <StatCard label="Open recommendations" value={data.kpis.open_recommendations} />
            <StatCard label="Assets monitored" value={data.kpis.assets_monitored} />
            <StatCard
              label="Appliances online"
              value={data.kpis.appliances_online}
              hint={`${data.kpis.appliances_other} other`}
            />
            <StatCard
              label="Latest report"
              valueLabel={
                data.latest_report
                  ? String(data.latest_report.report_month)
                  : "None"
              }
            />
          </div>

          <div className="dashboard-section-header">
            <h2 className="section-title">Recent incidents</h2>
            <Link className="dashboard-section-link" to="/incidents">
              View all
            </Link>
          </div>
          {data.recent_incidents.length === 0 ? (
            <div className="state-message">No incidents to show right now.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Incident</th>
                  <th>Title</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Summary</th>
                  <th>Opened</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_incidents.map((inc) => (
                  <tr key={inc.incident_number}>
                    <td>
                      <Link to={`/incidents/${encodeURIComponent(inc.incident_number)}`}>
                        {inc.incident_number}
                      </Link>
                    </td>
                    <td>
                      <Link to={`/incidents/${encodeURIComponent(inc.incident_number)}`}>
                        {inc.title}
                      </Link>
                    </td>
                    <td>
                      <span className={`badge badge-${inc.severity}`}>{inc.severity}</span>
                    </td>
                    <td>{inc.status}</td>
                    <td>{inc.customer_visible_summary ?? "—"}</td>
                    <td>{inc.opened_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="dashboard-section-header">
            <h2 className="section-title">Recent recommendations</h2>
            <Link className="dashboard-section-link" to="/recommendations">
              View all
            </Link>
          </div>
          {data.recent_recommendations.length === 0 ? (
            <div className="state-message">No recommendations to show right now.</div>
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
                {data.recent_recommendations.map((rec) => (
                  <tr key={rec.recommendation_id}>
                    <td>
                      <Link to={`/recommendations/${encodeURIComponent(rec.recommendation_id)}`}>
                        {rec.title}
                      </Link>
                    </td>
                    <td>
                      <span className={`badge badge-${rec.priority}`}>{rec.priority}</span>
                    </td>
                    <td>{rec.status}</td>
                    <td>{rec.due_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="dashboard-section-header">
            <h2 className="section-title">Recent alerts</h2>
            <Link className="dashboard-section-link" to="/alerts">
              View all
            </Link>
          </div>
          {data.recent_alerts.length === 0 ? (
            <div className="state-message">No customer-visible alerts to show right now.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Source</th>
                  <th>Summary</th>
                  <th>Detected</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_alerts.map((alert) => (
                  <tr key={alert.alert_id}>
                    <td>
                      <Link to={`/alerts/${encodeURIComponent(alert.alert_id)}`}>{alert.title}</Link>
                    </td>
                    <td>
                      <span className={`badge badge-${alert.severity}`}>{alert.severity}</span>
                    </td>
                    <td>{alert.status}</td>
                    <td>{alert.source}</td>
                    <td>{alert.summary ?? alert.description ?? "—"}</td>
                    <td>{alert.detected_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="dashboard-section-header">
            <h2 className="section-title">Latest report</h2>
            <Link className="dashboard-section-link" to="/reports">
              View all
            </Link>
          </div>
          {!data.latest_report ? (
            <div className="state-message">No published monthly reports yet.</div>
          ) : (
            <div className="dashboard-report-card">
              <div className="dashboard-report-card-body">
                <div className="dashboard-report-card-title">
                  <Link to={`/reports/${encodeURIComponent(data.latest_report.report_id)}`}>
                    {data.latest_report.title}
                  </Link>
                </div>
                <div className="dashboard-report-card-meta">
                  <span>{String(data.latest_report.report_month)}</span>
                  <span className="dashboard-welcome-sep">·</span>
                  <span>{data.latest_report.status}</span>
                  {data.latest_report.published_at ? (
                    <>
                      <span className="dashboard-welcome-sep">·</span>
                      <span>Published {data.latest_report.published_at}</span>
                    </>
                  ) : null}
                </div>
                <p className="dashboard-report-card-summary">
                  {data.latest_report.summary ?? "No executive summary provided."}
                </p>
              </div>
              <Link
                className="btn btn-ghost"
                to={`/reports/${encodeURIComponent(data.latest_report.report_id)}`}
              >
                Open report
              </Link>
            </div>
          )}

          <div className="dashboard-section-header">
            <h2 className="section-title">Appliance health</h2>
            <Link className="dashboard-section-link" to="/assets">
              View assets
            </Link>
          </div>
          <p className="dashboard-inline-summary">
            {data.kpis.assets_monitored} protected asset
            {data.kpis.assets_monitored === 1 ? "" : "s"} monitored ·{" "}
            {data.kpis.appliances_online} appliance
            {data.kpis.appliances_online === 1 ? "" : "s"} online ·{" "}
            {data.kpis.appliances_other} other
          </p>
          {data.recent_appliances.length === 0 ? (
            <div className="state-message">No appliances reported for your organization yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Appliance</th>
                  <th>Site</th>
                  <th>Status</th>
                  <th>Health</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_appliances.map((row) => (
                  <tr key={`${row.appliance_name}-${row.site_name}`}>
                    <td>{row.appliance_name}</td>
                    <td>{row.site_name}</td>
                    <td>
                      <span className={`badge badge-${row.status}`}>{row.status}</span>
                    </td>
                    <td>{row.health_status ?? "Unknown"}</td>
                    <td>{row.last_seen_at ?? "Never"}</td>
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
  valueLabel,
  hint,
}: {
  label: string;
  value?: number;
  valueLabel?: string;
  hint?: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-card-value">{valueLabel ?? value}</div>
      <div className="stat-card-label">{label}</div>
      {hint ? <div className="stat-card-hint">{hint}</div> : null}
    </div>
  );
}
