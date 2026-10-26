import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAdminDashboard, getTenants, TenantRiskRow } from "../api/soc";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function CustomersWall() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [rows, setRows] = useState<TenantRiskRow[]>([]);
  const [byCode, setByCode] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getAdminDashboard(), getTenants()])
      .then(([dash, ten]) => {
        setRows(dash.tenant_risk_summary || []);
        const map: Record<string, string> = {};
        for (const t of ten.tenants || []) map[t.short_code] = t.id;
        setByCode(map);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load customers");
      });
  }, [logout]);

  function openHere(shortCode: string) {
    navigate(`/monitor/${encodeURIComponent(shortCode)}`);
  }

  function openOnMonitor(shortCode: string) {
    // Absolute URL + localStorage JWT so the new window stays logged in.
    const url = `${window.location.origin}/monitor/${encodeURIComponent(shortCode)}`;
    const win = window.open(url, `soc-monitor-${shortCode}`, "noopener,noreferrer");
    if (!win) {
      setErr("Popup blocked — allow popups for this site, or use Open here.");
    }
  }

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <h2>Customers</h2>
          <p className="muted">
            Each customer opens a <strong>standalone monitor</strong> (alerts, incidents, vulns, patch gaps only — no
            Tia chat / no global live feed). Use <strong>Open on monitor</strong> for a second SOC wall display.
          </p>
        </div>
        <Link className="btn btn-ghost" to="/">
          Back to feed
        </Link>
      </div>
      <div className="workbench-b">
        {err && <div className="err">{err}</div>}
        <div className="customer-grid">
          {rows.map((r) => (
            <article key={r.short_code} className="customer-card">
              <header>
                <h3>{r.name}</h3>
                <span className="muted">{r.short_code}</span>
              </header>
              <div className="customer-stats">
                <div>
                  <strong>{r.high_or_critical_alerts ?? 0}</strong>
                  <span>High/Crit alerts</span>
                </div>
                <div>
                  <strong>{r.open_incidents ?? 0}</strong>
                  <span>Open incidents</span>
                </div>
                <div>
                  <strong>
                    {r.online_appliances ?? 0}/{r.appliances ?? 0}
                  </strong>
                  <span>Appliances up</span>
                </div>
              </div>
              <div className="customer-actions">
                <button type="button" className="btn btn-primary" onClick={() => openHere(r.short_code)}>
                  Open here
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => openOnMonitor(r.short_code)}>
                  Open on monitor
                </button>
                {byCode[r.short_code] && (
                  <Link className="btn btn-ghost" to={`/alerts?tenant=${byCode[r.short_code]}`}>
                    Alerts
                  </Link>
                )}
              </div>
            </article>
          ))}
          {rows.length === 0 && !err && <div className="empty">No customers found.</div>}
        </div>
      </div>
    </div>
  );
}
