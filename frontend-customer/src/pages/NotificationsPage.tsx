import { useSearchParams } from "react-router-dom";
import { getCustomerNotifications } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

const STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "sent", label: "Sent" },
  { value: "delivered", label: "Delivered" },
  { value: "failed", label: "Failed" },
];

export default function NotificationsPage() {
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
      getCustomerNotifications(shortCode as string, {
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
        <h1 className="page-title">Notifications</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so notifications cannot be loaded.
        </div>
      </div>
    );
  }

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
      <p className="page-subtitle">
        Read-only history of security notifications sent for your organization.
      </p>

      <ListToolbar
        searchPlaceholder="Search type or message…"
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
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        notifications.length === 0 ? (
          <div className="state-message">No notifications matching this view.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Message</th>
                <th>Sent</th>
                <th>Delivered</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((row) => (
                <tr key={row.notification_id}>
                  <td>{row.notification_type}</td>
                  <td>{row.status}</td>
                  <td>{row.message_body}</td>
                  <td>{row.sent_at ?? "—"}</td>
                  <td>{row.delivered_at ?? "—"}</td>
                  <td>{row.created_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
