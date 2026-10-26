import { useEffect, useState } from "react";
import { getIncidents, IncidentRow } from "../api/soc";
import Severity from "../components/Severity";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function IncidentsPage() {
  const { logout } = useAuth();
  const [rows, setRows] = useState<IncidentRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getIncidents()
      .then((r) => setRows(r.incidents || []))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load incidents");
      });
  }, [logout]);

  return (
    <div className="panel">
      <div className="panel-h"><h2>Incidents</h2><span className="muted">{rows.length} shown</span></div>
      <div className="panel-b">
        {err && <div className="err" style={{ padding: "0.75rem 1.1rem" }}>{err}</div>}
        {rows.length === 0 && !err ? <div className="empty">No incidents.</div> : (
          <table>
            <thead>
              <tr>
                <th>Number</th>
                <th>Severity</th>
                <th>Title</th>
                <th>Status</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id}>
                  <td>{i.incident_number}</td>
                  <td><Severity value={i.severity} /></td>
                  <td>{i.title}</td>
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
