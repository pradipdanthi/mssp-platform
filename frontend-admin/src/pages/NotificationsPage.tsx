import { useSearchParams } from "react-router-dom";
import { getNotifications } from "../api/admin";
import ListToolbar from "../components/ListToolbar";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useCustomerScope } from "../hooks/useCustomerScope";

const STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "sent", label: "Sent" },
  { value: "delivered", label: "Delivered" },
  { value: "failed", label: "Failed" },
];

export default function NotificationsPage() {
  const { tenantFilter } = useCustomerScope();
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

  const { status, data, errorMessage } = useAdminQuery(
    () =>
      getNotifications({
        page,
        page_size: pageSize,
        ...tenantFilter,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    [tenantFilter, statusFilter, qFilter, page, pageSize]
  );

  const notifications = status === "success" && data ? data.notifications : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? notifications.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  return (
    <div>
      <h1 className="page-title">Notifications</h1>
      <CustomerScopeBanner />
      <p className="page-subtitle">
        Notification delivery history across tenants. Preview only — no raw recipient secrets.
        Search and paginate when the history grows large.
      </p>

      <ListToolbar
        searchPlaceholder="Search type, preview, tenant…"
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

      {status === "loading" && <div className="state-message">Loading notifications...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view notifications.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        notifications.length === 0 ? (
          <div className="state-message">No notifications matching this view.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Type</th>
                <th>Status</th>
                <th>Provider</th>
                <th>Preview</th>
                <th>Sent</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((row) => (
                <tr key={row.id}>
                  <td>{row.tenant_name}</td>
                  <td>{row.notification_type}</td>
                  <td>
                    <span className={`badge badge-${row.status}`}>{row.status}</span>
                  </td>
                  <td>{row.provider ?? "—"}</td>
                  <td>{row.message_preview}</td>
                  <td>{row.sent_at ?? "—"}</td>
                  <td>{row.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
