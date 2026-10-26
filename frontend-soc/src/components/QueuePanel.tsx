import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { AlertRow, getQueue, IncidentRow } from "../api/soc";
import { useAuth } from "../auth/AuthContext";
import { useOps } from "../state/OpsContext";
import Severity from "./Severity";

export default function QueuePanel() {
  const { logout } = useAuth();
  const { query, setQuery, tab, setTab, selectedAlertId, selectAlert, selectAlertId } = useOps();
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [incidents, setIncidents] = useState<IncidentRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    // No severity/status filters — full live queue of recent work
    getQueue({ q: query || undefined })
      .then((r) => {
        if (cancelled) return;
        setAlerts(r.alerts || []);
        setIncidents(r.incidents || []);
        setErr(null);
        if (selectedAlertId) {
          const found = (r.alerts || []).find((a) => a.id === selectedAlertId) || null;
          if (found) selectAlert(found);
        }
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else if (!cancelled) setErr("Failed to load queue");
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    const t = window.setInterval(() => {
      getQueue({ q: query || undefined })
        .then((r) => {
          setAlerts(r.alerts || []);
          setIncidents(r.incidents || []);
        })
        .catch(() => undefined);
    }, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [query, logout, selectedAlertId, selectAlert]);

  return (
    <section className="ops-queue">
      <div className="queue-toolbar">
        <div className="queue-tabs">
          <button
            type="button"
            className={`btn ${tab === "alerts" ? "active" : "btn-ghost"}`}
            onClick={() => setTab("alerts")}
          >
            Alerts ({alerts.length})
          </button>
          <button
            type="button"
            className={`btn ${tab === "incidents" ? "active" : "btn-ghost"}`}
            onClick={() => setTab("incidents")}
          >
            Incidents ({incidents.length})
          </button>
        </div>
        <input
          className="queue-search"
          placeholder="Search host, title, tenant…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="muted">{busy ? "Refreshing…" : "Live queue"}</span>
      </div>
      {err && <div className="err" style={{ padding: "0.5rem 0.75rem" }}>{err}</div>}
      <div className="queue-list">
        {tab === "alerts" &&
          (alerts.length === 0 ? (
            <div className="empty">No recent alerts.</div>
          ) : (
            alerts.map((a) => (
              <div
                key={a.id}
                className={`q-row ${selectedAlertId === a.id ? "selected" : ""}`}
                onClick={() => selectAlert(a)}
              >
                <Severity value={a.severity} />
                <div>
                  <div className="q-title">{a.alert_title || a.title}</div>
                  <div className="q-sub">
                    {a.short_code || "—"} · {a.source_tool || "—"} · host {a.destination_host || "—"}
                    {a.ai_verdict ? ` · AI ${a.ai_verdict}` : ""}
                  </div>
                </div>
                <div className="q-sub">{a.status}</div>
                <div className="q-actions" onClick={(e) => e.stopPropagation()}>
                  <button type="button" className="btn btn-blue" onClick={() => selectAlert(a)}>
                    Focus
                  </button>
                </div>
              </div>
            ))
          ))}
        {tab === "incidents" &&
          (incidents.length === 0 ? (
            <div className="empty">No open incidents.</div>
          ) : (
            incidents.map((i) => (
              <div key={i.id} className="q-row" onClick={() => selectAlertId(null)}>
                <Severity value={i.severity} />
                <div>
                  <div className="q-title">
                    {i.incident_number}: {i.title}
                  </div>
                  <div className="q-sub">{i.short_code || i.tenant_name || "—"}</div>
                </div>
                <div className="q-sub">{i.status}</div>
                <div />
              </div>
            ))
          ))}
      </div>
    </section>
  );
}
