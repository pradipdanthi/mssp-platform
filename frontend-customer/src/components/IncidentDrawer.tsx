import { Link } from "react-router-dom";
import SeverityPill from "./SeverityPill";

export type DrawerIncident = {
  id?: string;
  incident_number: string;
  title: string;
  severity: string;
  status: string;
  tenant_name?: string;
  assigned_to?: string | null;
  summary?: string | null;
  business_impact?: string | null;
  customer_action_required?: string | boolean | null;
  opened_at?: string | null;
  affected_entity?: string | null;
  detailPath?: string;
};

type Props = {
  incident: DrawerIncident | null;
  onClose: () => void;
  mode?: "admin" | "customer";
};

/**
 * Customer-safe slide-over — no IPs, no raw JSON, no third-party SOC consoles.
 */
export default function IncidentDrawer({ incident, onClose }: Props) {
  if (!incident) return null;

  const actionRequired =
    typeof incident.customer_action_required === "boolean"
      ? incident.customer_action_required
        ? "Yes"
        : "No"
      : incident.customer_action_required || "—";

  return (
    <div className="incident-drawer-root" role="dialog" aria-modal="true" aria-label="Incident details">
      <button type="button" className="incident-drawer-backdrop" aria-label="Close" onClick={onClose} />
      <aside className="incident-drawer panel-surface">
        <header className="incident-drawer-header">
          <div>
            <div className="incident-drawer-kicker">Incident</div>
            <h2 className="incident-drawer-title cell-mono">{incident.incident_number}</h2>
          </div>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="incident-drawer-pills">
          <SeverityPill value={incident.severity} filterBase="/alerts" />
          <SeverityPill value={incident.status} kind="status" filterBase="/incidents" />
        </div>

        <h3 className="incident-drawer-name">{incident.title}</h3>

        <dl className="incident-drawer-dl">
          <dt>Opened</dt>
          <dd className="cell-mono">{incident.opened_at ?? "—"}</dd>
          <dt>Business impact</dt>
          <dd>{incident.business_impact ?? "—"}</dd>
          <dt>Summary</dt>
          <dd className="drawer-summary">{incident.summary ?? "—"}</dd>
          <dt>Action required</dt>
          <dd>{actionRequired}</dd>
        </dl>

        <div className="incident-drawer-actions">
          {incident.detailPath ? (
            <Link className="btn btn-primary" to={incident.detailPath} onClick={onClose}>
              View details
            </Link>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
