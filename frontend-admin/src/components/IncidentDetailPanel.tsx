import { Link } from "react-router-dom";
import type { DrawerIncident } from "./IncidentDrawer";
import InvestigationGraph from "./InvestigationGraph";
import SeverityPill from "./SeverityPill";

type Props = {
  incident: DrawerIncident | null;
  mode?: "admin" | "customer";
  onRunPlaybook?: () => void;
};

/**
 * Inline selected-incident panel (Sentinel-style bottom-right):
 * details + entity graph + quick actions.
 */
export default function IncidentDetailPanel({
  incident,
  mode = "admin",
  onRunPlaybook,
}: Props) {
  if (!incident) {
    return (
      <aside className="incident-detail-panel card-surface">
        <div className="incident-detail-empty">
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Incident details
          </h2>
          <p className="page-subtitle">
            Select a row from the incidents list to inspect entities and run quick actions.
          </p>
          <InvestigationGraph title="Entity mapping (idle)" />
        </div>
      </aside>
    );
  }

  const host =
    incident.affected_entity && incident.affected_entity !== "Pending enrichment"
      ? incident.affected_entity
      : mode === "admin"
        ? "host-pending"
        : "Protected asset";
  const ipLabel =
    mode === "admin" && incident.source_ip
      ? incident.source_ip
      : mode === "admin"
        ? "—"
        : "Hidden (customer-safe)";

  return (
    <aside className="incident-detail-panel card-surface" aria-label="Selected incident details">
      <div className="incident-detail-top">
        <div className="incident-detail-kicker">Selected incident</div>
        <div className="incident-detail-id cell-mono text-cyan">{incident.incident_number}</div>
        <h3 className="incident-detail-title">{incident.title}</h3>
        <div className="incident-drawer-pills">
          <SeverityPill value={incident.severity} filterBase="/alerts" />
          <SeverityPill value={incident.status} kind="status" filterBase="/incidents" />
        </div>
        <dl className="incident-drawer-dl">
          {incident.tenant_name ? (
            <>
              <dt>Tenant</dt>
              <dd>{incident.tenant_name}</dd>
            </>
          ) : null}
          <dt>Affected host</dt>
          <dd className="cell-mono">{host}</dd>
          <dt>{mode === "admin" ? "Source IP" : "Network"}</dt>
          <dd className="cell-mono text-cyan">{ipLabel}</dd>
          <dt>Assignee</dt>
          <dd>{incident.assigned_to ?? "Unassigned"}</dd>
          <dt>Created</dt>
          <dd className="cell-mono">{incident.opened_at ?? "—"}</dd>
          <dt>Summary</dt>
          <dd className="drawer-summary">{incident.summary ?? "—"}</dd>
        </dl>
      </div>

      <InvestigationGraph
        title="Entity mapping"
        entities={[
          { id: "user", label: "User", kind: "user" },
          { id: "host", label: "Host", kind: "host" },
          { id: "proc", label: "Process", kind: "process" },
          { id: "ip", label: mode === "admin" ? "IP" : "Net", kind: "network" },
        ]}
      />

      <div className="incident-detail-actions">
        {mode === "admin" ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              if (onRunPlaybook) onRunPlaybook();
              else
                window.alert(
                  "Playbook run queued for security automation. Execution status appears in the incident timeline when the SOAR workflow acknowledges the request."
                );
            }}
          >
            Run Playbook
          </button>
        ) : null}
        {incident.detailPath ? (
          <Link className="btn btn-ghost" to={incident.detailPath}>
            Investigate
          </Link>
        ) : (
          <Link className="btn btn-ghost" to="/incidents">
            Investigate
          </Link>
        )}
      </div>
    </aside>
  );
}
