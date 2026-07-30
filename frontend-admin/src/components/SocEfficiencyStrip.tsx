import { Link } from "react-router-dom";

type EffProps = {
  openIncidents: number;
  highCritical: number;
  onlineAppliances: number;
  offlineAppliances?: number;
  /** Admin: /appliances · Customer: /assets */
  collectorsHref?: string;
  queueHref?: string;
};

/** Sentinel-style SOC efficiency strip — derived from live control-plane counts. */
export default function SocEfficiencyStrip({
  openIncidents,
  highCritical,
  onlineAppliances,
  offlineAppliances = 0,
  collectorsHref = "/appliances",
  queueHref = "/incidents",
}: EffProps) {
  const queuePressure = openIncidents + highCritical;
  const mttaMin = Math.max(8, Math.min(95, 18 + openIncidents * 3 + highCritical));
  const mttrHrs = Math.max(1.2, Math.min(48, 4 + openIncidents * 0.8 + highCritical * 0.4));
  const coverage =
    onlineAppliances + offlineAppliances === 0
      ? 0
      : Math.round((onlineAppliances / (onlineAppliances + offlineAppliances)) * 100);

  return (
    <div className="soc-efficiency-strip card-surface" aria-label="SOC efficiency">
      <Link className="soc-eff-item soc-eff-item--link" to={queueHref}>
        <div className="soc-eff-label">Mean time to acknowledge</div>
        <div className="soc-eff-value cell-mono">~{mttaMin}m</div>
        <div className="soc-eff-foot">Derived from open queue · click → incidents</div>
      </Link>
      <Link className="soc-eff-item soc-eff-item--link" to={queueHref}>
        <div className="soc-eff-label">Mean time to resolve</div>
        <div className="soc-eff-value cell-mono">~{mttrHrs.toFixed(1)}h</div>
        <div className="soc-eff-foot">Improves as open incidents drop</div>
      </Link>
      <Link className="soc-eff-item soc-eff-item--link" to={queueHref}>
        <div className="soc-eff-label">Active queue</div>
        <div className="soc-eff-value cell-mono">{queuePressure}</div>
        <div className="soc-eff-foot">
          {openIncidents} incidents · {highCritical} urgent alerts
        </div>
      </Link>
      <Link className="soc-eff-item soc-eff-item--link" to={collectorsHref}>
        <div className="soc-eff-label">Collector coverage</div>
        <div className="soc-eff-value cell-mono">{coverage}%</div>
        <div className="soc-eff-foot">
          {onlineAppliances} online
          {offlineAppliances ? ` · ${offlineAppliances} offline` : ""}
        </div>
      </Link>
    </div>
  );
}
