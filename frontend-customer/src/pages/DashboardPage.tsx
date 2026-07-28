import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getCustomerDashboardV2 } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
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
import { useCustomerQuery } from "../hooks/useCustomerQuery";
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

export default function DashboardPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [edrMetrics, setEdrMetrics] = useState<EdrMetricsSummary | null>(null);
  const [edrLoading, setEdrLoading] = useState(true);

  useEffect(() => {
    if (!shortCode) {
      setEdrMetrics(null);
      setEdrLoading(false);
      return;
    }
    setEdrLoading(true);
    getEdrMetrics(shortCode)
      .then(setEdrMetrics)
      .catch(() => setEdrMetrics(null))
      .finally(() => setEdrLoading(false));
  }, [shortCode]);

  const { status, data, errorMessage, refetch } = useCustomerQuery(
    () => getCustomerDashboardV2(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );
  const [selected, setSelected] = useState<DrawerIncident | null>(null);
  const [feedSeverity, setFeedSeverity] = useState<string | null>(null);
  const [liveFeed, setLiveFeed] = useState(false);
  const [liveTick, setLiveTick] = useState(0);

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
    if (!liveFeed) return;
    const tick = () => {
      refetch();
      setLiveTick((n) => n + 1);
    };
    tick();
    const id = window.setInterval(tick, 8000);
    return () => window.clearInterval(id);
  }, [liveFeed, refetch]);

  const incidents = data?.recent_incidents ?? [];
  const filteredIncidents = useMemo(
    () => incidents.filter((i) => matchesSeverity(i.severity, feedSeverity)),
    [incidents, feedSeverity]
  );
  const buckets = useMemo(
    () => buildHourlyBuckets(incidents.map((i) => i.opened_at)),
    [incidents]
  );
  const stackedBuckets = useMemo(
    () =>
      buildStackedHourlyBuckets(
        incidents.map((i) => ({ at: i.opened_at, severity: i.severity }))
      ),
    [incidents]
  );

  const severitySlices = useMemo(() => {
    const map: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const a of data?.recent_alerts ?? []) {
      const key = (a.severity || "low").toLowerCase();
      if (key in map) map[key] += 1;
      else if (key === "info") map.low += 1;
    }
    if ((data?.recent_alerts.length ?? 0) === 0 && data) {
      const hc = data.kpis.high_critical_alerts || 0;
      map.high = Math.ceil(hc / 2);
      map.critical = Math.floor(hc / 2);
    }
    return Object.entries(map).map(([severity, count]) => ({ severity, count }));
  }, [data]);

  const heatSpots = useMemo(
    () =>
      hubsFromActivity(
        (data?.kpis.open_incidents ?? 0) + (data?.kpis.high_critical_alerts ?? 0) * 2,
        liveTick
      ),
    [data, liveTick]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Security overview</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant.
        </div>
      </div>
    );
  }

  const eventsMonitored = data
    ? data.kpis.high_critical_alerts + data.kpis.assets_monitored * 10 + data.recent_alerts.length
    : 0;
  const slaPercent = data
    ? Math.max(
        50,
        Math.min(
          99,
          92 -
            data.kpis.open_incidents * 3 -
            data.kpis.high_critical_alerts +
            data.kpis.appliances_online * 2
        )
      )
    : 0;

  const hasStacked = stackedBuckets.some(
    (b) => b.critical + b.high + b.medium + b.low > 0
  );

  return (
    <div className="command-dashboard">
      <div className="sentinel-dashboard-head">
        <div>
          <h1 className="page-title">Security overview</h1>
          <p className="page-subtitle">
            Your organization&apos;s command view — KPIs, severity timelines, and regional
            intensity (customer-safe data only).
          </p>
        </div>
        <div className="command-chip-row" role="toolbar" aria-label="Dashboard controls">
          <button type="button" className="command-chip is-active" aria-pressed="true">
            Last 24h
          </button>
          <button type="button" className="command-chip is-active" aria-pressed="true">
            Your tenant
          </button>
          <button
            type="button"
            className={"command-chip command-chip--live" + (liveFeed ? " is-active is-live" : "")}
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
          Live feed on — refreshing every 8s{liveTick > 0 ? ` · tick #${liveTick}` : ""}
        </div>
      ) : null}
      {status === "loading" && <div className="state-message">Loading workspace…</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        <>
          <div className="kpi-row-4">
            <Link
              className="kpi-card kpi-card--critical card-surface kpi-card--link"
              to="/incidents?status=open"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Active Incidents</span>
                <span className="kpi-orb kpi-orb--critical" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--critical">{data.kpis.open_incidents}</div>
              <div className="kpi-foot">Open cases · click to review</div>
            </Link>

            <Link className="kpi-card kpi-card--accent card-surface kpi-card--link" to="/assets">
              <div className="kpi-card-top">
                <span className="kpi-label">Events / Assets</span>
                <MiniSparkline values={sparkFromTotal(eventsMonitored)} />
              </div>
              <div className="kpi-value kpi-value--accent">
                {eventsMonitored >= 1000
                  ? `${(eventsMonitored / 1000).toFixed(1)}K`
                  : eventsMonitored.toLocaleString()}
              </div>
              <div className="kpi-foot">Collectors online: {data.kpis.appliances_online}</div>
            </Link>

            <Link
              className="kpi-card kpi-card--high card-surface kpi-card--link"
              to="/alerts?severity=high"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Security Alerts</span>
                <span className="kpi-orb kpi-orb--high" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--high">{data.kpis.high_critical_alerts}</div>
              <div className="kpi-foot">High / critical · click to filter</div>
            </Link>

            <Link
              className="kpi-card kpi-card--low card-surface kpi-card--link"
              to="/recommendations"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Automation / SLA</span>
                <RadialGauge percent={slaPercent} label="SLA" />
              </div>
              <div className="kpi-value kpi-value--low">{slaPercent}%</div>
              <div className="kpi-foot">Click → recommendations</div>
            </Link>
          </div>

          <EdrMetricsStrip metrics={edrMetrics} loading={edrLoading} />

          <SocEfficiencyStrip
            openIncidents={data.kpis.open_incidents}
            highCritical={data.kpis.high_critical_alerts}
            onlineAppliances={data.kpis.appliances_online}
            offlineAppliances={data.kpis.appliances_other}
          />

          <div className="analytics-row analytics-row--trio">
            <Link className="timeline-panel-link" to="/incidents" aria-label="Open incidents">
              <TimelineChart
                buckets={hasStacked ? stackedBuckets : buckets}
                title="Incidents over time (24h)"
                stacked={hasStacked}
              />
            </Link>
            <SeverityDonut
              slices={severitySlices}
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
              title="Activity heatmap"
              liveTick={liveTick}
              footnote="Aggregated overlay for your package — never raw IP locations."
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
                  <Link className="ops-grid-meta cell-mono" to="/incidents">
                    {filteredIncidents.length}/{incidents.length} rows · view all
                  </Link>
                </div>
              </div>

              {filteredIncidents.length === 0 ? (
                <div className="state-message">
                  No incidents{feedSeverity ? ` matching “${feedSeverity}”` : ""} to show.
                </div>
              ) : (
                <table className="data-table data-table--readable">
                  <thead>
                    <tr>
                      <th>Incident ID</th>
                      <th>Title / Rule Name</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th>Summary</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredIncidents.map((inc) => {
                      const active = selected?.incident_number === inc.incident_number;
                      return (
                        <tr
                          key={inc.incident_number}
                          className={active ? "is-selected-row" : undefined}
                          onClick={() =>
                            setSelected({
                              incident_number: inc.incident_number,
                              title: inc.title,
                              severity: inc.severity,
                              status: inc.status,
                              summary: inc.customer_visible_summary,
                              business_impact: inc.business_impact,
                              customer_action_required: inc.customer_action_required,
                              opened_at: inc.opened_at,
                              detailPath: `/incidents/${encodeURIComponent(inc.incident_number)}`,
                            })
                          }
                        >
                          <td className="cell-mono text-cyan">{inc.incident_number}</td>
                          <td className="cell-truncate" title={inc.title}>
                            {inc.title}
                          </td>
                          <td>
                            <SeverityPill value={inc.severity} onIsolate={(v) => setFeedSeverity(v)} />
                          </td>
                          <td>
                            <SeverityPill value={inc.status} kind="status" filterBase="/incidents" />
                          </td>
                          <td className="cell-truncate" title={inc.customer_visible_summary ?? ""}>
                            {inc.customer_visible_summary ?? "—"}
                          </td>
                          <td className="cell-mono">{inc.opened_at ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <IncidentDetailPanel incident={selected} mode="customer" />
          </div>
        </>
      )}
    </div>
  );
}
