import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError, request } from "../api/client";

interface AuditRow {
  id: string;
  timestamp?: string;
  created_at?: string;
  actor_email?: string | null;
  actor_role?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  action_status?: string;
  source_ip?: string | null;
}

function errMsg(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  return fallback;
}

export default function AuditLogsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code || "";
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shortCode) return;
    request<{ audit_logs: AuditRow[] }>(
      `/customer/audit-logs/${encodeURIComponent(shortCode)}`
    )
      .then((res) => setRows(res.audit_logs || []))
      .catch((e) => setError(errMsg(e, "Could not load audit log")));
  }, [shortCode]);

  return (
    <div>
      <h1 className="page-title">Audit log</h1>
      <p className="page-subtitle">Actions performed in your organization (tenant-scoped).</p>
      {error ? <p className="form-error">{error}</p> : null}
      <div className="card-surface">
        <table className="data-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="cell-mono">{r.timestamp || r.created_at || "—"}</td>
                <td>
                  {r.actor_email || "—"}
                  {r.actor_role ? <span className="muted"> · {r.actor_role}</span> : null}
                </td>
                <td>{r.action}</td>
                <td className="cell-mono">
                  {r.resource_type || "—"}
                  {r.resource_id ? ` / ${r.resource_id}` : ""}
                </td>
                <td>{r.action_status || "SUCCESS"}</td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  No audit events yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
