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
  resource_type?: string | null;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
}

const DETAIL_LABELS: Record<string, string> = {
  summary: "Summary",
  portal: "Portal",
  incident_number: "Incident",
  action: "Action",
  reason: "Reason",
  target: "Target",
  hostname: "Hostname",
  result: "Result",
};

function errMsg(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  return fallback;
}

function portalLabel(portal: string | null | undefined): string {
  if (portal === "customer_portal") return "Customer portal";
  if (portal === "mssp_admin_portal") return "MSSP admin / SOC";
  return portal || "—";
}

function friendlyDetailEntries(details: Record<string, unknown>): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(details)) {
    if (key === "source_ip" || key === "raw_event" || key === "raw_json") continue;
    if (value == null) continue;
    if (typeof value === "object") continue;
    const label = DETAIL_LABELS[key] || key.replace(/_/g, " ");
    out.push([label, String(value)]);
  }
  return out;
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
  const detailRows = friendlyDetailEntries(details);

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
                <th>What happened</th>
                <td>{row.summary || row.action_label || row.action}</td>
              </tr>
              <tr>
                <th>When</th>
                <td className="cell-mono">{row.timestamp || row.created_at}</td>
              </tr>
              <tr>
                <th>Who</th>
                <td>
                  {row.actor_email ?? "—"}
                  {row.actor_role ? ` · ${row.actor_role}` : ""}
                </td>
              </tr>
              <tr>
                <th>Action</th>
                <td>{row.action_label || row.action}</td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{row.action_status || "SUCCESS"}</td>
              </tr>
              <tr>
                <th>Where</th>
                <td>{portalLabel(row.portal)}</td>
              </tr>
            </tbody>
          </table>
          <h2 className="section-title">Additional context</h2>
          <table className="data-table">
            <tbody>
              {detailRows.length === 0 ? (
                <tr>
                  <td className="muted">No extra customer-visible detail for this event.</td>
                </tr>
              ) : (
                detailRows.map(([label, value]) => (
                  <tr key={label}>
                    <th>{label}</th>
                    <td>{value}</td>
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
