import { Link } from "react-router-dom";
import type { EdrMetricsSummary } from "../../api/edr";

type Props = {
  metrics: EdrMetricsSummary | null;
  loading?: boolean;
  incidentsLink?: string;
};

function fmtMttc(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export default function EdrMetricsStrip({ metrics, loading, incidentsLink = "/incidents" }: Props) {
  return (
    <section className="edr-metrics-strip card-surface" id="edr-mxdr" aria-label="Endpoint detection and response metrics">
      <div className="edr-metrics-strip-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          EDR / MXDR operations
        </h2>
        <p className="page-subtitle" style={{ margin: "0.25rem 0 0" }}>
          Co-managed endpoint response — open an incident for process tree and containment actions.
        </p>
      </div>
      {loading ? (
        <p className="muted">Loading EDR metrics…</p>
      ) : (
        <div className="kpi-row-3 edr-metrics-kpis">
          <div className="kpi-card card-surface">
            <span className="kpi-label">Mean time to contain</span>
            <div className="kpi-value kpi-value--accent">{fmtMttc(metrics?.mean_time_to_contain_seconds)}</div>
            <div className="kpi-foot">Alert → host isolation (avg)</div>
          </div>
          <div className="kpi-card card-surface">
            <span className="kpi-label">Telemetry processed</span>
            <div className="kpi-value">{(metrics?.telemetry_events_processed ?? 0).toLocaleString()}</div>
            <div className="kpi-foot">Sysmon / Osquery events (today rollup)</div>
          </div>
          <div className="kpi-card card-surface">
            <span className="kpi-label">Isolated endpoints</span>
            <div className="kpi-value kpi-value--critical">{metrics?.isolated_endpoints_count ?? 0}</div>
            <div className="kpi-foot">Currently quarantined</div>
          </div>
        </div>
      )}
      <p style={{ marginTop: "0.75rem" }}>
        <Link className="btn btn-ghost" to={incidentsLink}>
          View incidents with EDR deep dive →
        </Link>
      </p>
    </section>
  );
}
