import { Link, useSearchParams } from "react-router-dom";
import { getCustomerReports } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

const STATUS_OPTIONS = [
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
];

export default function ReportsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status") ?? "";
  const qFilter = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;

  function patchParams(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  const { status, data, errorMessage } = useCustomerQuery(
    () =>
      getCustomerReports(shortCode as string, {
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    Boolean(shortCode),
    [shortCode, statusFilter, qFilter, page, pageSize]
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

  const reports = status === "success" && data ? data.reports : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? reports.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  return (
    <div>
      <h1 className="page-title">Reports</h1>
      <p className="page-subtitle">
        Read-only published monthly security reports for your organization.
      </p>

      <ListToolbar
        searchPlaceholder="Search title, month, or summary…"
        searchValue={qFilter}
        onSearchChange={(q) => patchParams({ q, page: "1" })}
        statusOptions={STATUS_OPTIONS}
        statusValue={statusFilter}
        onStatusChange={(status) => patchParams({ status, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {status === "loading" && <div className="state-message">Loading reports...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        reports.length === 0 ? (
          <div className="state-message">No published monthly reports matching this view.</div>
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
              {reports.map((report) => (
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
