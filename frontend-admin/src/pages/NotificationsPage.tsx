import { getNotifications } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function NotificationsPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getNotifications(), []);

  return (
    <div>
      <h1 className="page-title">Notifications</h1>
      <p className="page-subtitle">
        Notification delivery history across tenants (latest 100). Preview only — no raw recipient secrets.
      </p>

      {status === "loading" && <div className="state-message">Loading notifications...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view notifications.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.notifications.length === 0 ? (
          <div className="state-message">No notifications yet.</div>
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
              {data.notifications.map((row) => (
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
