import { Link } from "react-router-dom";
import type { EdrMetricsSummary } from "../../api/edr";

type Props = {
  metrics: EdrMetricsSummary | null;
  loading?: boolean;
  isolatedHref?: string;
  telemetryHref?: string;
};

function fmtMttc(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export default function EdrMetricsStrip({
  metrics,
  loading,
  isolatedHref = "/incidents",
  telemetryHref = "/alerts",
}: Props) {
  return (
    <section className="edr-metrics-strip card-surface" id="edr-mxdr" aria-label="EDR MXDR metrics">
      <div className="edr-metrics-strip-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Endpoint response metrics
        </h2>
        <Link className="edr-metrics-open-link" to="/incidents">
          Open incidents →
        </Link>
      </div>
      {loading ? (
        <p className="muted" style={{ margin: "0.35rem 0 0" }}>
          Loading EDR metrics…
        </p>
      ) : (
        <div className="kpi-row-3 edr-metrics-kpis">
          <div className="kpi-card card-surface">
            <span className="kpi-label">Mean time to contain</span>
            <div className="kpi-value kpi-value--accent">
              {fmtMttc(metrics?.mean_time_to_contain_seconds)}
            </div>
            <div className="kpi-foot">Average containment speed</div>
          </div>
          <Link
            className="kpi-card card-surface kpi-card--link"
            to={telemetryHref}
            aria-label="Open alerts for EDR telemetry"
          >
            <span className="kpi-label">Endpoint activity</span>
            <div className="kpi-value">
              {(metrics?.telemetry_events_processed ?? 0).toLocaleString()}
            </div>
            <div className="kpi-foot">Monitored events · alerts</div>
          </Link>
          <Link
            className="kpi-card card-surface kpi-card--link"
            to={isolatedHref}
            aria-label="Open incidents for isolated endpoints"
          >
            <span className="kpi-label">Isolated endpoints</span>
            <div className="kpi-value kpi-value--critical">
              {metrics?.isolated_endpoints_count ?? 0}
            </div>
            <div className="kpi-foot">In quarantine · incidents</div>
          </Link>
        </div>
      )}
    </section>
  );
}
