import { Link, useParams } from "react-router-dom";
import { getCustomerAlertDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function AlertDetailPage() {
  const { user } = useAuth();
  const { alertId } = useParams<{ alertId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerAlertDetail(shortCode as string, alertId as string),
    Boolean(shortCode && alertId),
    [shortCode, alertId]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Alert</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so alert detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!alertId) {
    return (
      <div>
        <h1 className="page-title">Alert</h1>
        <div className="state-message state-error">Alert id is missing from the URL.</div>
        <p>
          <Link to="/alerts">Back to alerts</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <p>
        <Link to="/alerts">← Back to alerts</Link>
      </p>
      <h1 className="page-title">Alert</h1>
      <p className="page-subtitle">Read-only customer-visible detail for this alert.</p>

      {status === "loading" && <div className="state-message">Loading alert...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Alert was not found."}</div>
      )}

      {status === "success" && data && (
        <>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Title</th>
                <td>{data.alert.title}</td>
              </tr>
              <tr>
                <th>Severity</th>
                <td>
                  <span className={`badge badge-${data.alert.severity}`}>{data.alert.severity}</span>
                </td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{data.alert.status}</td>
              </tr>
              <tr>
                <th>Detection</th>
                <td>{data.alert.source}</td>
              </tr>
              <tr>
                <th>Summary</th>
                <td>{data.alert.summary ?? "—"}</td>
              </tr>
              <tr>
                <th>Description</th>
                <td>{data.alert.description ?? "—"}</td>
              </tr>
              <tr>
                <th>Hostname</th>
                <td>{data.alert.hostname ?? "—"}</td>
              </tr>
              <tr>
                <th>Device type</th>
                <td>{data.alert.device_type ?? "—"}</td>
              </tr>
              <tr>
                <th>Asset category</th>
                <td>{data.alert.asset_category_label ?? data.alert.asset_category ?? "—"}</td>
              </tr>
              <tr>
                <th>Criticality</th>
                <td>{data.alert.criticality ?? "—"}</td>
              </tr>
              <tr>
                <th>Operating system</th>
                <td>{data.alert.operating_system ?? "—"}</td>
              </tr>
              <tr>
                <th>Detected</th>
                <td>{data.alert.detected_at ?? "—"}</td>
              </tr>
            </tbody>
          </table>

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            What this means
          </h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Business impact</th>
                <td>{data.alert.business_impact ?? "—"}</td>
              </tr>
              <tr>
                <th>Recommended action</th>
                <td>{data.alert.recommended_action ?? "—"}</td>
              </tr>
              <tr>
                <th>Likely attack type</th>
                <td>{data.alert.likely_attack_type ?? "—"}</td>
              </tr>
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
