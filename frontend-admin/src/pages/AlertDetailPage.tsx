import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriageUpdate,
  getAlertDetail,
  updateAlertTriage,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

type AlertStatus = NonNullable<AlertTriageUpdate["status"]>;

const ALERT_STATUSES: AlertStatus[] = [
  "new",
  "triaged",
  "incident_created",
  "false_positive",
  "closed",
];

export default function AlertDetailPage() {
  const { alertId } = useParams<{ alertId: string }>();
  const { user, logout } = useAuth();
  const canUpdate = user?.role === "platform_admin" || user?.role === "soc_manager";
  const { status, data, errorMessage, refetch } = useAdminQuery(
    () => getAlertDetail(alertId as string),
    [alertId]
  );
  const [triageStatus, setTriageStatus] = useState<AlertStatus>("new");
  const [customerVisible, setCustomerVisible] = useState(false);
  const [customerSummary, setCustomerSummary] = useState("");
  const [recommendedAction, setRecommendedAction] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setTriageStatus(data.alert.status as AlertStatus);
      setCustomerVisible(data.alert.customer_visible);
      setCustomerSummary(data.alert.ai_plain_summary ?? "");
      setRecommendedAction(data.alert.ai_recommended_action ?? "");
    }
  }, [data]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!alertId || !triageStatus || !canUpdate) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await updateAlertTriage(alertId, {
        status: triageStatus,
        customer_visible: customerVisible,
        ai_plain_summary: customerSummary || null,
        ai_recommended_action: recommendedAction || null,
      });
      setSaveMessage("Alert triage updated.");
      refetch();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout();
        return;
      }
      setSaveMessage(
        error instanceof ApiError && typeof error.detail === "string"
          ? error.detail
          : "Unable to update alert triage."
      );
    } finally {
      setSaving(false);
    }
  }

  if (!alertId) {
    return <div className="state-message state-error">Alert ID is missing from the URL.</div>;
  }

  const alert = data?.alert;
  const macDisplay =
    alert?.display_mac_address ??
    (alert?.mac_address_status ? alert.mac_address_status : "—");

  return (
    <div>
      <p><Link to="/alerts">← Back to alerts</Link></p>
      <h1 className="page-title">Alert detail</h1>
      <p className="page-subtitle">Internal SOC evidence and customer visibility controls.</p>

      {status === "loading" && <div className="state-message">Loading alert...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && alert && (
        <>
          <h2 className="section-title">Detection</h2>
          <table className="data-table">
            <tbody>
              <tr><th>Tenant</th><td>{alert.tenant_name} ({alert.short_code})</td></tr>
              <tr><th>Title</th><td>{alert.alert_title}</td></tr>
              <tr><th>Severity</th><td><span className={`badge badge-${alert.severity}`}>{alert.severity}</span></td></tr>
              <tr><th>Status</th><td>{alert.status}</td></tr>
              <tr><th>Source</th><td>{alert.source_tool} / {alert.external_alert_id ?? "—"}</td></tr>
              <tr><th>Wazuh rule</th><td>{alert.wazuh_rule_id ?? "—"}</td></tr>
              <tr><th>Event time</th><td>{alert.event_time ?? "—"}</td></tr>
              <tr><th>Description</th><td>{alert.alert_description ?? "—"}</td></tr>
            </tbody>
          </table>

          <h2 className="section-title">Endpoint & asset</h2>
          <table className="data-table">
            <tbody>
              <tr><th>Asset category</th><td>{alert.asset_category_label ?? alert.asset_category ?? "—"}</td></tr>
              <tr><th>Device type</th><td>{alert.device_type ?? "—"}</td></tr>
              <tr><th>Criticality</th><td>{alert.asset_criticality ?? "—"}</td></tr>
              <tr><th>Location</th><td>{alert.asset_location ?? "—"}</td></tr>
              <tr><th>Asset</th><td>{alert.asset_hostname ?? "—"}</td></tr>
              <tr><th>Asset owner</th><td>{alert.asset_owner ?? "—"}</td></tr>
              <tr><th>Wazuh agent</th><td>{alert.wazuh_agent_id ?? "—"}</td></tr>
              <tr><th>IP address</th><td className="cell-mono">{alert.display_ip_address ?? "—"}</td></tr>
              <tr><th>Operating system</th><td>{alert.display_operating_system ?? "—"}</td></tr>
              <tr><th>MAC address</th><td className="cell-mono">{macDisplay}</td></tr>
              <tr><th>Source user</th><td>{alert.source_user ?? "—"}</td></tr>
              <tr><th>Source IP</th><td className="cell-mono">{alert.source_ip ?? "—"}</td></tr>
              <tr><th>Destination</th><td>{alert.destination_host ?? "—"} / {alert.destination_ip ?? "—"}</td></tr>
              <tr><th>Appliance</th><td>{alert.appliance_name ?? "Not registered (endpoint alerts use Asset)"}</td></tr>
            </tbody>
          </table>

          <h2 className="section-title">SOC analysis</h2>
          <table className="data-table">
            <tbody>
              <tr><th>Plain summary</th><td>{alert.ai_plain_summary ?? "—"}</td></tr>
              <tr><th>Technical summary</th><td>{alert.ai_technical_summary ?? "—"}</td></tr>
              <tr><th>Business impact</th><td>{alert.ai_business_impact ?? "—"}</td></tr>
              <tr><th>Recommended action</th><td>{alert.ai_recommended_action ?? "—"}</td></tr>
              <tr><th>Likely attack type</th><td>{alert.ai_likely_attack_type ?? "—"}</td></tr>
              <tr><th>False-positive score</th><td>{alert.ai_false_positive_score ?? "—"}</td></tr>
            </tbody>
          </table>

          <p className="page-subtitle" style={{ marginTop: "0.5rem" }}>
            SOC analysis fields are rule-driven until the AI worker is enabled. High-severity Wazuh
            alerts are forwarded to Shuffle for case creation via the control-plane ingress path.
          </p>

          <h2 className="section-title">Triage</h2>
          <form className="credential-panel" onSubmit={handleSave}>
            <label className="form-label" htmlFor="alert-status">Status</label>
            <select
              id="alert-status"
              className="form-input"
              value={triageStatus}
              disabled={!canUpdate || saving}
              onChange={(event) => setTriageStatus(event.target.value as AlertStatus)}
            >
              {ALERT_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
            <label className="form-label" style={{ display: "block" }}>
              <input
                type="checkbox"
                checked={customerVisible}
                disabled={!canUpdate || saving}
                onChange={(event) => setCustomerVisible(event.target.checked)}
              />{" "}
              Customer visible
            </label>
            <label className="form-label" htmlFor="alert-customer-summary">
              Customer-visible summary
            </label>
            <textarea
              id="alert-customer-summary"
              className="form-input"
              rows={4}
              value={customerSummary}
              disabled={!canUpdate || saving}
              onChange={(event) => setCustomerSummary(event.target.value)}
              placeholder="Plain-language summary the customer will see when this alert is visible."
            />
            <label className="form-label" htmlFor="alert-recommended-action">
              Recommended action
            </label>
            <textarea
              id="alert-recommended-action"
              className="form-input"
              rows={4}
              value={recommendedAction}
              disabled={!canUpdate || saving}
              onChange={(event) => setRecommendedAction(event.target.value)}
              placeholder="What the customer (or your SOC) should do next."
            />
            <p className="page-subtitle">
              Edit these before enabling customer visibility. Rule-driven defaults can be polished into
              customer-ready wording here.
            </p>
            {!canUpdate && (
              <p className="page-subtitle">Only platform administrators and SOC managers can change alert triage.</p>
            )}
            {saveMessage && <div className="state-message">{saveMessage}</div>}
            <button className="btn btn-primary" type="submit" disabled={!canUpdate || saving}>
              {saving ? "Saving..." : "Save triage"}
            </button>
          </form>

          <h2 className="section-title">MITRE mapping</h2>
          <pre className="credential-panel">{JSON.stringify(alert.mitre_mapping, null, 2)}</pre>
          <h2 className="section-title">Raw event (internal)</h2>
          <pre className="credential-panel">{JSON.stringify(alert.raw_event, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
