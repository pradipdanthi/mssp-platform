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
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setTriageStatus(data.alert.status as AlertStatus);
      setCustomerVisible(data.alert.customer_visible);
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

  return (
    <div>
      <p><Link to="/alerts">← Back to alerts</Link></p>
      <h1 className="page-title">Alert detail</h1>
      <p className="page-subtitle">Internal SOC evidence and customer visibility controls.</p>

      {status === "loading" && <div className="state-message">Loading alert...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        <>
          <table className="data-table">
            <tbody>
              <tr><th>Tenant</th><td>{data.alert.tenant_name} ({data.alert.short_code})</td></tr>
              <tr><th>Title</th><td>{data.alert.alert_title}</td></tr>
              <tr><th>Severity</th><td><span className={`badge badge-${data.alert.severity}`}>{data.alert.severity}</span></td></tr>
              <tr><th>Status</th><td>{data.alert.status}</td></tr>
              <tr><th>Source</th><td>{data.alert.source_tool} / {data.alert.external_alert_id ?? "—"}</td></tr>
              <tr><th>Asset category</th><td>{data.alert.asset_category_label ?? data.alert.asset_category ?? "—"}</td></tr>
              <tr><th>Device type</th><td>{data.alert.device_type ?? "—"}</td></tr>
              <tr><th>Event time</th><td>{data.alert.event_time ?? "—"}</td></tr>
              <tr><th>Asset</th><td>{data.alert.asset_hostname ?? "—"}</td></tr>
              <tr><th>Appliance</th><td>{data.alert.appliance_name ?? "—"}</td></tr>
              <tr><th>Source user</th><td>{data.alert.source_user ?? "—"}</td></tr>
              <tr><th>Source IP</th><td>{data.alert.source_ip ?? "—"}</td></tr>
              <tr><th>Destination</th><td>{data.alert.destination_host ?? "—"} / {data.alert.destination_ip ?? "—"}</td></tr>
              <tr><th>Description</th><td>{data.alert.alert_description ?? "—"}</td></tr>
              <tr><th>Plain summary</th><td>{data.alert.ai_plain_summary ?? "—"}</td></tr>
              <tr><th>Technical summary</th><td>{data.alert.ai_technical_summary ?? "—"}</td></tr>
              <tr><th>Business impact</th><td>{data.alert.ai_business_impact ?? "—"}</td></tr>
              <tr><th>Recommended action</th><td>{data.alert.ai_recommended_action ?? "—"}</td></tr>
              <tr><th>Likely attack type</th><td>{data.alert.ai_likely_attack_type ?? "—"}</td></tr>
              <tr><th>False-positive score</th><td>{data.alert.ai_false_positive_score ?? "—"}</td></tr>
            </tbody>
          </table>

          <p className="page-subtitle" style={{ marginTop: "0.5rem" }}>
            High-severity Wazuh alerts are forwarded to Shuffle for TheHive case creation automatically
            via the control-plane ingress path. Use incident records for playbook triggers and TheHive links.
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
            {!canUpdate && (
              <p className="page-subtitle">Only platform administrators and SOC managers can change alert triage.</p>
            )}
            {saveMessage && <div className="state-message">{saveMessage}</div>}
            <button className="btn btn-primary" type="submit" disabled={!canUpdate || saving}>
              {saving ? "Saving..." : "Save triage"}
            </button>
          </form>

          <h2 className="section-title">MITRE mapping</h2>
          <pre className="credential-panel">{JSON.stringify(data.alert.mitre_mapping, null, 2)}</pre>
          <h2 className="section-title">Raw event (internal)</h2>
          <pre className="credential-panel">{JSON.stringify(data.alert.raw_event, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
