import { getCustomerIncidents } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function IncidentsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerIncidents(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Incidents</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so incident data cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">Read-only customer-visible incidents for your organization.</p>

      {status === "loading" && <div className="state-message">Loading incidents...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.incidents.length === 0 ? (
          <div className="state-message">No incidents yet.</div>
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
              {data.incidents.map((inc) => (
                <tr key={inc.incident_number}>
                  <td>{inc.incident_number}</td>
                  <td>{inc.title}</td>
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
        )
      )}
    </div>
  );
}
