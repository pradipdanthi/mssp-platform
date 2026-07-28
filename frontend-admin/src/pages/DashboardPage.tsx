import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard, getIncidents, getTenants, type Incident } from "../api/admin";
import { getStoredTenantFilter } from "../components/TenantSwitcher";
import DetectionStackPanel from "../components/DetectionStackPanel";
import GeoActivityHeatmap, { hubsFromActivity } from "../components/GeoActivityHeatmap";
import IncidentDetailPanel from "../components/IncidentDetailPanel";
import type { DrawerIncident } from "../components/IncidentDrawer";
import MiniSparkline from "../components/MiniSparkline";
import RadialGauge from "../components/RadialGauge";
import SeverityDonut from "../components/SeverityDonut";
import SeverityPill from "../components/SeverityPill";
import SocEfficiencyStrip from "../components/SocEfficiencyStrip";
import TimelineChart, {
  buildHourlyBuckets,
  buildStackedHourlyBuckets,
} from "../components/TimelineChart";
import { useAdminQuery } from "../hooks/useAdminQuery";
import EdrMetricsStrip from "../components/edr/EdrMetricsStrip";
import { getEdrMetrics, type EdrMetricsSummary } from "../api/edr";

const LIVE_FEED_KEY = "kestrel-live-feed";
const LIVE_FEED_EVENT = "kestrel-live-feed-change";

function publishLiveFeed(on: boolean) {
  try {
    sessionStorage.setItem(LIVE_FEED_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(LIVE_FEED_EVENT));
}

type TimeWindow = "24h" | "7d";

function sparkFromTotal(n: number): number[] {
  const base = Math.max(n, 1);
  return Array.from({ length: 12 }, (_, i) =>
    Math.max(0, Math.round(base * (0.55 + 0.08 * Math.sin(i) + (i / 12) * 0.35)))
  );
}

function matchesSeverity(sev: string, filter: string | null): boolean {
  if (!filter) return true;
  const s = sev.toLowerCase();
  const f = filter.toLowerCase();
  if (f === "urgent") return s === "high" || s === "critical";
  return s === f;
}

function withinWindow(iso: string | null | undefined, window: TimeWindow): boolean {
  if (!iso) return window === "7d";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return true;
  const hours = window === "24h" ? 24 : 24 * 7;
  return t >= Date.now() - hours * 3600_000;
}

function toDrawer(inc: Incident): DrawerIncident {
  return {
    id: inc.id,
    incident_number: inc.incident_number,
    title: inc.title,
    severity: inc.severity,
    status: inc.status,
    tenant_name: inc.tenant_name,
    short_code: inc.short_code,
    assigned_to: inc.assigned_to,
    summary: inc.customer_visible_summary,
    opened_at: inc.opened_at,
    affected_entity: inc.tenant_name ? `${inc.short_code || "host"}-01` : "Pending enrichment",
    source_ip: null,
    target_ip: null,
    rule_source: "SIEM → Incident Response",
    detailPath: `/incidents/${inc.id}`,
  };
}

export default function DashboardPage() {
  const dash = useAdminQuery(() => getDashboard(), []);
  const incidentsQ = useAdminQuery(() => getIncidents(), []);
  const [selected, setSelected] = useState<DrawerIncident | null>(null);
  const [feedSeverity, setFeedSeverity] = useState<string | null>(null);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("24h");
  const [crossTenant, setCrossTenant] = useState(true);
  const [liveFeed, setLiveFeed] = useState(false);
  const [liveTick, setLiveTick] = useState(0);
  const [tenantFilter, setTenantFilter] = useState(getStoredTenantFilter);
  const [tenantCodeById, setTenantCodeById] = useState<Record<string, string>>({});
  const [edrMetrics, setEdrMetrics] = useState<EdrMetricsSummary | null>(null);
  const [edrLoading, setEdrLoading] = useState(true);

  useEffect(() => {
    setEdrLoading(true);
    getEdrMetrics(tenantFilter || undefined)
      .then(setEdrMetrics)
      .catch(() => setEdrMetrics(null))
      .finally(() => setEdrLoading(false));
  }, [tenantFilter]);

  useEffect(() => {
    publishLiveFeed(liveFeed);
  }, [liveFeed]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelected(null);
        setFeedSeverity(null);
      }
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, []);

  useEffect(() => {
    const onTenant = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (typeof detail === "string") setTenantFilter(detail);
    };
    window.addEventListener("mssp-tenant-filter", onTenant as EventListener);
    return () => window.removeEventListener("mssp-tenant-filter", onTenant as EventListener);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getTenants()
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, string> = {};
        for (const t of res.tenants || []) map[t.id] = t.short_code;
        setTenantCodeById(map);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Live feed: poll dashboard + incidents; bump heatmap tick for visual refresh
  useEffect(() => {
    if (!liveFeed) return;
    const tick = () => {
      dash.refetch();
      incidentsQ.refetch();
      setLiveTick((n) => n + 1);
    };
    tick();
    const id = window.setInterval(tick, 8000);
    return () => window.clearInterval(id);
  }, [liveFeed, dash.refetch, incidentsQ.refetch]);

  const incidents: Incident[] = incidentsQ.data?.incidents ?? [];

  const scopedIncidents = useMemo(() => {
    let rows = incidents.filter((i) => withinWindow(i.opened_at || i.created_at, timeWindow));
    if (!crossTenant) {
      if (tenantFilter !== "all") {
        const code = tenantCodeById[tenantFilter]?.toUpperCase();
        rows = rows.filter((i) => {
          if (code && i.short_code?.toUpperCase() === code) return true;
          return i.short_code === tenantFilter || i.tenant_name === tenantFilter;
        });
      } else if (rows.length > 0) {
        const first = rows[0].short_code;
        rows = rows.filter((i) => i.short_code === first);
      }
    }
    return rows;
  }, [incidents, timeWindow, crossTenant, tenantFilter, tenantCodeById]);

  const filteredIncidents = useMemo(
    () => scopedIncidents.filter((i) => matchesSeverity(i.severity, feedSeverity)),
    [scopedIncidents, feedSeverity]
  );

  const buckets = useMemo(
    () =>
      buildHourlyBuckets(
        scopedIncidents.map((i) => i.opened_at || i.created_at),
        timeWindow === "24h" ? 24 : 24
      ),
    [scopedIncidents, timeWindow]
  );
  const stackedBuckets = useMemo(
    () =>
      buildStackedHourlyBuckets(
        scopedIncidents.map((i) => ({
          at: i.opened_at || i.created_at,
          severity: i.severity,
        })),
        timeWindow === "24h" ? 24 : 24
      ),
    [scopedIncidents, timeWindow]
  );

  const overview = dash.data?.overview;
  const eventsMonitored = overview
    ? overview.total_alerts + overview.protected_assets * 10 + liveTick * 3
    : 0;
  const slaPercent = overview
    ? Math.max(
        40,
        Math.min(
          99,
          Math.round(
            100 -
              overview.open_incidents * 4 -
              overview.high_or_critical_alerts * 2 +
              overview.online_appliances * 2
          )
        )
      )
    : 0;
  const heatSpots = useMemo(
    () =>
      hubsFromActivity(
        (overview?.open_incidents ?? 0) +
          (overview?.high_or_critical_alerts ?? 0) * 2 +
          scopedIncidents.length,
        liveTick
      ),
    [overview, scopedIncidents.length, liveTick]
  );

  const selectIncident = useCallback((inc: Incident) => {
    setSelected(toDrawer(inc));
  }, []);

  const loading = dash.status === "loading" || incidentsQ.status === "loading";
  const forbidden = dash.status === "forbidden" || incidentsQ.status === "forbidden";
  const error =
    dash.status === "error"
      ? dash.errorMessage
      : incidentsQ.status === "error"
        ? incidentsQ.errorMessage
        : null;

  const hasStacked = stackedBuckets.some(
    (b) => b.critical + b.high + b.medium + b.low > 0
  );

  return (
    <div className="command-dashboard">
      <div className="sentinel-dashboard-head">
        <div>
          <h1 className="page-title">Security operations</h1>
          <p className="page-subtitle">
            MSSP command center — KPIs, anomaly heatmap, and investigation workspace.
          </p>
        </div>
        <div className="command-chip-row" role="toolbar" aria-label="Dashboard controls">
          <button
            type="button"
            className={"command-chip" + (timeWindow === "24h" ? " is-active" : "")}
            aria-pressed={timeWindow === "24h"}
            onClick={() => setTimeWindow("24h")}
          >
            Last 24h
          </button>
          <button
            type="button"
            className={"command-chip" + (timeWindow === "7d" ? " is-active" : "")}
            aria-pressed={timeWindow === "7d"}
            onClick={() => setTimeWindow("7d")}
          >
            Last 7d
          </button>
          <button
            type="button"
            className={"command-chip" + (crossTenant ? " is-active" : "")}
            aria-pressed={crossTenant}
            title={
              crossTenant
                ? "Showing all tenants — click to scope to header tenant filter / first tenant"
                : "Scoped tenant view — click for cross-tenant"
            }
            onClick={() => setCrossTenant((v) => !v)}
          >
            Cross-tenant
          </button>
          <button
            type="button"
            className={
              "command-chip command-chip--live" + (liveFeed ? " is-active is-live" : "")
            }
            aria-pressed={liveFeed}
            onClick={() => setLiveFeed((v) => !v)}
          >
            Live feed
            <span className={"live-dot" + (liveFeed ? " is-on" : "")} aria-hidden="true" />
          </button>
        </div>
      </div>

      {liveFeed ? (
        <div className="live-banner" role="status">
          Live feed on — refreshing metrics &amp; heatmap every 8s
          {liveTick > 0 ? ` · tick #${liveTick}` : ""}
        </div>
      ) : null}

      {loading && !overview && <div className="state-message">Loading workspace…</div>}
      {forbidden && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view this data.
        </div>
      )}
      {error && <div className="state-message state-error">{error}</div>}

      {overview && (
        <>
          <div className="kpi-row-4">
            <Link
              className="kpi-card kpi-card--critical card-surface kpi-card--link"
              to="/incidents?status=open"
              aria-label="Open active incidents"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Active Incidents</span>
                <span className="kpi-orb kpi-orb--critical" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--critical">{overview.open_incidents}</div>
              <div className="kpi-foot">
                {crossTenant ? "Cross-tenant" : "Scoped"} · {timeWindow}
              </div>
            </Link>

            <Link
              className="kpi-card kpi-card--accent card-surface kpi-card--link"
              to="/appliances?status=offline"
              aria-label="Open offline appliances"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Events Collected</span>
                <MiniSparkline values={sparkFromTotal(eventsMonitored)} />
              </div>
              <div className="kpi-value kpi-value--accent">
                {eventsMonitored >= 1000
                  ? `${(eventsMonitored / 1000).toFixed(1)}K`
                  : eventsMonitored.toLocaleString()}
              </div>
              <div className="kpi-foot">Offline collectors: {overview.offline_appliances}</div>
            </Link>

            <Link
              className="kpi-card kpi-card--high card-surface kpi-card--link"
              to="/alerts?severity=high"
              aria-label="Open high severity alerts"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Security Alerts</span>
                <span className="kpi-orb kpi-orb--high" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--high">{overview.high_or_critical_alerts}</div>
              <div className="kpi-foot">High / critical · click to filter</div>
            </Link>

            <Link
              className="kpi-card kpi-card--low card-surface kpi-card--link"
              to="/tenants"
              aria-label="Open customers / tenants"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Automation / SLA</span>
                <RadialGauge percent={slaPercent} label="SLA" />
              </div>
              <div className="kpi-value kpi-value--low">{slaPercent}%</div>
              <div className="kpi-foot">
                {overview.active_tenants}/{overview.total_tenants} active tenants
              </div>
            </Link>
          </div>

          <EdrMetricsStrip metrics={edrMetrics} loading={edrLoading} />

          <SocEfficiencyStrip
            openIncidents={overview.open_incidents}
            highCritical={overview.high_or_critical_alerts}
            onlineAppliances={overview.online_appliances}
            offlineAppliances={overview.offline_appliances}
          />

          <div className="analytics-row analytics-row--trio">
            <Link className="timeline-panel-link" to="/incidents" aria-label="Open incidents timeline">
              <TimelineChart
                buckets={hasStacked ? stackedBuckets : buckets}
                title={`Incidents over time (${timeWindow})`}
                stacked={hasStacked}
              />
            </Link>
            <SeverityDonut
              slices={
                (dash.data?.severity_breakdown?.length
                  ? dash.data.severity_breakdown
                  : [
                      { severity: "high", count: overview.high_or_critical_alerts || 0 },
                      { severity: "medium", count: 0 },
                      { severity: "low", count: 0 },
                      { severity: "critical", count: 0 },
                    ]) as { severity: string; count: number }[]
              }
              title="Alerts"
              showMitre
              activeSeverity={feedSeverity}
              onSeveritySelect={(sev) =>
                setFeedSeverity((prev) => (prev?.toLowerCase() === sev.toLowerCase() ? null : sev))
              }
              severityHref={(sev) => `/alerts?severity=${encodeURIComponent(sev)}`}
            />
            <GeoActivityHeatmap
              spots={heatSpots}
              title="Log Source Anomaly Heatmap"
              liveTick={liveTick}
            />
          </div>

          <DetectionStackPanel />

          <div className="ops-split">
            <div className="ops-split-main">
              <div className="ops-grid-header">
                <h2 className="section-title">Incidents</h2>
                <div className="ops-grid-actions">
                  {feedSeverity ? (
                    <button
                      type="button"
                      className="filter-chip"
                      onClick={() => setFeedSeverity(null)}
                    >
                      Isolated: {feedSeverity} ×
                    </button>
                  ) : null}
                  {!crossTenant ? (
                    <span className="filter-chip">Tenant scoped</span>
                  ) : null}
                  <Link className="ops-grid-meta cell-mono" to="/incidents">
                    {filteredIncidents.length}/{scopedIncidents.length} rows · view all
                  </Link>
                </div>
              </div>

              {filteredIncidents.length === 0 ? (
                <div className="state-message">
                  No incidents
                  {feedSeverity ? ` matching “${feedSeverity}”` : ""}
                  {!crossTenant ? " in scoped tenant view" : ""}
                  {` for ${timeWindow}`}.
                </div>
              ) : (
                <table className="data-table data-table--readable">
                  <thead>
                    <tr>
                      <th>Incident ID</th>
                      <th>Title / Rule Name</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Assignee</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredIncidents.slice(0, 40).map((inc) => {
                      const active = selected?.id === inc.id;
                      return (
                        <tr
                          key={inc.id}
                          className={active ? "is-selected-row" : undefined}
                          onClick={() => selectIncident(inc)}
                        >
                          <td className="cell-mono text-cyan">{inc.incident_number}</td>
                          <td className="cell-truncate" title={inc.title}>
                            {inc.title}
                            {crossTenant ? (
                              <div className="row-submeta">{inc.tenant_name}</div>
                            ) : null}
                          </td>
                          <td>
                            <SeverityPill
                              value={inc.severity}
                              onIsolate={(v) => setFeedSeverity(v)}
                            />
                          </td>
                          <td>
                            <SeverityPill
                              value={inc.status}
                              kind="status"
                              filterBase="/incidents"
                            />
                          </td>
                          <td>{inc.assigned_to ?? "—"}</td>
                          <td className="cell-mono">{inc.opened_at ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <IncidentDetailPanel incident={selected} mode="admin" />
          </div>
        </>
      )}
    </div>
  );
}
