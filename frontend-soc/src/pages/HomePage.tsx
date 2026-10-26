import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getOverview, AlertRow } from "../api/soc";
import Severity from "../components/Severity";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function HomePage() {
  const { logout } = useAuth();
  const [kpis, setKpis] = useState<Record<string, number>>({});
  const [recent, setRecent] = useState<AlertRow[]>([]);
  const [chatOn, setChatOn] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getOverview()
      .then((r) => {
        setKpis(r.kpis || {});
        setRecent(r.recent_alerts || []);
        setChatOn(Boolean(r.chat_enabled));
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Could not load overview");
      });
  }, [logout]);

  return (
    <>
      <div className="kpis">
        <div className="kpi"><div className="n">{kpis.open_alerts_24h ?? "—"}</div><div className="l">Alerts 24h</div></div>
        <div className="kpi"><div className="n">{kpis.high_open ?? "—"}</div><div className="l">High / Critical open</div></div>
        <div className="kpi"><div className="n">{kpis.open_incidents ?? "—"}</div><div className="l">Open incidents</div></div>
        <div className="kpi"><div className="n">{kpis.edge_events_24h ?? "—"}</div><div className="l">Edge events 24h</div></div>
      </div>
      {err && <div className="err">{err}</div>}
      <div className="panel">
        <div className="panel-h">
          <h2>Latest alerts</h2>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Link className="btn btn-ghost" to="/alerts">All alerts</Link>
            <Link className="btn btn-primary" to="/chat">{chatOn ? "Open Cursor chat" : "Chat (configure agent)"}</Link>
          </div>
        </div>
        <div className="panel-b">
          {recent.length === 0 ? (
            <div className="empty">No recent alerts.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Title</th>
                  <th>AI</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((a) => (
                  <tr key={a.id}>
                    <td><Severity value={a.severity} /></td>
                    <td>{a.alert_title || a.title}</td>
                    <td>{a.ai_verdict ? `${a.ai_verdict}${a.ai_confidence != null ? ` (${Math.round(Number(a.ai_confidence))}%)` : ""}` : "—"}</td>
                    <td>{a.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}
