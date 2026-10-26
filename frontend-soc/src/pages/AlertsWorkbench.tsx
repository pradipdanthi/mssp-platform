import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertRow, getAlerts } from "../api/soc";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Severity from "../components/Severity";

export default function AlertsWorkbench() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const tenantFilter = params.get("tenant") || "";
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getAlerts({
      page_size: 100,
      q: q.trim() || undefined,
      status: status || undefined,
      severity: severity || undefined,
      tenant_id: tenantFilter || undefined,
    })
      .then((r) => {
        setRows(r.alerts || []);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load alerts");
      })
      .finally(() => setLoading(false));
  }, [logout, q, status, severity, tenantFilter]);

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <h2>Security Alerts</h2>
          <p className="muted">Triage here — no need to leave the SOC console.</p>
        </div>
        <div className="workbench-filters">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search title / host / tenant"
            aria-label="Search alerts"
          />
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">All statuses</option>
            <option value="new">Open</option>
            <option value="triaged">In review</option>
            <option value="incident_created">Incident created</option>
            <option value="false_positive">False positive</option>
            <option value="closed">Closed</option>
          </select>
          <Link className="btn btn-ghost" to="/">
            Back to feed
          </Link>
        </div>
      </div>
      <div className="workbench-b">
        {err && <div className="err">{err}</div>}
        {loading ? (
          <div className="empty">Loading alerts…</div>
        ) : rows.length === 0 ? (
          <div className="empty">No alerts match.</div>
        ) : (
          <table className="wb-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Title</th>
                <th>Customer</th>
                <th>Host</th>
                <th>AI</th>
                <th>Status</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} onClick={() => navigate(`/alerts/${a.id}`)}>
                  <td>
                    <Severity value={a.severity} />
                  </td>
                  <td>{a.alert_title || a.title}</td>
                  <td>{a.short_code || a.tenant_name || "—"}</td>
                  <td>{a.destination_host || "—"}</td>
                  <td>{a.ai_verdict || "—"}</td>
                  <td>{a.status}</td>
                  <td>{a.event_time ? new Date(a.event_time).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
