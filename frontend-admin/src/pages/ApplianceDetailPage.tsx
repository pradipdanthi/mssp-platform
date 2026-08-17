import { Link, useParams } from "react-router-dom";
import {
  ApplianceHealthCell,
  ApplianceHeartbeatCell,
  ApplianceServicesCell,
  ApplianceVersionCell,
} from "../components/appliance/ApplianceFleetCells";
import SeverityPill from "../components/SeverityPill";
import { getApplianceDetail, type Appliance } from "../api/admin";
import { useAdminQuery } from "../hooks/useAdminQuery";

function ApplianceAgentsCell({ reporting, total }: { reporting: number; total: number }) {
  if (total <= 0) {
    return <span className="appliance-agents-cell appliance-agents-cell--empty">0 / 0</span>;
  }
  const allReporting = reporting >= total;
  return (
    <span
      className={`appliance-agents-cell${allReporting ? "" : " appliance-agents-cell--partial"}`}
      title={`${reporting} reporting · ${total} enrolled`}
    >
      {reporting} active / {total}
    </span>
  );
}

export default function ApplianceDetailPage() {
  const { applianceId } = useParams<{ applianceId: string }>();
  const { status, data, errorMessage } = useAdminQuery(
    () => getApplianceDetail(applianceId as string),
    [applianceId]
  );

  if (!applianceId) {
    return (
      <div>
        <h1 className="page-title">Appliance</h1>
        <div className="state-message state-error">Appliance id is missing from the URL.</div>
        <p>
          <Link to="/appliances">Back to appliances</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <p>
        <Link to="/appliances">← Back to appliances</Link>
      </p>
      <h1 className="page-title">Appliance detail</h1>
      <p className="page-subtitle">Fleet posture, entitlements, and resource health for this edge appliance.</p>

      {status === "loading" && <div className="state-message">Loading appliance...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this appliance view.</div>
      )}
      {status === "error" && (
        <div className="state-message state-error">{errorMessage ?? "Appliance was not found."}</div>
      )}

      {status === "success" && data && (
        <>
          {(() => {
            const fleetRow: Appliance = {
              ...data,
              heartbeat_at: data.latest_heartbeat_at ?? null,
              health_status: data.latest_health_status ?? null,
              agents_total: data.protected_assets,
            };
            const licensed = data.licensed_endpoints;
            const reporting = data.agents_reporting ?? 0;
            const enrolled = data.protected_assets ?? 0;
            const seatsOver = licensed != null && licensed > 0 && reporting > licensed;
            return (
        <table className="data-table data-table--readable">
          <tbody>
            <tr>
              <th>Tenant</th>
              <td>
                {data.tenant_name} ({data.tenant_short_code})
              </td>
            </tr>
            <tr>
              <th>Appliance</th>
              <td>{data.appliance_name}</td>
            </tr>
            <tr>
              <th>Site</th>
              <td>{data.site_name}</td>
            </tr>
            <tr>
              <th>Status</th>
              <td>
                <SeverityPill value={data.status} kind="status" filterBase="/appliances" />
              </td>
            </tr>
            <tr>
              <th>Last seen</th>
              <td>
                <ApplianceHeartbeatCell appliance={fleetRow} />
              </td>
            </tr>
            <tr>
              <th>Version</th>
              <td>
                <ApplianceVersionCell appliance={fleetRow} />
              </td>
            </tr>
            <tr>
              <th>Agents</th>
              <td>
                <ApplianceAgentsCell reporting={reporting} total={enrolled} />
              </td>
            </tr>
            <tr>
              <th>Licensed seats</th>
              <td className={seatsOver ? "appliance-seats-cell--over" : undefined}>
                {licensed != null && licensed > 0
                  ? `${reporting} reporting / ${licensed} licensed`
                  : "Not set on tenant contract"}
              </td>
            </tr>
            <tr>
              <th>Health & resources</th>
              <td>
                <ApplianceHealthCell appliance={fleetRow} />
              </td>
            </tr>
            <tr>
              <th>Enabled services</th>
              <td>
                <ApplianceServicesCell services={data.enabled_services} />
              </td>
            </tr>
            <tr>
              <th>Pending jobs</th>
              <td>{data.pending_jobs_count ?? 0}</td>
            </tr>
            <tr>
              <th>Failed jobs</th>
              <td>{data.failed_jobs_count ?? 0}</td>
            </tr>
            <tr>
              <th>Deployment mode</th>
              <td>{data.deployment_mode ?? "—"}</td>
            </tr>
            <tr>
              <th>Local IP</th>
              <td>{data.local_ip ?? "—"}</td>
            </tr>
            <tr>
              <th>Registered</th>
              <td>{data.created_at}</td>
            </tr>
            <tr>
              <th>Updated</th>
              <td>{data.updated_at}</td>
            </tr>
          </tbody>
        </table>
            );
          })()}
        </>
      )}
    </div>
  );
}
