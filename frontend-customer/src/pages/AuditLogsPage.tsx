import { useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError, request } from "../api/client";
import ListToolbar from "../components/ListToolbar";

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
  resource_type?: string | null;
  resource_id?: string | null;
  action_status?: string;
  source_ip?: string | null;
  details?: Record<string, unknown> | null;
}

interface AuditListResponse {
  audit_logs: AuditRow[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_next?: boolean;
  has_prev?: boolean;
}

function errMsg(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  return fallback;
}

export default function AuditLogsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const shortCode = user?.tenant_short_code || "";
  const [params, setParams] = useSearchParams();
  const qFilter = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;
  const [data, setData] = useState<AuditListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function patchParams(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  useEffect(() => {
    if (!shortCode) return;
    setLoading(true);
    const q = new URLSearchParams();
    q.set("page", String(page));
    q.set("page_size", String(pageSize));
    if (qFilter) q.set("q", qFilter);
    request<AuditListResponse>(
      `/customer/audit-logs/${encodeURIComponent(shortCode)}?${q.toString()}`
    )
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((e) => setError(errMsg(e, "Could not load audit log")))
      .finally(() => setLoading(false));
  }, [shortCode, qFilter, page, pageSize]);

  const rows = data?.audit_logs || [];
  const meta = data
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
      <h1 className="page-title">Audit log</h1>
      <p className="page-subtitle">
        Actions in your organization — including who isolated or released an endpoint. Open a row
        for full detail.
      </p>
      {error ? <p className="form-error">{error}</p> : null}

      <ListToolbar
        searchPlaceholder="Search actor, action, incident…"
        searchValue={qFilter}
        onSearchChange={(value) => patchParams({ q: value || null, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {loading ? <div className="state-message">Loading…</div> : null}

      {!loading ? (
        <div className="card-surface">
          <table className="data-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Status</th>
                <th></th>
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
                  <td>
                    <div>{r.summary || r.action_label || r.action}</div>
                    <div className="muted cell-mono" style={{ fontSize: "0.85em" }}>
                      {r.action}
                    </div>
                  </td>
                  <td>{r.action_status || "SUCCESS"}</td>
                  <td>
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => navigate(`/audit/${r.id}`)}
                    >
                      Open
                    </button>
                  </td>
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
      ) : null}
    </div>
  );
}
