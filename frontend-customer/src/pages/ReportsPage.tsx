import { Link } from "react-router-dom";
import { getCustomerReports } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function ReportsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerReports(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Reports</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so reports cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Reports</h1>
      <p className="page-subtitle">
        Read-only published monthly security reports for your organization.
      </p>

      {status === "loading" && <div className="state-message">Loading reports...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.reports.length === 0 ? (
          <div className="state-message">
            No published monthly reports yet. Drafts prepared by your SOC team are not shown here
            until they are published.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Month</th>
                <th>Status</th>
                <th>Summary</th>
                <th>Published</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.reports.map((report) => (
                <tr key={report.report_id}>
                  <td>
                    <Link to={`/reports/${encodeURIComponent(report.report_id)}`}>{report.title}</Link>
                  </td>
                  <td>{String(report.report_month)}</td>
                  <td>{report.status}</td>
                  <td>{report.summary ?? "—"}</td>
                  <td>{report.published_at ?? "—"}</td>
                  <td>{report.created_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
