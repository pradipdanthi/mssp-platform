import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCustomerAlertDetail } from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import AiSocAssistPanel from "../components/soc/AiSocAssistPanel";
import AlertTechnicalEvidence from "../components/soc/AlertTechnicalEvidence";
import FilterValueLink from "../components/soc/FilterValueLink";
import SeverityPill from "../components/SeverityPill";
import SuppressionRuleModal from "../components/soc/SuppressionRuleModal";
import { useCustomerQuery } from "../hooks/useCustomerQuery";
import { AiSuggestedSuppressionScope } from "../lib/ai-triage";

export default function AlertDetailPage() {
  const { user } = useAuth();
  const { alertId } = useParams<{ alertId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const canSuppress = user?.role === "customer_admin";
  const { status, data, errorMessage, refetch } = useCustomerQuery(
    () => getCustomerAlertDetail(shortCode as string, alertId as string),
    Boolean(shortCode && alertId),
    [shortCode, alertId]
  );
  const [suppressOpen, setSuppressOpen] = useState(false);
  const [aiPrefill, setAiPrefill] = useState<AiSuggestedSuppressionScope | null>(null);
  const [suppressMessage, setSuppressMessage] = useState<string | null>(null);

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
          {suppressMessage ? <div className="state-message">{suppressMessage}</div> : null}
          <table className="data-table">
            <tbody>
              <tr>
                <th>Title</th>
                <td>{data.alert.title}</td>
              </tr>
              <tr>
                <th>Severity</th>
                <td>
                  <SeverityPill value={data.alert.severity} filterBase="/alerts" />
                </td>
              </tr>
              <tr>
                <th>Status</th>
                <td>
                  <SeverityPill value={data.alert.status} kind="status" filterBase="/alerts" />
                </td>
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
                <td>
                  <FilterValueLink
                    base="/alerts"
                    param="hostname"
                    value={data.alert.hostname}
                  />
                </td>
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
              <tr>
                <th>Detection rule</th>
                <td>
                  {data.alert.wazuh_rule_id ? (
                    <>
                      <FilterValueLink
                        base="/alerts"
                        param="rule_id"
                        value={data.alert.wazuh_rule_id}
                      />
                      {data.alert.wazuh_rule_level
                        ? ` (level ${data.alert.wazuh_rule_level})`
                        : null}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            </tbody>
          </table>

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            Technical evidence
          </h2>
          <AlertTechnicalEvidence
            alert={data.alert}
            renderProcessLink={(value) => (
              <FilterValueLink base="/alerts" param="process" value={value} />
            )}
            renderPathLink={(value) => (
              <FilterValueLink base="/alerts" param="path" value={value} />
            )}
          />

          <AiSocAssistPanel
            shortCode={shortCode}
            alertId={alertId}
            canSuppress={canSuppress}
            onApplySuppress={(scope) => {
              setAiPrefill(scope);
              setSuppressOpen(true);
            }}
          />

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

          {canSuppress ? (
            <SuppressionRuleModal
              open={suppressOpen}
              shortCode={shortCode}
              seedAlerts={[
                {
                  alert_id: data.alert.alert_id,
                  title: data.alert.title,
                  wazuh_rule_id: data.alert.wazuh_rule_id,
                  process_name: data.alert.process_name,
                  parent_process_name: data.alert.parent_process_name,
                  hash_sha256: data.alert.hash_sha256,
                  hash_md5: data.alert.hash_md5,
                  file_path: data.alert.file_path,
                  hostname: data.alert.hostname,
                },
              ]}
              aiPrefill={aiPrefill}
              onClose={() => {
                setSuppressOpen(false);
                setAiPrefill(null);
              }}
              onCreated={async () => {
                setSuppressMessage("Suppression created from AI recommendation.");
                refetch();
              }}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
