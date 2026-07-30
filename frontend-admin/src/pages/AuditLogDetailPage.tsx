import { Link, useParams } from "react-router-dom";
import { getAuditLogDetail } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

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
  const { status, data, errorMessage } = useAdminQuery(
    () => getAuditLogDetail(auditId as string),
    [auditId]
  );

  if (!auditId) {
    return <div className="state-message state-error">Audit event id missing.</div>;
  }

  const row = data?.audit_log;
  const details = row?.details && typeof row.details === "object" ? row.details : {};

  return (
    <div>
      <p>
        <Link to="/audit">← Back to audit log</Link>
      </p>
      <h1 className="page-title">Audit event</h1>
      <p className="page-subtitle">
        Full accountability record — who performed the action, from which portal, against which
        customer/endpoint, and when.
      </p>

      {status === "loading" && <div className="state-message">Loading…</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && row ? (
        <>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Summary</th>
                <td>{row.summary || row.action_label || row.action}</td>
              </tr>
              <tr>
                <th>When (UTC)</th>
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
                <th>Action code</th>
                <td className="cell-mono">{row.action}</td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{row.action_status || "SUCCESS"}</td>
              </tr>
              <tr>
                <th>Customer / tenant</th>
                <td>
                  {row.tenant_name
                    ? `${row.tenant_name}${row.short_code ? ` (${row.short_code})` : ""}`
                    : "—"}
                </td>
              </tr>
              <tr>
                <th>Portal</th>
                <td>
                  {row.portal === "customer_portal"
                    ? "Customer portal"
                    : row.portal === "mssp_admin_portal"
                      ? "MSSP admin / SOC portal"
                      : row.portal || "—"}
                </td>
              </tr>
              <tr>
                <th>Source IP</th>
                <td className="cell-mono">{row.source_ip ?? "—"}</td>
              </tr>
              <tr>
                <th>Entity</th>
                <td className="cell-mono">
                  {row.entity_type}
                  {row.entity_id ? ` / ${row.entity_id}` : ""}
                </td>
              </tr>
            </tbody>
          </table>

          <h2 className="section-title">Event details</h2>
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
