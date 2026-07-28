import { Link, useParams } from "react-router-dom";
import { getCustomerIncidentDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function IncidentDetailPage() {
  const { user } = useAuth();
  const { incidentNumber } = useParams<{ incidentNumber: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerIncidentDetail(shortCode as string, incidentNumber as string),
    Boolean(shortCode && incidentNumber),
    [shortCode, incidentNumber]
  );

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
                  <span className={`badge badge-${data.incident.severity}`}>
                    {data.incident.severity}
                  </span>
                </td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{data.incident.status}</td>
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
                      <span className={`badge badge-${alert.severity}`}>{alert.severity}</span>
                    </td>
                    <td>{alert.status}</td>
                    <td>{alert.source}</td>
                    <td>{alert.summary ?? alert.description ?? "—"}</td>
                    <td>{alert.hostname ?? "—"}</td>
                    <td>{alert.detected_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
