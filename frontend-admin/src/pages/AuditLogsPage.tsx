import { useMemo, useState } from "react";
import { AuditLog, getAuditLogs } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

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

function toCsv(rows: AuditLog[]): string {
  const header = [
    "created_at",
    "actor_email",
    "action",
    "entity_type",
    "entity_id",
    "tenant_name",
    "short_code",
    "source_ip",
    "details_json",
  ];
  const escape = (v: unknown) => {
    const s = v == null ? "" : String(v);
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push(
      [
        r.created_at,
        r.actor_email,
        r.action,
        r.entity_type,
        r.entity_id,
        r.tenant_name,
        r.short_code,
        r.source_ip,
        r.details ? JSON.stringify(r.details) : "",
      ]
        .map(escape)
        .join(",")
    );
  }
  return lines.join("\n");
}

export default function AuditLogsPage() {
  const { status, data, errorMessage } = useAdminQuery(() => getAuditLogs(), []);
  const [actorFilter, setActorFilter] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const rows = useMemo(() => {
    const all = data?.audit_logs ?? [];
    if (!actorFilter) return all;
    return all.filter((r) => (r.actor_email ?? "").toLowerCase() === actorFilter.toLowerCase());
  }, [data, actorFilter]);

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Audit Log</h1>
          <p className="page-subtitle">
            Connected platform actions with actor / entity drill-down (latest 200). Click an actor
            to filter; click an entity to view before/after details.
          </p>
        </div>
        <div className="ops-grid-actions">
          <button
            type="button"
            className="btn btn-ghost"
            disabled={rows.length === 0}
            onClick={() =>
              downloadBlob(
                `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`,
                toCsv(rows),
                "text/csv;charset=utf-8"
              )
            }
          >
            Export CSV
          </button>
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
            Export JSON
          </button>
        </div>
      </div>

      {actorFilter && (
        <div className="filter-bar" style={{ marginBottom: "12px" }}>
          <span className="filter-chip">Actor: {actorFilter}</span>
          <button type="button" className="linkish" onClick={() => setActorFilter(null)}>
            Clear actor filter
          </button>
        </div>
      )}

      {status === "loading" && <div className="state-message">Loading audit log...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        rows.length === 0 ? (
          <div className="state-message">
            {actorFilter
              ? "No events for this actor in the current window."
              : "No audit events recorded yet. Events appear as platform actions are written to audit_logs."}
          </div>
        ) : (
          <table className="data-table data-table--readable">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Customer</th>
                <th>Source IP</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="cell-mono">{row.created_at}</td>
                  <td>
                    {row.actor_email ? (
                      <button
                        type="button"
                        className="linkish"
                        onClick={() => setActorFilter(row.actor_email)}
                        title="Filter by this actor"
                      >
                        {row.actor_email}
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{row.action}</td>
                  <td>
                    <button
                      type="button"
                      className="linkish cell-mono"
                      onClick={() => setSelected(row)}
                      title="Open change details"
                    >
                      {row.entity_type}
                      {row.entity_id ? ` / ${row.entity_id.slice(0, 8)}…` : ""}
                    </button>
                  </td>
                  <td>
                    {row.tenant_name
                      ? `${row.tenant_name}${row.short_code ? ` (${row.short_code})` : ""}`
                      : "—"}
                  </td>
                  <td className="cell-mono">{row.source_ip ?? "—"}</td>
                  <td>
                    <span className="badge badge-active">ok</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {selected && (
        <div className="modal-root" role="dialog" aria-modal="true" aria-label="Audit event detail">
          <button
            type="button"
            className="modal-backdrop"
            aria-label="Close"
            onClick={() => setSelected(null)}
          />
          <div className="modal-card card-surface">
            <h2 className="modal-title">Change details</h2>
            <p className="modal-body">
              <span className="cell-mono">{selected.action}</span> on{" "}
              <span className="cell-mono">
                {selected.entity_type}
                {selected.entity_id ? `:${selected.entity_id}` : ""}
              </span>
            </p>
            <pre className="audit-diff-json">
              {JSON.stringify(selected.details ?? { note: "No before/after payload stored" }, null, 2)}
            </pre>
            <div className="modal-actions">
              <button type="button" className="btn btn-primary" onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
