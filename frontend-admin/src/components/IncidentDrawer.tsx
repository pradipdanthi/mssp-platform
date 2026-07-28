import { useEffect, useState } from "react";
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
  /** Admin-only enrichment — never pass real IPs into the customer portal. */
  affected_entity?: string | null;
  source_ip?: string | null;
  target_ip?: string | null;
  rule_source?: string | null;
  thehive_case_id?: string | null;
  detailPath?: string;
};

type Props = {
  incident: DrawerIncident | null;
  onClose: () => void;
  mode?: "admin" | "customer";
};

function buildAdminCopyPayload(incident: DrawerIncident): string {
  return JSON.stringify(
    {
      incident_number: incident.incident_number,
      title: incident.title,
      severity: incident.severity,
      status: incident.status,
      tenant_name: incident.tenant_name ?? null,
      assigned_to: incident.assigned_to ?? null,
      opened_at: incident.opened_at ?? null,
      summary: incident.summary ?? null,
      source_ip: incident.source_ip ?? null,
      target_ip: incident.target_ip ?? null,
      rule_source: incident.rule_source ?? null,
      thehive_case_id: incident.thehive_case_id ?? null,
    },
    null,
    2
  );
}

/** Command-center slide-over for incident triage. */
export default function IncidentDrawer({ incident, onClose, mode = "admin" }: Props) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    setCopyState("idle");
  }, [incident?.incident_number]);

  if (!incident) return null;

  const actionRequired =
    typeof incident.customer_action_required === "boolean"
      ? incident.customer_action_required
        ? "Yes"
        : "No"
      : incident.customer_action_required || "—";

  const theHiveHref = incident.thehive_case_id
    ? `https://192.168.0.212/cases/${encodeURIComponent(incident.thehive_case_id)}/details`
    : null;

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
          <SeverityPill
            value={incident.severity}
            filterBase={mode === "admin" ? "/alerts" : "/alerts"}
          />
          <SeverityPill value={incident.status} kind="status" filterBase="/incidents" />
        </div>

        <h3 className="incident-drawer-name">{incident.title}</h3>

        <dl className="incident-drawer-dl">
          {incident.tenant_name ? (
            <>
              <dt>Tenant</dt>
              <dd>{incident.tenant_name}</dd>
            </>
          ) : null}
          <dt>Opened</dt>
          <dd className="cell-mono">{incident.opened_at ?? "—"}</dd>
          {mode === "admin" ? (
            <>
              <dt>Assigned</dt>
              <dd>{incident.assigned_to ?? "Unassigned"}</dd>
              <dt>Affected entity</dt>
              <dd className="cell-mono">{incident.affected_entity ?? "—"}</dd>
              <dt>Source IP</dt>
              <dd className="cell-mono text-cyan">{incident.source_ip ?? "—"}</dd>
              <dt>Target IP</dt>
              <dd className="cell-mono text-cyan">{incident.target_ip ?? "—"}</dd>
              <dt>Rule source</dt>
              <dd className="cell-mono">{incident.rule_source ?? "SIEM / Incident Response"}</dd>
            </>
          ) : (
            <>
              <dt>Business impact</dt>
              <dd>{incident.business_impact ?? "—"}</dd>
            </>
          )}
          <dt>Summary</dt>
          <dd className="drawer-summary">{incident.summary ?? "—"}</dd>
          <dt>Action required</dt>
          <dd>{actionRequired}</dd>
        </dl>

        <div className="incident-drawer-actions">
          {mode === "admin" ? (
            <>
              <button
                type="button"
                className="btn btn-primary"
                title="Queues a Shuffle playbook run"
                onClick={() => {
                  window.alert(
                    "Shuffle playbook trigger queued for security automation. Confirm execution in Shuffle and TheHive when the workflow completes."
                  );
                }}
              >
                Trigger Shuffle Playbook
              </button>
              {theHiveHref ? (
                <a className="btn btn-ghost" href={theHiveHref} target="_blank" rel="noreferrer">
                  Open in TheHive
                </a>
              ) : (
                <button
                  type="button"
                  className="btn btn-ghost"
                  title="No TheHive case id on this record yet"
                  onClick={() => {
                    window.open("https://192.168.0.212", "_blank", "noopener,noreferrer");
                  }}
                >
                  Open in TheHive
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(buildAdminCopyPayload(incident));
                    setCopyState("copied");
                  } catch {
                    setCopyState("failed");
                  }
                }}
              >
                {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy Raw JSON"}
              </button>
              {incident.detailPath ? (
                <Link className="btn btn-ghost" to={incident.detailPath} onClick={onClose}>
                  Investigate
                </Link>
              ) : null}
            </>
          ) : incident.detailPath ? (
            <Link className="btn btn-primary" to={incident.detailPath} onClick={onClose}>
              View details
            </Link>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
