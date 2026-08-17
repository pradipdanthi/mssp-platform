import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getCustomerDashboardV2 } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import GeoActivityHeatmap, { hubsFromActivity } from "../components/GeoActivityHeatmap";
import MiniSparkline from "../components/MiniSparkline";
import RadialGauge from "../components/RadialGauge";
import SeverityDonut from "../components/SeverityDonut";
import SocEfficiencyStrip from "../components/SocEfficiencyStrip";
import TimelineChart, {
  buildHourlyBuckets,
  buildStackedHourlyBuckets,
} from "../components/TimelineChart";
import { useCustomerQuery } from "../hooks/useCustomerQuery";
import EdrMetricsStrip from "../components/edr/EdrMetricsStrip";
import { getEdrMetrics, type EdrMetricsSummary } from "../api/edr";
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

function sparkFromTotal(n: number): number[] {
  if (n <= 0) return Array.from({ length: 12 }, () => 0);
  const base = n;
  return Array.from({ length: 12 }, (_, i) =>
    Math.max(0, Math.round(base * (0.55 + 0.08 * Math.sin(i) + (i / 12) * 0.35)))
  );
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
  const [feedSeverity, setFeedSeverity] = useState<string | null>(null);
  const [liveFeed, setLiveFeed] = useState(false);
  const [liveTick, setLiveTick] = useState(0);

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
      /* Keep zeros — do not invent severity slices when there are no alerts. */
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

  const eventsMonitored = data ? data.kpis.total_alerts : 0;

  const hasStacked = stackedBuckets.some(
    (b) => b.critical + b.high + b.medium + b.low > 0
  );

  return (
    <div className="command-dashboard" data-testid="customer-dashboard">
      <div className="sentinel-dashboard-head">
        <div className="dash-welcome">
          <p className="dash-welcome-kicker">Welcome back,</p>
          <h1 className="dash-welcome-name" data-testid="customer-dashboard-welcome">
            {user?.full_name || "Customer"}
          </h1>
          <p className="page-subtitle">
            Priority KPIs for your organization — open a tile to dig in.
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
                <KpiIcon name="shield" />
                <span className="kpi-label">Active Incidents</span>
                <span className="kpi-orb kpi-orb--critical" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--critical">{data.kpis.open_incidents}</div>
              <div className="kpi-foot">Open cases · click to review</div>
            </Link>

            <Link
              className="kpi-card kpi-card--accent card-surface kpi-card--link"
              to="/alerts"
              aria-label="Open security alerts / events"
            >
              <div className="kpi-card-top">
                <KpiIcon name="activity" />
                <span className="kpi-label">Events monitored</span>
                <MiniSparkline values={sparkFromTotal(eventsMonitored)} width={56} height={18} />
              </div>
              <div className="kpi-value kpi-value--accent">
                {eventsMonitored >= 1000
                  ? `${(eventsMonitored / 1000).toFixed(1)}K`
                  : eventsMonitored.toLocaleString()}
              </div>
              <div className="kpi-foot">
                {data.kpis.total_alerts} alerts · {data.kpis.assets_monitored} assets
              </div>
            </Link>

            <Link
              className="kpi-card kpi-card--high card-surface kpi-card--link"
              to="/alerts?severity=high"
            >
              <div className="kpi-card-top">
                <KpiIcon name="bell" />
                <span className="kpi-label">Security Alerts</span>
                <span className="kpi-orb kpi-orb--high" aria-hidden="true" />
              </div>
              <div className="kpi-value kpi-value--high">{data.kpis.high_critical_alerts}</div>
              <div className="kpi-foot">High / critical</div>
            </Link>

            <Link
              className="kpi-card kpi-card--low card-surface kpi-card--link kpi-card--gauge"
              to="/recommendations"
              aria-label="Open recommendations"
            >
              <div className="kpi-card-top">
                <KpiIcon name="check" />
                <span className="kpi-label">Open recommendations</span>
              </div>
              <div className="kpi-card-metric-row">
                <div>
                  <div className="kpi-value kpi-value--low">
                    {data.kpis.open_recommendations ?? 0}
                  </div>
                  <div className="kpi-foot">Open items</div>
                </div>
                <RadialGauge
                  size={68}
                  percent={Math.min(
                    99,
                    Math.max(
                      5,
                      100 - Math.min(90, (data.kpis.open_recommendations || 0) * 8)
                    )
                  )}
                  label="Readiness"
                />
              </div>
              <div className="kpi-foot">Actions for your team · click to open</div>
            </Link>
          </div>

          <EdrMetricsStrip metrics={edrMetrics} loading={edrLoading} />

          <SocEfficiencyStrip
            openIncidents={data.kpis.open_incidents}
            highCritical={data.kpis.high_critical_alerts}
            onlineAppliances={data.kpis.appliances_online}
            offlineAppliances={data.kpis.appliances_other}
            collectorsHref="/assets"
            queueHref="/incidents"
          />

          <div className="analytics-row analytics-row--trio" data-testid="customer-analytics-row">
            <Link
              className="timeline-panel-link"
              to="/incidents"
              aria-label="Open incidents"
              data-testid="widget-timeline"
            >
              <TimelineChart
                buckets={hasStacked ? stackedBuckets : buckets}
                title="Incidents over time (24h)"
                stacked={hasStacked}
              />
            </Link>
            <div data-testid="widget-severity-donut">
              <SeverityDonut
                slices={severitySlices}
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
                title="Activity heatmap"
                liveTick={liveTick}
                footnote="Aggregated overlay for your package — never raw IP locations."
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
