import { Link, useParams } from "react-router-dom";
import { getCustomerApplianceDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function ApplianceDetailPage() {
  const { user } = useAuth();
  const { applianceId } = useParams<{ applianceId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerApplianceDetail(shortCode as string, applianceId as string),
    Boolean(shortCode && applianceId),
    [shortCode, applianceId]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Appliance</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so appliance detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!applianceId) {
    return (
      <div>
        <h1 className="page-title">Appliance</h1>
        <div className="state-message state-error">Appliance id is missing from the URL.</div>
        <p>
          <Link to="/assets">Back to assets</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <p>
        <Link to="/assets">← Back to assets</Link>
      </p>
      <h1 className="page-title">Appliance</h1>
      <p className="page-subtitle">Read-only posture detail for this security appliance.</p>

      {status === "loading" && <div className="state-message">Loading appliance...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Appliance was not found."}</div>
      )}

      {status === "success" && data && (
        <>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Appliance</th>
                <td>{data.appliance.appliance_name}</td>
              </tr>
              <tr>
                <th>Site</th>
                <td>{data.appliance.site_name}</td>
              </tr>
              <tr>
                <th>Status</th>
                <td>
                  <span className={`badge badge-${data.appliance.status}`}>{data.appliance.status}</span>
                </td>
              </tr>
              <tr>
                <th>Health</th>
                <td>{data.appliance.health_status ?? "Unknown"}</td>
              </tr>
              <tr>
                <th>CPU %</th>
                <td>{data.appliance.cpu_percent ?? "—"}</td>
              </tr>
              <tr>
                <th>Memory %</th>
                <td>{data.appliance.memory_percent ?? "—"}</td>
              </tr>
              <tr>
                <th>Disk %</th>
                <td>{data.appliance.disk_percent ?? "—"}</td>
              </tr>
              <tr>
                <th>Agent version</th>
                <td>{data.appliance.agent_version ?? "—"}</td>
              </tr>
              <tr>
                <th>Config version</th>
                <td>{data.appliance.config_version ?? "—"}</td>
              </tr>
              <tr>
                <th>Update status</th>
                <td>{data.appliance.update_status ?? "—"}</td>
              </tr>
              <tr>
                <th>Last seen</th>
                <td>{data.appliance.last_seen_at ?? "Never"}</td>
              </tr>
              <tr>
                <th>Latest heartbeat</th>
                <td>{data.appliance.latest_heartbeat_at ?? "—"}</td>
              </tr>
              <tr>
                <th>Protected assets</th>
                <td>{data.appliance.protected_assets_count}</td>
              </tr>
            </tbody>
          </table>

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            Protected assets on this appliance
          </h2>
          {data.appliance.protected_assets.length === 0 ? (
            <div className="state-message">No protected assets are linked to this appliance yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Hostname</th>
                  <th>Type</th>
                  <th>Criticality</th>
                  <th>Status</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {data.appliance.protected_assets.map((asset) => (
                  <tr key={asset.asset_id}>
                    <td>
                      <Link to={`/assets/${encodeURIComponent(asset.asset_id)}`}>
                        {asset.hostname ?? "—"}
                      </Link>
                    </td>
                    <td>{asset.asset_type}</td>
                    <td>
                      <span className={`badge badge-${asset.criticality}`}>{asset.criticality}</span>
                    </td>
                    <td>{asset.status}</td>
                    <td>{asset.last_seen_at ?? "—"}</td>
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
