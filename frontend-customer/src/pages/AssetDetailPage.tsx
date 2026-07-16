import { Link, useParams } from "react-router-dom";
import { getCustomerAssetDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function AssetDetailPage() {
  const { user } = useAuth();
  const { assetId } = useParams<{ assetId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerAssetDetail(shortCode as string, assetId as string),
    Boolean(shortCode && assetId),
    [shortCode, assetId]
  );

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Protected asset</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so asset detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!assetId) {
    return (
      <div>
        <h1 className="page-title">Protected asset</h1>
        <div className="state-message state-error">Asset id is missing from the URL.</div>
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
      <h1 className="page-title">Protected asset</h1>
      <p className="page-subtitle">Read-only detail for this protected asset.</p>

      {status === "loading" && <div className="state-message">Loading asset...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Asset was not found."}</div>
      )}

      {status === "success" && data && (
        <table className="data-table">
          <tbody>
            <tr>
              <th>Hostname</th>
              <td>{data.asset.hostname ?? "—"}</td>
            </tr>
            <tr>
              <th>Type</th>
              <td>{data.asset.asset_type}</td>
            </tr>
            <tr>
              <th>Criticality</th>
              <td>
                <span className={`badge badge-${data.asset.criticality}`}>{data.asset.criticality}</span>
              </td>
            </tr>
            <tr>
              <th>Status</th>
              <td>{data.asset.status}</td>
            </tr>
            <tr>
              <th>OS</th>
              <td>{data.asset.os_name ?? "—"}</td>
            </tr>
            <tr>
              <th>Owner</th>
              <td>{data.asset.owner ?? "—"}</td>
            </tr>
            <tr>
              <th>Appliance</th>
              <td>{data.asset.appliance_name ?? "—"}</td>
            </tr>
            <tr>
              <th>Site</th>
              <td>{data.asset.site_name ?? "—"}</td>
            </tr>
            <tr>
              <th>Last seen</th>
              <td>{data.asset.last_seen_at ?? "—"}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}
