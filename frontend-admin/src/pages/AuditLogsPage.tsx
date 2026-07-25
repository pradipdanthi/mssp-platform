import { getAuditLogs } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

export default function AuditLogsPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getAuditLogs(), []);

  return (
    <div>
      <h1 className="page-title">Audit Log</h1>
      <p className="page-subtitle">
        Recent platform actions (latest 100). Read-only compliance visibility for SOC/admin.
      </p>

      {status === "loading" && <div className="state-message">Loading audit log...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.audit_logs.length === 0 ? (
          <div className="state-message">
            No audit events recorded yet. Events appear as platform actions are written to
            audit_logs.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Customer</th>
                <th>Source IP</th>
              </tr>
            </thead>
            <tbody>
              {data.audit_logs.map((row) => (
                <tr key={row.id}>
                  <td>{row.created_at}</td>
                  <td>{row.actor_email ?? "—"}</td>
                  <td>{row.action}</td>
                  <td>
                    {row.entity_type}
                    {row.entity_id ? ` / ${row.entity_id.slice(0, 8)}…` : ""}
                  </td>
                  <td>
                    {row.tenant_name
                      ? `${row.tenant_name}${row.short_code ? ` (${row.short_code})` : ""}`
                      : "—"}
                  </td>
                  <td>{row.source_ip ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
