import { Link, useParams } from "react-router-dom";
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
  action_label?: string | null;
  summary?: string | null;
  portal?: string | null;
  action_status?: string;
  source_ip?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
}

function errMsg(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  return fallback;
}

function detailValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

export default function AuditLogDetailPage() {
  const { auditId } = useParams<{ auditId: string }>();
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code || "";
  const [row, setRow] = useState<AuditRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shortCode || !auditId) return;
    request<{ audit_log: AuditRow }>(
      `/customer/audit-logs/${encodeURIComponent(shortCode)}/${encodeURIComponent(auditId)}`
    )
      .then((res) => setRow(res.audit_log))
      .catch((e) => setError(errMsg(e, "Could not load audit event")));
  }, [shortCode, auditId]);

  const details = row?.details && typeof row.details === "object" ? row.details : {};

  return (
    <div>
      <p>
        <Link to="/audit">← Back to audit log</Link>
      </p>
      <h1 className="page-title">Audit event</h1>
      <p className="page-subtitle">Who did what in your organization, and when.</p>
      {error ? <p className="form-error">{error}</p> : null}
      {!error && !row ? <div className="state-message">Loading…</div> : null}
      {row ? (
        <>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Summary</th>
                <td>{row.summary || row.action_label || row.action}</td>
              </tr>
              <tr>
                <th>When</th>
                <td className="cell-mono">{row.timestamp || row.created_at}</td>
              </tr>
              <tr>
                <th>Actor</th>
                <td>
                  {row.actor_email ?? "—"}
                  {row.actor_role ? ` · ${row.actor_role}` : ""}
                </td>
              </tr>
              <tr>
                <th>Action</th>
                <td className="cell-mono">{row.action}</td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{row.action_status || "SUCCESS"}</td>
              </tr>
              <tr>
                <th>Portal</th>
                <td>
                  {row.portal === "customer_portal"
                    ? "Customer portal"
                    : row.portal === "mssp_admin_portal"
                      ? "MSSP admin / SOC"
                      : row.portal || "—"}
                </td>
              </tr>
              <tr>
                <th>Source IP</th>
                <td className="cell-mono">{row.source_ip ?? "—"}</td>
              </tr>
            </tbody>
          </table>
          <h2 className="section-title">Details</h2>
          <table className="data-table">
            <tbody>
              {Object.keys(details).length === 0 ? (
                <tr>
                  <td className="muted">No extra detail fields.</td>
                </tr>
              ) : (
                Object.entries(details).map(([key, value]) => (
                  <tr key={key}>
                    <th>{key}</th>
                    <td>
                      <pre className="cell-mono" style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                        {detailValue(value)}
                      </pre>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </>
      ) : null}
    </div>
  );
}
