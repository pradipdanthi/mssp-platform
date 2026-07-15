import { getTenants } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function TenantsPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getTenants(), []);

  return (
    <div>
      <h1 className="page-title">Tenants</h1>
      <p className="page-subtitle">Read-only view. Tenant create/edit is planned for a future module.</p>

      {status === "loading" && <div className="state-message">Loading tenants...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view tenants.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.tenants.length === 0 ? (
          <div className="state-message">No tenants yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Short Code</th>
                <th>Status</th>
                <th>SLA Level</th>
                <th>Criticality</th>
                <th>Appliances</th>
                <th>Protected Assets</th>
                <th>Incidents</th>
              </tr>
            </thead>
            <tbody>
              {data.tenants.map((tenant) => (
                <tr key={tenant.id}>
                  <td>{tenant.name}</td>
                  <td>{tenant.short_code}</td>
                  <td>
                    <span className={`badge badge-${tenant.status}`}>{tenant.status}</span>
                  </td>
                  <td>{tenant.sla_level}</td>
                  <td>{tenant.business_criticality}</td>
                  <td>{tenant.appliances}</td>
                  <td>{tenant.protected_assets}</td>
                  <td>{tenant.incidents}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
