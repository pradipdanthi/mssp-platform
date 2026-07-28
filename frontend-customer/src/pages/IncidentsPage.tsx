import { Link, useSearchParams } from "react-router-dom";
import { getCustomerIncidents } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import SeverityPill from "../components/SeverityPill";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

function isOpenStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s === "open" || s === "investigating" || s === "in_progress" || s === "new";
}

export default function IncidentsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [params] = useSearchParams();
  const statusFilter = params.get("status");
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

  const incidents =
    status === "success" && data
      ? data.incidents.filter((i) => {
          if (!statusFilter) return true;
          if (statusFilter === "open") return isOpenStatus(i.status);
          return i.status.toLowerCase() === statusFilter.toLowerCase();
        })
      : [];

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">
        Read-only customer-visible incidents for your organization.
        {statusFilter ? (
          <>
            {" "}
            Filtered by status: <strong>{statusFilter}</strong>
            {" · "}
            <Link to="/incidents">Clear filter</Link>
          </>
        ) : null}
      </p>

      {status === "loading" && <div className="state-message">Loading incidents...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        incidents.length === 0 ? (
          <div className="state-message">
            No incidents{statusFilter ? ` matching “${statusFilter}”` : ""} yet.
          </div>
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
              {incidents.map((inc) => (
                <tr key={inc.incident_number}>
                  <td className="cell-mono">
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
                    <SeverityPill value={inc.severity} />
                  </td>
                  <td>
                    <SeverityPill value={inc.status} kind="status" />
                  </td>
                  <td>{inc.customer_visible_summary ?? "—"}</td>
                  <td className="cell-mono">{inc.opened_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
