import { Link } from "react-router-dom";
import type { EdrMetricsSummary } from "../../api/edr";

type Props = {
  metrics: EdrMetricsSummary | null;
  loading?: boolean;
  /** Admin vs customer destination for “isolated endpoints”. */
  isolatedHref?: string;
  telemetryHref?: string;
};

function fmtMttc(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

/**
 * Compact EDR/MXDR strip on the main dashboard.
 * These are service-level counters (containment speed, telemetry volume, hosts
 * currently marked isolated) — not a separate product page. Drill-down goes to
 * Incidents (where isolate/unisolate lives) and Alerts (telemetry).
 */
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
          EDR / MXDR service metrics
        </h2>
        <p className="page-subtitle" style={{ margin: "0.25rem 0 0" }}>
          Endpoint detection &amp; response health for this view. Isolate / un-isolate and process
          actions run from an <strong>incident</strong> (select a row below or open Incidents).
          These tiles are summary counters — not a separate console.
        </p>
      </div>
      {loading ? (
        <p className="muted">Loading EDR metrics…</p>
      ) : (
        <div className="kpi-row-3 edr-metrics-kpis">
          <div className="kpi-card card-surface">
            <span className="kpi-label">Mean time to contain</span>
            <div className="kpi-value kpi-value--accent">
              {fmtMttc(metrics?.mean_time_to_contain_seconds)}
            </div>
            <div className="kpi-foot">Avg. isolate dispatch → verified (when available)</div>
          </div>
          <Link
            className="kpi-card card-surface kpi-card--link"
            to={telemetryHref}
            aria-label="Open alerts for EDR telemetry"
          >
            <span className="kpi-label">EDR telemetry rate</span>
            <div className="kpi-value">
              {(metrics?.telemetry_events_processed ?? 0).toLocaleString()}
            </div>
            <div className="kpi-foot">Processed endpoint events · click → alerts</div>
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
            <div className="kpi-foot">Hosts in quarantine · click → incidents</div>
          </Link>
        </div>
      )}
      <p style={{ marginTop: "0.75rem" }}>
        <Link className="btn btn-ghost" to="/incidents">
          Open incidents (containment actions) →
        </Link>
      </p>
    </section>
  );
}
