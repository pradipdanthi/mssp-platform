import { useEffect, useState } from "react";
import { AlertRow, getAlerts } from "../api/soc";
import Severity from "../components/Severity";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function AlertsPage() {
  const { logout } = useAuth();
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getAlerts()
      .then((r) => setRows(r.alerts || []))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load alerts");
      });
  }, [logout]);

  return (
    <div className="panel">
      <div className="panel-h"><h2>Security alerts</h2><span className="muted">{rows.length} shown</span></div>
      <div className="panel-b">
        {err && <div className="err" style={{ padding: "0.75rem 1.1rem" }}>{err}</div>}
        {rows.length === 0 && !err ? <div className="empty">No alerts.</div> : (
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Title</th>
                <th>Host</th>
                <th>AI verdict</th>
                <th>Status</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td><Severity value={a.severity} /></td>
                  <td>{a.alert_title || a.title}</td>
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
