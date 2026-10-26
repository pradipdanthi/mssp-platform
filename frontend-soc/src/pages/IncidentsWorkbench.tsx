import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getIncidents, IncidentRow } from "../api/soc";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Severity from "../components/Severity";

export default function IncidentsWorkbench() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [rows, setRows] = useState<IncidentRow[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getIncidents({
      page_size: 100,
      q: q.trim() || undefined,
      status: status || undefined,
    })
      .then((r) => {
        setRows(r.incidents || []);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load incidents");
      })
      .finally(() => setLoading(false));
  }, [logout, q, status]);

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <h2>Incidents</h2>
          <p className="muted">Open, update, and comment without leaving this console.</p>
        </div>
        <div className="workbench-filters">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search number / title / tenant"
            aria-label="Search incidents"
          />
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="waiting_customer">Waiting customer</option>
            <option value="resolved">Resolved</option>
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
          <div className="empty">Loading incidents…</div>
        ) : rows.length === 0 ? (
          <div className="empty">No incidents match.</div>
        ) : (
          <table className="wb-table">
            <thead>
              <tr>
                <th>Number</th>
                <th>Severity</th>
                <th>Title</th>
                <th>Customer</th>
                <th>Status</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id} onClick={() => navigate(`/incidents/${i.id}`)}>
                  <td>{i.incident_number}</td>
                  <td>
                    <Severity value={i.severity} />
                  </td>
                  <td>{i.title}</td>
                  <td>{i.short_code || i.tenant_name || "—"}</td>
                  <td>{i.status}</td>
                  <td>{i.opened_at ? new Date(i.opened_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
