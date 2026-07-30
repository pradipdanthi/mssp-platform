import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getAuditLogs } from "../api/admin";
import ListToolbar from "../components/ListToolbar";
import { useAdminQuery } from "../hooks/useAdminQuery";

const ACTION_OPTIONS = [
  { value: "EDR_ISOLATE_HOST", label: "Isolate / quarantine host" },
  { value: "EDR_UNISOLATE_HOST", label: "Un-isolate / release host" },
  { value: "EDR_KILL_PROCESS", label: "Kill process" },
  { value: "EDR_BLOCK_HASH", label: "Block file hash" },
  { value: "EDR_COLLECT_FORENSICS", label: "Collect forensics" },
  { value: "LOGIN_SUCCESS", label: "Login succeeded" },
  { value: "LOGIN_FAILURE", label: "Login failed" },
  { value: "PASSWORD_CHANGE", label: "Password changed" },
];

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function AuditLogsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const qFilter = params.get("q") ?? "";
  const actionFilter = params.get("action") ?? "";
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
      getAuditLogs({
        page,
        page_size: pageSize,
        ...(qFilter ? { q: qFilter } : {}),
        ...(actionFilter ? { action_type: actionFilter } : {}),
      }),
    [qFilter, actionFilter, page, pageSize]
  );

  const rows = status === "success" && data ? data.audit_logs : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? rows.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Audit Log</h1>
          <p className="page-subtitle">
            Who did what, when, from which portal/IP — including customer isolate actions. Click a row
            for full detail.
          </p>
        </div>
        <div className="ops-grid-actions">
          <button
            type="button"
            className="btn btn-ghost"
            disabled={rows.length === 0}
            onClick={() =>
              downloadBlob(
                `audit-logs-${new Date().toISOString().slice(0, 10)}.json`,
                JSON.stringify(rows, null, 2),
                "application/json"
              )
            }
          >
            Export page JSON
          </button>
        </div>
      </div>

      <ListToolbar
        searchPlaceholder="Search actor, action, tenant, incident, agent, IP…"
        searchValue={qFilter}
        onSearchChange={(value) => patchParams({ q: value || null, page: "1" })}
        statusOptions={ACTION_OPTIONS}
        statusValue={actionFilter}
        onStatusChange={(value) => patchParams({ action: value || null, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {status === "loading" && <div className="state-message">Loading audit log...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        rows.length === 0 ? (
          <div className="state-message">No audit events match this filter.</div>
        ) : (
          <table className="data-table data-table--readable">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Customer</th>
                <th>Source</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="clickable-row"
                  onClick={() => navigate(`/audit/${row.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") navigate(`/audit/${row.id}`);
                  }}
                  tabIndex={0}
                  role="link"
                >
                  <td className="cell-mono">{row.timestamp || row.created_at}</td>
                  <td>
                    {row.actor_email ?? "—"}
                    {row.actor_role ? (
                      <div className="muted" style={{ fontSize: "0.85em" }}>
                        {row.actor_role}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div>{row.summary || row.action_label || row.action}</div>
                    <div className="muted cell-mono" style={{ fontSize: "0.85em" }}>
                      {row.action}
                    </div>
                  </td>
                  <td>
                    {row.tenant_name
                      ? `${row.tenant_name}${row.short_code ? ` (${row.short_code})` : ""}`
                      : "—"}
                  </td>
                  <td>
                    <div>{row.portal === "customer_portal" ? "Customer portal" : row.portal === "mssp_admin_portal" ? "MSSP admin" : "—"}</div>
                    <div className="cell-mono muted" style={{ fontSize: "0.85em" }}>
                      {row.source_ip ?? "—"}
                    </div>
                  </td>
                  <td>
                    <span
                      className={
                        (row.action_status || "SUCCESS") === "FAILED"
                          ? "badge badge-critical"
                          : "badge badge-active"
                      }
                    >
                      {row.action_status || "SUCCESS"}
                    </span>
                  </td>
                  <td>
                    <Link
                      to={`/audit/${row.id}`}
                      className="linkish"
                      onClick={(e) => e.stopPropagation()}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
