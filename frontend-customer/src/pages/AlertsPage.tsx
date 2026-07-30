import { Link, useSearchParams } from "react-router-dom";
import { getCustomerAlerts } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import SeverityPill from "../components/SeverityPill";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

const SEVERITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "urgent", label: "High + Critical" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "triaged", label: "Triaged" },
  { value: "incident_created", label: "Incident created" },
  { value: "false_positive", label: "False positive" },
  { value: "closed", label: "Closed" },
];

export default function AlertsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [params, setParams] = useSearchParams();
  const severityFilter = params.get("severity") ?? "";
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
      getCustomerAlerts(shortCode as string, {
        page,
        page_size: pageSize,
        ...(qFilter ? { q: qFilter } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
      }),
    Boolean(shortCode),
    [shortCode, severityFilter, statusFilter, qFilter, page, pageSize]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Alerts</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so alert data cannot be loaded.
        </div>
      </div>
    );
  }

  const alerts = status === "success" && data ? data.alerts : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? alerts.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-subtitle">
        Read-only customer-visible alerts for your organization. Internal SOC-only alerts are not
        shown here. Use search and filters when the list grows.
      </p>

      <ListToolbar
        searchPlaceholder="Search title, host, or summary…"
        searchValue={qFilter}
        onSearchChange={(q) => patchParams({ q, page: "1" })}
        statusOptions={STATUS_OPTIONS}
        statusValue={statusFilter}
        onStatusChange={(status) => patchParams({ status, page: "1" })}
        severityOptions={SEVERITY_OPTIONS}
        severityValue={severityFilter}
        onSeverityChange={(severity) => patchParams({ severity, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {status === "loading" && <div className="state-message">Loading alerts...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        alerts.length === 0 ? (
          <div className="state-message">No customer-visible alerts in this view.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Detection</th>
                <th>Device</th>
                <th>Category</th>
                <th>Summary</th>
                <th>Hostname</th>
                <th>Detected</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.alert_id}>
                  <td>
                    <Link to={`/alerts/${encodeURIComponent(alert.alert_id)}`}>{alert.title}</Link>
                  </td>
                  <td>
                    <SeverityPill value={alert.severity} filterBase="/alerts" />
                  </td>
                  <td>
                    <SeverityPill value={alert.status} kind="status" filterBase="/alerts" />
                  </td>
                  <td className="cell-mono">{alert.source}</td>
                  <td>{alert.device_type ?? "—"}</td>
                  <td>{alert.asset_category_label ?? alert.asset_category ?? "—"}</td>
                  <td>{alert.summary ?? alert.description ?? "—"}</td>
                  <td className="cell-mono">{alert.hostname ?? "—"}</td>
                  <td className="cell-mono">{alert.detected_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
