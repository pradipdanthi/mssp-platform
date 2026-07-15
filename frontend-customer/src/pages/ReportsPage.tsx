import { getCustomerDashboard } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function ReportsPage() {
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
      <p className="page-subtitle">Read-only monthly reports from your customer dashboard.</p>

      {status === "loading" && <div className="state-message">Loading reports...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.monthly_reports.length === 0 ? (
          <div className="state-message">No monthly reports yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Month</th>
                <th>Status</th>
                <th>Published</th>
                <th>Executive Summary</th>
              </tr>
            </thead>
            <tbody>
              {data.monthly_reports.map((report) => (
                <tr key={String(report.report_month)}>
                  <td>{String(report.report_month)}</td>
                  <td>{report.status}</td>
                  <td>{report.published_at ?? "—"}</td>
                  <td>{report.executive_summary ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
