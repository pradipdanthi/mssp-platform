import { getCustomerNotifications } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function NotificationsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerNotifications(shortCode as string),
    Boolean(shortCode),
    [shortCode]
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

  return (
    <div>
      <h1 className="page-title">Notifications</h1>
      <p className="page-subtitle">
        Read-only history of security notifications sent for your organization.
      </p>

      {status === "loading" && <div className="state-message">Loading notifications...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        data.notifications.length === 0 ? (
          <div className="state-message">
            No notifications yet. When your SOC team sends updates, they will appear here.
          </div>
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
              {data.notifications.map((row) => (
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
