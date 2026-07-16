import { Link } from "react-router-dom";
import { getCustomerAssets } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function AssetsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerAssets(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Assets</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so asset posture cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Assets</h1>
      <p className="page-subtitle">
        Read-only appliance posture and protected assets for your organization.
      </p>

      {status === "loading" && <div className="state-message">Loading assets...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        <>
          <h2 className="page-subtitle" style={{ marginTop: "1.5rem" }}>
            Appliances
          </h2>
          {data.appliances.length === 0 ? (
            <div className="state-message">No appliances reported for your organization yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Appliance</th>
                  <th>Site</th>
                  <th>Status</th>
                  <th>Health</th>
                  <th>CPU %</th>
                  <th>Memory %</th>
                  <th>Disk %</th>
                  <th>Agent</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {data.appliances.map((row) => (
                  <tr key={row.appliance_id}>
                    <td>
                      <Link to={`/appliances/${encodeURIComponent(row.appliance_id)}`}>
                        {row.appliance_name}
                      </Link>
                    </td>
                    <td>{row.site_name}</td>
                    <td>
                      <span className={`badge badge-${row.status}`}>{row.status}</span>
                    </td>
                    <td>{row.health_status ?? "Unknown"}</td>
                    <td>{row.cpu_percent ?? "—"}</td>
                    <td>{row.memory_percent ?? "—"}</td>
                    <td>{row.disk_percent ?? "—"}</td>
                    <td>{row.agent_version ?? "—"}</td>
                    <td>{row.last_seen_at ?? "Never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            Protected assets
          </h2>
          {data.assets.length === 0 ? (
            <div className="state-message">No protected assets listed for your organization yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Hostname</th>
                  <th>Type</th>
                  <th>Criticality</th>
                  <th>Status</th>
                  <th>OS</th>
                  <th>Owner</th>
                  <th>Appliance</th>
                  <th>Site</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {data.assets.map((asset) => (
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
                    <td>{asset.os_name ?? "—"}</td>
                    <td>{asset.owner ?? "—"}</td>
                    <td>{asset.appliance_name ?? "—"}</td>
                    <td>{asset.site_name ?? "—"}</td>
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
