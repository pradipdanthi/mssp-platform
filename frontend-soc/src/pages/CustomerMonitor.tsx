import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import {
  AdminVulnerability,
  AlertRow,
  getAdminDashboard,
  getAlerts,
  getIncidents,
  getPatchGaps,
  getVulnerabilities,
  IncidentRow,
  PatchGapRow,
} from "../api/soc";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Severity from "../components/Severity";
import {
  alertDetailPath,
  alertsListPath,
  incidentDetailPath,
  incidentsListPath,
  patchGapsListPath,
  vulnerabilitiesListPath,
} from "../lib/socPaths";

type OutletCtx = {
  tenant: { id: string; name: string; short_code: string } | null;
  shortCode?: string;
  base: string;
};

/** Customer overview — KPI tiles navigate into scoped list/detail. */
export default function CustomerMonitor() {
  const { shortCode } = useParams<{ shortCode: string }>();
  const { tenant, base } = useOutletContext<OutletCtx>();
  const { logout } = useAuth();
  const [overview, setOverview] = useState<Record<string, number>>({});
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [incidents, setIncidents] = useState<IncidentRow[]>([]);
  const [vulns, setVulns] = useState<AdminVulnerability[]>([]);
  const [patches, setPatches] = useState<PatchGapRow[]>([]);
  const [patchTotal, setPatchTotal] = useState(0);
  const [vulnTotal, setVulnTotal] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tenant) return;
    let cancelled = false;
    Promise.all([
      getAdminDashboard(tenant.id),
      getAlerts({ tenant_id: tenant.id, page_size: 40 }),
      getIncidents({ tenant_id: tenant.id, page_size: 40 }),
      getVulnerabilities({
        tenant_short_code: tenant.short_code,
        status: "open",
        page_size: 40,
      }),
      getPatchGaps({ short_code: tenant.short_code, page_size: 40 }),
    ])
      .then(([dash, a, i, v, p]) => {
        if (cancelled) return;
        setOverview(dash.overview || {});
        setAlerts(a.alerts || []);
        setIncidents(i.incidents || []);
        setVulns(v.vulnerabilities || []);
        setVulnTotal(v.total ?? (v.vulnerabilities || []).length);
        setPatches(p.items || []);
        setPatchTotal(p.total || 0);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Failed to load customer dashboard");
      });
    return () => {
      cancelled = true;
    };
  }, [tenant, logout]);

  if (!tenant) {
    return <div className="empty">Loading customer…</div>;
  }

  return (
    <div className="customer-overview">
      {err && <div className="err" style={{ padding: "0.75rem 1rem" }}>{err}</div>}

      <div className="monitor-kpis">
        <Link className="mk mk-link" to={`${base}/alerts`}>
          <strong>{overview.critical_alerts ?? 0}</strong>
          <span>Critical alerts</span>
        </Link>
        <Link className="mk mk-link" to={`${base}/alerts`}>
          <strong>{overview.high_alerts ?? 0}</strong>
          <span>High alerts</span>
        </Link>
        <Link className="mk mk-link" to={`${base}/incidents`}>
          <strong>{overview.open_incidents ?? 0}</strong>
          <span>Open incidents</span>
        </Link>
        <Link className="mk mk-link" to={`${base}/vulnerabilities`}>
          <strong>{vulnTotal}</strong>
          <span>Open vulns</span>
        </Link>
        <Link className="mk mk-link" to={`${base}/patch-gaps`}>
          <strong>{patchTotal}</strong>
          <span>Patch gaps</span>
        </Link>
        <div className="mk">
          <strong>
            {overview.online_appliances ?? 0}/{overview.total_appliances ?? 0}
          </strong>
          <span>Appliances</span>
        </div>
      </div>

      <div className="monitor-quad">
        <section className="detail-card">
          <h3>
            Security alerts{" "}
            <Link className="muted" to={alertsListPath()}>
              full list →
            </Link>
          </h3>
          <ul className="monitor-list">
            {alerts.slice(0, 20).map((a) => (
              <li key={a.id}>
                <Link to={alertDetailPath(a.id)}>
                  <Severity value={a.severity} /> {a.alert_title || a.title}
                </Link>
                <span className="muted">{a.status}</span>
              </li>
            ))}
            {alerts.length === 0 && <li className="muted">No alerts for this customer</li>}
          </ul>
        </section>

        <section className="detail-card">
          <h3>
            Incidents{" "}
            <Link className="muted" to={incidentsListPath()}>
              full list →
            </Link>
          </h3>
          <ul className="monitor-list">
            {incidents.slice(0, 20).map((i) => (
              <li key={i.id}>
                <Link to={incidentDetailPath(i.id)}>
                  <Severity value={i.severity} /> {i.incident_number} — {i.title}
                </Link>
                <span className="muted">{i.status}</span>
              </li>
            ))}
            {incidents.length === 0 && <li className="muted">No incidents for this customer</li>}
          </ul>
        </section>

        <section className="detail-card">
          <h3>
            Vulnerabilities{" "}
            <Link className="muted" to={vulnerabilitiesListPath()}>
              full list →
            </Link>
          </h3>
          <ul className="monitor-list">
            {vulns.slice(0, 20).map((v) => (
              <li key={v.id}>
                <Link to={vulnerabilitiesListPath()}>
                  <Severity value={v.severity || "medium"} /> {v.cve_id || v.title || v.id}
                </Link>
                <span className="muted">{v.host || v.status || ""}</span>
              </li>
            ))}
            {vulns.length === 0 && <li className="muted">No open findings</li>}
          </ul>
        </section>

        <section className="detail-card">
          <h3>
            Patch gaps{" "}
            <Link className="muted" to={patchGapsListPath()}>
              full list →
            </Link>
          </h3>
          <ul className="monitor-list">
            {patches.slice(0, 20).map((p) => (
              <li key={p.id}>
                <Link to={patchGapsListPath()}>
                  <Severity value={p.severity || "medium"} /> {p.rule_title || p.check_id}
                </Link>
                <span className="muted">{p.agent_name || ""}</span>
              </li>
            ))}
            {patches.length === 0 && <li className="muted">No failed hardening checks</li>}
          </ul>
        </section>
      </div>
      <p className="muted" style={{ padding: "0 1rem 1rem" }}>
        Viewing <strong>{shortCode}</strong> only. Use the tabs above to open full triage (including Isolate on
        incidents).
      </p>
    </div>
  );
}
