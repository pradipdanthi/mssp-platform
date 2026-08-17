import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  getDashboard,
  getIncidents,
  getTenants,
  getConsultationSummary,
  getApplianceCommandSummary,
  type Incident,
  type ApplianceCommandSummary,
} from "../api/admin";
import {
  getStoredTenantFilter,
  setStoredTenantFilter,
  TENANT_FILTER_EVENT,
} from "../components/TenantSwitcher";
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
import { useAuth } from "../auth/AuthContext";
import KpiIcon from "../components/icons/KpiIcon";

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
  if (n <= 0) return Array.from({ length: 12 }, () => 0);
  const base = n;
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
  const { user } = useAuth();
  const [feedSeverity, setFeedSeverity] = useState<string | null>(null);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("24h");
  const [liveFeed, setLiveFeed] = useState(false);
  const [liveTick, setLiveTick] = useState(0);
  const [tenantFilter, setTenantFilter] = useState(getStoredTenantFilter);
  const [tenantMetaById, setTenantMetaById] = useState<
    Record<string, { name: string; short_code: string }>
  >({});
  const [edrMetrics, setEdrMetrics] = useState<EdrMetricsSummary | null>(null);
  const [edrLoading, setEdrLoading] = useState(true);
  const [pendingServiceRequests, setPendingServiceRequests] = useState<number | null>(null);
  const [applianceCmd, setApplianceCmd] = useState<ApplianceCommandSummary | null>(null);

  const scopedTenantId = tenantFilter !== "all" ? tenantFilter : undefined;
  const crossTenant = !scopedTenantId;
  const scopedTenantLabel = scopedTenantId
    ? tenantMetaById[scopedTenantId]?.name ||
      tenantMetaById[scopedTenantId]?.short_code ||
      "Selected customer"
    : "All tenants";

  const dash = useAdminQuery(
    () => getDashboard(scopedTenantId ? { tenant_id: scopedTenantId } : undefined),
    [scopedTenantId]
  );
  const incidentsQ = useAdminQuery(
    () =>
      getIncidents({
        page: 1,
        page_size: 200,
        ...(scopedTenantId ? { tenant_id: scopedTenantId } : {}),
      }),
    [scopedTenantId]
  );

  useEffect(() => {
    getConsultationSummary(scopedTenantId ? { tenant_id: scopedTenantId } : undefined)
      .then((s) => setPendingServiceRequests(s.unreviewed_total))
      .catch(() => setPendingServiceRequests(null));
  }, [scopedTenantId]);

  useEffect(() => {
    getApplianceCommandSummary(scopedTenantId ? { tenant_id: scopedTenantId } : undefined)
      .then(setApplianceCmd)
      .catch(() => setApplianceCmd(null));
  }, [liveTick, scopedTenantId]);

  useEffect(() => {
    const shortCode = scopedTenantId
      ? tenantMetaById[scopedTenantId]?.short_code
      : undefined;
    if (scopedTenantId && !shortCode) return;
    setEdrLoading(true);
    getEdrMetrics(shortCode)
      .then(setEdrMetrics)
      .catch(() => setEdrMetrics(null))
      .finally(() => setEdrLoading(false));
  }, [scopedTenantId, tenantMetaById]);

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
    window.addEventListener(TENANT_FILTER_EVENT, onTenant as EventListener);
    return () => window.removeEventListener(TENANT_FILTER_EVENT, onTenant as EventListener);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getTenants({ page_size: 200 })
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, { name: string; short_code: string }> = {};
        for (const t of res.tenants || []) {
          map[t.id] = { name: t.name, short_code: t.short_code };
        }
        setTenantMetaById(map);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

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
  }, [liveFeed, dash.refetch, incidentsQ.refetch, scopedTenantId]);

  const incidents: Incident[] = incidentsQ.data?.incidents ?? [];

  const scopedIncidents = useMemo(() => {
    let rows = incidents.filter((i) => withinWindow(i.opened_at || i.created_at, timeWindow));
    if (scopedTenantId) {
      const meta = tenantMetaById[scopedTenantId];
      const code = meta?.short_code?.toUpperCase();
      rows = rows.filter((i) => {
        if (code && i.short_code?.toUpperCase() === code) return true;
        return i.short_code === scopedTenantId || i.tenant_name === meta?.name;
      });
    }
    return rows;
  }, [incidents, timeWindow, scopedTenantId, tenantMetaById]);

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
  const eventsMonitored = overview ? overview.total_alerts : 0;
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
    <div className="command-dashboard" data-testid="admin-dashboard">
      <div className="sentinel-dashboard-head">
        <div className="dash-welcome">
          <p className="dash-welcome-kicker">Welcome back,</p>
          <h1 className="dash-welcome-name" data-testid="admin-dashboard-welcome">
            {user?.full_name || "Administrator"}
          </h1>
          <p className="page-subtitle">
            Priority KPIs and ops health — open a tile to dig in.
          </p>
        </div>
        <div
          className="command-chip-row"
          role="toolbar"
          aria-label="Dashboard controls"
          data-testid="admin-dashboard-controls"
        >
          <button
            type="button"
            className={"command-chip" + (timeWindow === "24h" ? " is-active" : "")}
            aria-pressed={timeWindow === "24h"}
            data-testid="filter-window-24h"
            onClick={() => setTimeWindow("24h")}
          >
            Last 24h
          </button>
          <button
            type="button"
            className={"command-chip" + (timeWindow === "7d" ? " is-active" : "")}
            aria-pressed={timeWindow === "7d"}
            data-testid="filter-window-7d"
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
                ? "Showing all customers — pick one in the header Customer scope dropdown to filter"
                : `Scoped to ${scopedTenantLabel} — click to show all customers`
            }
            onClick={() => {
              if (!crossTenant) {
                setTenantFilter("all");
                setStoredTenantFilter("all");
              }
            }}
          >
            {crossTenant ? "Cross-tenant" : `Scoped: ${scopedTenantLabel}`}
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
          {applianceCmd ? (
            <div className="kpi-row-5" style={{ marginBottom: "1rem" }}>
              <Link
                className="kpi-card card-surface kpi-card--link"
                to="/appliances"
                aria-label="Open appliances"
              >
                <div className="kpi-card-top">
                  <KpiIcon name="monitor" />
                  <span className="kpi-label">Edge appliances</span>
                </div>
                <div className="kpi-value">
                  {applianceCmd.appliances.online}/{applianceCmd.appliances.total}
                </div>
                <div className="kpi-foot">
                  Online · {applianceCmd.appliances.offline} offline
                </div>
              </Link>
              <div className="kpi-card card-surface">
                <div className="kpi-card-top">
                  <KpiIcon name="database" />
                  <span className="kpi-label">Data Lake volume</span>
                </div>
                <div className="kpi-value">
                  {Number(applianceCmd.appliances.disk_used_gb_total || 0).toFixed(1)} GB
                </div>
                <div className="kpi-foot">Aggregate appliance storage</div>
              </div>
              <Link
                className="kpi-card card-surface kpi-card--link"
                to="/retrospective-hunts"
                aria-label="Open retrospective hunts"
              >
                <div className="kpi-card-top">
                  <KpiIcon name="search" />
                  <span className="kpi-label">Retrospective hunts</span>
                </div>
                <div className="kpi-value">{applianceCmd.hunts.running}</div>
                <div className="kpi-foot">
                  Running · {applianceCmd.hunts.pending} pending · {applianceCmd.hunts.last_24h} / 24h
                </div>
              </Link>
            </div>
          ) : null}

          <div className="kpi-row-5">
            <Link
              className="kpi-card kpi-card--critical card-surface kpi-card--link"
              to="/incidents?status=open"
              aria-label="Open active incidents"
            >
              <div className="kpi-card-top">
                <KpiIcon name="shield" />
                <span className="kpi-label">Active Incidents</span>
                <span className="kpi-orb kpi-orb--critical" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--critical">{overview.open_incidents}</div>
              <div className="kpi-foot">
                {crossTenant ? "Cross-tenant" : scopedTenantLabel} · {timeWindow}
              </div>
            </Link>

            <Link
              className="kpi-card kpi-card--accent card-surface kpi-card--link"
              to="/alerts"
              aria-label="Open security alerts / events"
            >
              <div className="kpi-card-top">
                <KpiIcon name="activity" />
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
                <KpiIcon name="bell" />
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
                <KpiIcon name="monitor" />
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
                <KpiIcon name="inbox" />
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

          <div className="analytics-row analytics-row--trio" data-testid="admin-analytics-row">
            <Link
              className="timeline-panel-link"
              to="/incidents"
              aria-label="Open incidents timeline"
              data-testid="widget-timeline"
            >
              <TimelineChart
                buckets={hasStacked ? stackedBuckets : buckets}
                title={`Incidents over time (${timeWindow})`}
                stacked={hasStacked}
              />
            </Link>
            <div data-testid="widget-severity-donut">
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
                  setFeedSeverity((prev) =>
                    prev?.toLowerCase() === sev.toLowerCase() ? null : sev
                  )
                }
                severityHref={(sev) => `/alerts?severity=${encodeURIComponent(sev)}`}
              />
            </div>
            <div data-testid="widget-geo-heatmap">
              <GeoActivityHeatmap
                spots={heatSpots}
                title="Log Source Anomaly Heatmap"
                liveTick={liveTick}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
