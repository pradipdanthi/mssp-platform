import { Link, useParams } from "react-router-dom";
import { getCustomerReportDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function ReportDetailPage() {
  const { user } = useAuth();
  const { reportId } = useParams<{ reportId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerReportDetail(shortCode as string, reportId as string),
    Boolean(shortCode && reportId),
    [shortCode, reportId]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Report</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so report detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!reportId) {
    return (
      <div>
        <h1 className="page-title">Report</h1>
        <div className="state-message state-error">Report id is missing from the URL.</div>
        <p>
          <Link to="/reports">Back to reports</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <p>
        <Link to="/reports">← Back to reports</Link>
      </p>
      <h1 className="page-title">Report</h1>
      <p className="page-subtitle">Read-only published monthly security report detail.</p>

      {status === "loading" && <div className="state-message">Loading report...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Report was not found."}</div>
      )}

      {status === "success" && data && (
        <table className="data-table">
          <tbody>
            <tr>
              <th>Title</th>
              <td>{data.report.title}</td>
            </tr>
            <tr>
              <th>Month</th>
              <td>{String(data.report.report_month)}</td>
            </tr>
            <tr>
              <th>Status</th>
              <td>{data.report.status}</td>
            </tr>
            <tr>
              <th>Summary</th>
              <td>{data.report.summary ?? "—"}</td>
            </tr>
            <tr>
              <th>Published</th>
              <td>{data.report.published_at ?? "—"}</td>
            </tr>
            <tr>
              <th>Created</th>
              <td>{data.report.created_at ?? "—"}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}
