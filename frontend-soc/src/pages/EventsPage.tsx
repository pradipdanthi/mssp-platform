import { useEffect, useState } from "react";
import { EdgeEvent, getEdgeEvents } from "../api/soc";
import Severity from "../components/Severity";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function EventsPage() {
  const { logout } = useAuth();
  const [rows, setRows] = useState<EdgeEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getEdgeEvents()
      .then((r) => setRows(r.events || []))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load Secure Edge events");
      });
  }, [logout]);

  return (
    <div className="panel">
      <div className="panel-h">
        <h2>Security events</h2>
        <span className="muted">Secure Edge + WAF / bot / edge telemetry</span>
      </div>
      <div className="panel-b">
        {err && <div className="err" style={{ padding: "0.75rem 1.1rem" }}>{err}</div>}
        {rows.length === 0 && !err ? <div className="empty">No edge events yet.</div> : (
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Type</th>
                <th>Summary</th>
                <th>Hostname</th>
                <th>Tenant</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={String(e.id)}>
                  <td><Severity value={e.severity} /></td>
                  <td>{e.event_type}</td>
                  <td>{e.summary}</td>
                  <td>{e.public_hostname || e.edge_hostname || "—"}</td>
                  <td>{e.tenant_short_code || "—"}</td>
                  <td>{e.created_at ? new Date(e.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
