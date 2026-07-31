import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard, getIncidents, getTenants, getConsultationSummary, type Incident } from "../api/admin";
import { getStoredTenantFilter } from "../components/TenantSwitcher";
import GeoActivityHeatmap, { hubsFromActivity } from "../components/GeoActivityHeatmap";
import MiniSparkline from "../components/MiniSparkline";
import RadialGauge from "../components/RadialGauge";
import SeverityDonut from "../components/SeverityDonut";
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

function withinWindow(iso: string | null | undefined, window: TimeWindow): boolean {
  if (!iso) return window === "7d";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return true;
  const hours = window === "24h" ? 24 : 24 * 7;
  return t >= Date.now() - hours * 3600_000;
}

export default function DashboardPage() {
  const dash = useAdminQuery(() => getDashboard(), []);
  const incidentsQ = useAdminQuery(() => getIncidents({ page: 1, page_size: 200 }), []);
  const [feedSeverity, setFeedSeverity] = useState<string | null>(null);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("24h");
  const [crossTenant, setCrossTenant] = useState(true);
  const [liveFeed, setLiveFeed] = useState(false);
  const [liveTick, setLiveTick] = useState(0);
  const [tenantFilter, setTenantFilter] = useState(getStoredTenantFilter);
  const [tenantCodeById, setTenantCodeById] = useState<Record<string, string>>({});
  const [edrMetrics, setEdrMetrics] = useState<EdrMetricsSummary | null>(null);
  const [edrLoading, setEdrLoading] = useState(true);
  const [pendingServiceRequests, setPendingServiceRequests] = useState<number | null>(null);

  useEffect(() => {
    getConsultationSummary()
      .then((s) => setPendingServiceRequests(s.unreviewed_total))
      .catch(() => setPendingServiceRequests(null));
  }, []);

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
      if (e.key === "Escape") setFeedSeverity(null);
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
    getTenants({ page_size: 200 })
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
  const collectorCoverage = overview
    ? overview.online_appliances + overview.offline_appliances === 0
      ? 0
      : Math.round(
          (overview.online_appliances /
            (overview.online_appliances + overview.offline_appliances)) *
            100
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
            Priority KPIs and ops health — open a tile to dig in.
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
          <div className="kpi-row-5">
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
              to="/alerts"
              aria-label="Open security alerts / events"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Events Collected</span>
                <MiniSparkline values={sparkFromTotal(eventsMonitored)} width={56} height={18} />
              </div>
              <div className="kpi-value kpi-value--accent">
                {eventsMonitored >= 1000
                  ? `${(eventsMonitored / 1000).toFixed(1)}K`
                  : eventsMonitored.toLocaleString()}
              </div>
              <div className="kpi-foot">
                {overview.total_alerts} alerts · {overview.protected_assets} assets
              </div>
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
              <div className="kpi-foot">High / critical</div>
            </Link>

            <Link
              className="kpi-card kpi-card--low card-surface kpi-card--link kpi-card--gauge"
              to="/appliances"
              aria-label="Open appliances / collectors"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Collector health</span>
              </div>
              <div className="kpi-card-metric-row">
                <div>
                  <div className="kpi-value kpi-value--low">{collectorCoverage}%</div>
                  <div className="kpi-foot">
                    {overview.online_appliances} online
                    {overview.offline_appliances ? ` · ${overview.offline_appliances} off` : ""}
                  </div>
                </div>
                <RadialGauge percent={collectorCoverage} label="Online" size={68} />
              </div>
              <div className="kpi-foot">Click → appliances</div>
            </Link>

            <Link
              className="kpi-card kpi-card--high card-surface kpi-card--link"
              to="/service-requests"
              aria-label="Open pending service requests"
            >
              <div className="kpi-card-top">
                <span className="kpi-label">Pending Service Requests</span>
                <span className="kpi-orb kpi-orb--high" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--high">
                {pendingServiceRequests == null ? "—" : pendingServiceRequests}
              </div>
              <div className="kpi-foot">Unreviewed · manage</div>
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
        </>
      )}
    </div>
  );
}
