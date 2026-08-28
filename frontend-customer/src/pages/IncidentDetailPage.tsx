import { Link, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { getCustomerIncidentDetail } from "../api/customer";
import { getEdrDeepDive, type EdrDeepDive } from "../api/edr";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";
import EdrControlPanel from "../components/edr/EdrControlPanel";
import MitreBadges from "../components/edr/MitreBadges";
import ProcessTreeWidget from "../components/edr/ProcessTreeWidget";
import AiExecutiveSummary from "../components/AiExecutiveSummary";
import FilterValueLink from "../components/soc/FilterValueLink";
import SeverityPill from "../components/SeverityPill";
import { alertStatusLabel } from "../lib/alertStatusLabels";

export default function IncidentDetailPage() {
  const { user } = useAuth();
  const { incidentNumber } = useParams<{ incidentNumber: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerIncidentDetail(shortCode as string, incidentNumber as string),
    Boolean(shortCode && incidentNumber),
    [shortCode, incidentNumber]
  );
  const [edr, setEdr] = useState<EdrDeepDive | null>(null);
  const canExecute = user?.role === "customer_admin";

  useEffect(() => {
    if (!shortCode || !incidentNumber || status !== "success") return;
    getEdrDeepDive(incidentNumber, shortCode)
      .then(setEdr)
      .catch(() => setEdr(null));
  }, [shortCode, incidentNumber, status]);

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Incident</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so incident detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!incidentNumber) {
    return (
      <div>
        <h1 className="page-title">Incident</h1>
        <div className="state-message state-error">Incident number is missing from the URL.</div>
        <p>
          <Link to="/incidents">Back to incidents</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <p>
        <Link to="/incidents">← Back to incidents</Link>
      </p>
      <h1 className="page-title">Incident {incidentNumber}</h1>
      <p className="page-subtitle">Read-only customer-visible detail for this incident.</p>

      {status === "loading" && <div className="state-message">Loading incident...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Incident was not found."}</div>
      )}

      {status === "success" && data && (
        <>
          <AiExecutiveSummary
            whatHappened={data.incident.customer_visible_summary}
            businessImpact={data.incident.business_impact}
            actionTaken={
              data.incident.resolution_summary ||
              (typeof data.incident.customer_action_required === "string"
                ? data.incident.customer_action_required
                : data.primary_alert?.recommended_action) ||
              null
            }
          />

          <table className="data-table">
            <tbody>
              <tr>
                <th>Incident</th>
                <td>{data.incident.incident_number}</td>
              </tr>
              <tr>
                <th>Title</th>
                <td>{data.incident.title}</td>
              </tr>
              <tr>
                <th>Severity</th>
                <td>
                  <SeverityPill value={data.incident.severity} filterBase="/incidents" />
                </td>
              </tr>
              <tr>
                <th>Status</th>
                <td>
                  <SeverityPill value={data.incident.status} kind="status" filterBase="/incidents" />
                </td>
              </tr>
              <tr>
                <th>Summary</th>
                <td>{data.incident.customer_visible_summary ?? "—"}</td>
              </tr>
              <tr>
                <th>Business impact</th>
                <td>{data.incident.business_impact ?? "—"}</td>
              </tr>
              <tr>
                <th>Action required</th>
                <td>
                  {data.incident.customer_action_required === null ||
                  data.incident.customer_action_required === undefined
                    ? "—"
                    : String(data.incident.customer_action_required)}
                </td>
              </tr>
              <tr>
                <th>Resolution</th>
                <td>{data.incident.resolution_summary ?? "—"}</td>
              </tr>
              <tr>
                <th>Opened</th>
                <td>{data.incident.opened_at ?? "—"}</td>
              </tr>
              <tr>
                <th>Resolved</th>
                <td>{data.incident.resolved_at ?? "—"}</td>
              </tr>
              <tr>
                <th>Closed</th>
                <td>{data.incident.closed_at ?? "—"}</td>
              </tr>
            </tbody>
          </table>

          {data.primary_alert ? (
            <>
              <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
                Affected asset
              </h2>
              <table className="data-table">
                <tbody>
                  <tr>
                    <th>Hostname</th>
                    <td>
                      <FilterValueLink
                        base="/incidents"
                        param="hostname"
                        value={data.primary_alert.hostname}
                      />
                    </td>
                  </tr>
                  <tr>
                    <th>Device type</th>
                    <td>{data.primary_alert.device_type ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Asset category</th>
                    <td>
                      {data.primary_alert.asset_category_label ??
                        data.primary_alert.asset_category ??
                        "—"}
                    </td>
                  </tr>
                  <tr>
                    <th>Criticality</th>
                    <td>{data.primary_alert.criticality ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Operating system</th>
                    <td>{data.primary_alert.operating_system ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Recommended action</th>
                    <td>{data.primary_alert.recommended_action ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Detection rule</th>
                    <td>
                      {data.primary_alert.wazuh_rule_id ? (
                        <>
                          <FilterValueLink
                            base="/alerts"
                            param="rule_id"
                            value={data.primary_alert.wazuh_rule_id}
                          />
                          {data.primary_alert.wazuh_rule_level
                            ? ` (level ${data.primary_alert.wazuh_rule_level})`
                            : null}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>

              <h2 className="page-subtitle" style={{ marginTop: "1.5rem" }}>
                Primary alert evidence
              </h2>
              <table className="data-table">
                <tbody>
                  <tr>
                    <th>File path</th>
                    <td>
                      <FilterValueLink
                        base="/alerts"
                        param="path"
                        value={data.primary_alert.file_path}
                      />
                    </td>
                  </tr>
                  <tr>
                    <th>File name</th>
                    <td>{data.primary_alert.file_name ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Process</th>
                    <td>
                      <FilterValueLink
                        base="/alerts"
                        param="process"
                        value={data.primary_alert.process_name}
                      />
                    </td>
                  </tr>
                  <tr>
                    <th>Parent process</th>
                    <td>{data.primary_alert.parent_process_name ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Command line</th>
                    <td>{data.primary_alert.command_line ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>SHA256</th>
                    <td>{data.primary_alert.hash_sha256 ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>MD5</th>
                    <td>{data.primary_alert.hash_md5 ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>MITRE</th>
                    <td>
                      {[
                        ...(data.primary_alert.mitre_tactics ?? []),
                        ...(data.primary_alert.mitre_techniques ?? []),
                      ].length
                        ? [
                            ...(data.primary_alert.mitre_tactics ?? []),
                            ...(data.primary_alert.mitre_techniques ?? []),
                          ].join(", ")
                        : "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </>
          ) : null}

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            Timeline
          </h2>
          {data.timeline.length === 0 ? (
            <div className="state-message">No customer-visible timeline updates yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Type</th>
                  <th>Title</th>
                </tr>
              </thead>
              <tbody>
                {data.timeline.map((event, index) => (
                  <tr key={`${event.event_type}-${event.created_at ?? "t"}-${index}`}>
                    <td>{event.created_at ?? "—"}</td>
                    <td>{event.event_type}</td>
                    <td>{event.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            Related alerts
          </h2>
          {data.related_alerts.length === 0 ? (
            <div className="state-message">No customer-visible related alerts for this incident.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Detection</th>
                  <th>Device</th>
                  <th>Summary</th>
                  <th>Hostname</th>
                  <th>Detected</th>
                </tr>
              </thead>
              <tbody>
                {data.related_alerts.map((alert) => (
                  <tr key={alert.alert_id}>
                    <td>{alert.title}</td>
                    <td>
                      <SeverityPill value={alert.severity} filterBase="/alerts" />
                    </td>
                    <td>{alertStatusLabel(alert.status)}</td>
                    <td>{alert.source}</td>
                    <td>{alert.device_type ?? "—"}</td>
                    <td>{alert.summary ?? alert.description ?? "—"}</td>
                    <td>{alert.hostname ?? "—"}</td>
                    <td>{alert.detected_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {edr ? (
            <>
              <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
                Endpoint context
              </h2>
              <table className="data-table">
                <tbody>
                  <tr>
                    <th>Hostname</th>
                    <td>{String(edr.endpoint.hostname ?? "—")}</td>
                  </tr>
                  <tr>
                    <th>OS</th>
                    <td>{String(edr.endpoint.os_version ?? "—")}</td>
                  </tr>
                </tbody>
              </table>
              <h2 className="page-subtitle" style={{ marginTop: "1.5rem" }}>
                MITRE ATT&amp;CK
              </h2>
              <MitreBadges tactics={edr.mitre.tactics} techniques={edr.mitre.techniques} />

              <details className="forensic-accordion card-surface">
                <summary>Technical Forensic Details (EDR Execution Tree)</summary>
                <div className="forensic-accordion-body">
                  <p className="muted" style={{ marginTop: 0 }}>
                    Optional technical detail for your security contacts. Leaders can stay with the
                    AI Executive Summary above — Kevantic SOC owns the investigation.
                  </p>
                  <ProcessTreeWidget
                    root={edr.process_tree.root}
                    message={edr.process_tree.message}
                  />
                  {edr.forensic_artifacts && edr.forensic_artifacts.length > 0 ? (
                    <div className="edr-forensics-list" style={{ marginTop: "1rem" }}>
                      <h3 className="page-subtitle">Forensic collections</h3>
                      <ul>
                        {edr.forensic_artifacts.map((a) => (
                          <li key={a.artifact_id}>
                            <span className="muted">{a.status}</span>
                            {a.download_url ? (
                              <>
                                {" — "}
                                <a href={a.download_url} target="_blank" rel="noreferrer">
                                  Download package
                                </a>
                              </>
                            ) : (
                              <span className="muted"> — awaiting upload</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </details>

              <EdrControlPanel
                tenantShortCode={shortCode}
                incidentNumber={incidentNumber}
                agentId={edr.endpoint.agent_id as string | undefined}
                canExecute={canExecute}
                downloadUrl={edr.forensic_artifacts?.find((a) => a.download_url)?.download_url}
              />
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
