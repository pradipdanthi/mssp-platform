import { getCustomerDashboard } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function AssetsPage() {
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
        <h1 className="page-title">Assets</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so asset posture cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Assets</h1>
      <p className="page-subtitle">
        Read-only appliance health from your customer dashboard (protected-asset detail API is not
        included in this foundation).
      </p>

      {status === "loading" && <div className="state-message">Loading asset posture...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.appliance_health.length === 0 ? (
          <div className="state-message">No appliances reported for your organization yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Appliance</th>
                <th>Site</th>
                <th>Status</th>
                <th>Health</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {data.appliance_health.map((row) => (
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
        )
      )}
    </div>
  );
}
