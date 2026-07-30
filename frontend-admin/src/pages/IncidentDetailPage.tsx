import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  addIncidentComment,
  getIncidentDetail,
  getUsers,
  IncidentTriageUpdate,
  updateIncidentTriage,
} from "../api/admin";
import { getEdrDeepDive, type EdrDeepDive } from "../api/edr";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import EdrControlPanel from "../components/edr/EdrControlPanel";
import MitreBadges from "../components/edr/MitreBadges";
import ProcessTreeWidget from "../components/edr/ProcessTreeWidget";

type IncidentStatus = NonNullable<IncidentTriageUpdate["status"]>;
const INCIDENT_STATUSES: IncidentStatus[] = [
  "open",
  "in_progress",
  "waiting_customer",
  "resolved",
  "closed",
];

export default function IncidentDetailPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const { user, logout } = useAuth();
  const canExecuteEdr =
    user?.role === "platform_admin" ||
    user?.role === "soc_manager" ||
    user?.role === "soc_analyst";
  const incidentQuery = useAdminQuery(
    () => getIncidentDetail(incidentId as string),
    [incidentId]
  );
  const usersQuery = useAdminQuery(() => getUsers({ page_size: 200 }), []);
  const [triageStatus, setTriageStatus] = useState<IncidentStatus>("open");
  const [assigneeId, setAssigneeId] = useState("");
  const [customerSummary, setCustomerSummary] = useState("");
  const [recommendedAction, setRecommendedAction] = useState("");
  const [commentText, setCommentText] = useState("");
  const [commentVisibility, setCommentVisibility] = useState<"internal" | "customer">("internal");
  const [saving, setSaving] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [edr, setEdr] = useState<EdrDeepDive | null>(null);

  useEffect(() => {
    if (incidentQuery.data) {
      setTriageStatus(incidentQuery.data.incident.status as IncidentStatus);
      setAssigneeId(incidentQuery.data.incident.assigned_to_user_id ?? "");
      setCustomerSummary(incidentQuery.data.incident.customer_visible_summary ?? "");
      setRecommendedAction(
        incidentQuery.data.incident.customer_action_required ??
          incidentQuery.data.primary_alert?.ai_recommended_action ??
          ""
      );
    }
  }, [incidentQuery.data]);

  useEffect(() => {
    const inc = incidentQuery.data?.incident;
    if (!inc?.incident_number || !inc.short_code) {
      setEdr(null);
      return;
    }
    getEdrDeepDive(inc.incident_number, inc.short_code)
      .then(setEdr)
      .catch(() => setEdr(null));
  }, [incidentQuery.data?.incident.incident_number, incidentQuery.data?.incident.short_code]);

  function handleActionError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.status === 401) {
      logout();
      return;
    }
    setActionMessage(
      error instanceof ApiError && typeof error.detail === "string" ? error.detail : fallback
    );
  }

  async function handleTriageSave(event: FormEvent) {
    event.preventDefault();
    if (!incidentId) return;
    setSaving(true);
    setActionMessage(null);
    try {
      await updateIncidentTriage(incidentId, {
        status: triageStatus,
        assigned_to_user_id: assigneeId || null,
        customer_visible_summary: customerSummary || null,
        customer_action_required: recommendedAction || null,
      });
      setActionMessage("Incident triage updated.");
      incidentQuery.refetch();
    } catch (error) {
      handleActionError(error, "Unable to update incident triage.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCommentSubmit(event: FormEvent) {
    event.preventDefault();
    if (!incidentId || !commentText.trim()) return;
    setSaving(true);
    setActionMessage(null);
    try {
      await addIncidentComment(incidentId, {
        comment_text: commentText,
        visibility: commentVisibility,
      });
      setCommentText("");
      setCommentVisibility("internal");
      setActionMessage("Comment added.");
      incidentQuery.refetch();
    } catch (error) {
      handleActionError(error, "Unable to add incident comment.");
    } finally {
      setSaving(false);
    }
  }

  if (!incidentId) {
    return <div className="state-message state-error">Incident ID is missing from the URL.</div>;
  }

  const assignableUsers =
    usersQuery.data?.users.filter(
      (user) =>
        user.status === "active" &&
        ["platform_admin", "soc_manager", "soc_analyst"].includes(user.role)
    ) ?? [];

  return (
    <div>
      <p><Link to="/incidents">← Back to incidents</Link></p>
      <h1 className="page-title">Incident detail</h1>
      <p className="page-subtitle">Internal case workflow, assignment, timeline, and comments.</p>

      {incidentQuery.status === "loading" && <div className="state-message">Loading incident...</div>}
      {incidentQuery.status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {incidentQuery.status === "error" && (
        <div className="state-message state-error">{incidentQuery.errorMessage}</div>
      )}

      {incidentQuery.status === "success" && incidentQuery.data && (
        <>
          <table className="data-table">
            <tbody>
              <tr><th>Tenant</th><td>{incidentQuery.data.incident.tenant_name} ({incidentQuery.data.incident.short_code})</td></tr>
              <tr><th>Incident</th><td>{incidentQuery.data.incident.incident_number}</td></tr>
              <tr><th>Title</th><td>{incidentQuery.data.incident.title}</td></tr>
              <tr><th>Severity</th><td><span className={`badge badge-${incidentQuery.data.incident.severity}`}>{incidentQuery.data.incident.severity}</span></td></tr>
              <tr><th>Status</th><td>{incidentQuery.data.incident.status}</td></tr>
              <tr><th>Assigned to</th><td>{incidentQuery.data.incident.assigned_to ?? "Unassigned"}</td></tr>
              <tr><th>Business impact</th><td>{incidentQuery.data.incident.business_impact ?? "—"}</td></tr>
              <tr><th>Customer action</th><td>{incidentQuery.data.incident.customer_action_required ?? "—"}</td></tr>
              <tr><th>Resolution</th><td>{incidentQuery.data.incident.resolution_summary ?? "—"}</td></tr>
              <tr><th>Internal notes</th><td>{incidentQuery.data.incident.internal_notes ?? "—"}</td></tr>
              <tr><th>Opened</th><td>{incidentQuery.data.incident.opened_at ?? "—"}</td></tr>
            </tbody>
          </table>

          {incidentQuery.data.primary_alert ? (
            <>
              <h2 className="section-title">Primary alert context</h2>
              <table className="data-table">
                <tbody>
                  <tr>
                    <th>Alert</th>
                    <td>
                      <Link to={`/alerts/${incidentQuery.data.primary_alert.id}`}>
                        {incidentQuery.data.primary_alert.alert_title}
                      </Link>
                    </td>
                  </tr>
                  <tr><th>Device type</th><td>{incidentQuery.data.primary_alert.device_type ?? "—"}</td></tr>
                  <tr><th>Asset category</th><td>{incidentQuery.data.primary_alert.asset_category_label ?? "—"}</td></tr>
                  <tr><th>Criticality</th><td>{incidentQuery.data.primary_alert.asset_criticality ?? "—"}</td></tr>
                  <tr><th>Location</th><td>{incidentQuery.data.primary_alert.asset_location ?? "—"}</td></tr>
                  <tr><th>IP address</th><td className="cell-mono">{incidentQuery.data.primary_alert.display_ip_address ?? "—"}</td></tr>
                  <tr><th>Operating system</th><td>{incidentQuery.data.primary_alert.display_operating_system ?? "—"}</td></tr>
                  <tr><th>MAC address</th><td className="cell-mono">{incidentQuery.data.primary_alert.display_mac_address ?? incidentQuery.data.primary_alert.mac_address_status ?? "—"}</td></tr>
                  <tr><th>Business impact</th><td>{incidentQuery.data.primary_alert.ai_business_impact ?? incidentQuery.data.incident.business_impact ?? "—"}</td></tr>
                  <tr><th>Recommended action</th><td>{incidentQuery.data.primary_alert.ai_recommended_action ?? "—"}</td></tr>
                  <tr><th>Likely attack type</th><td>{incidentQuery.data.primary_alert.ai_likely_attack_type ?? "—"}</td></tr>
                </tbody>
              </table>
            </>
          ) : null}

          {incidentQuery.data.incident.short_code ? (
            <>
              <h2 className="section-title">Endpoint containment (EDR)</h2>
              <p className="page-subtitle">
                Network quarantine blocks all traffic except Manager/DHCP/loopback (not RDP-only).
                Every isolate/unisolate is written to the Audit Log with actor, portal, and source IP.
              </p>
              {edr ? (
                <>
                  <MitreBadges tactics={edr.mitre.tactics} techniques={edr.mitre.techniques} />
                  <ProcessTreeWidget
                    root={edr.process_tree.root}
                    message={edr.process_tree.message}
                  />
                </>
              ) : null}
              <EdrControlPanel
                tenantShortCode={incidentQuery.data.incident.short_code}
                incidentNumber={incidentQuery.data.incident.incident_number}
                agentId={(edr?.endpoint?.agent_id as string | undefined) ?? undefined}
                canExecute={canExecuteEdr}
              />
            </>
          ) : null}

          <h2 className="section-title">Triage</h2>
          <form className="credential-panel" onSubmit={handleTriageSave}>
            <label className="form-label" htmlFor="incident-status">Status</label>
            <select
              id="incident-status"
              className="form-input"
              value={triageStatus}
              disabled={saving}
              onChange={(event) => setTriageStatus(event.target.value as IncidentStatus)}
            >
              {INCIDENT_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>

            <label className="form-label" htmlFor="incident-assignee">Assigned to</label>
            <select
              id="incident-assignee"
              className="form-input"
              value={assigneeId}
              disabled={saving || usersQuery.status !== "success"}
              onChange={(event) => setAssigneeId(event.target.value)}
            >
              <option value="">Unassigned</option>
              {assignableUsers.map((user) => (
                <option key={user.id} value={user.id}>{user.full_name} ({user.role})</option>
              ))}
            </select>

            <label className="form-label" htmlFor="customer-summary">Customer-visible summary</label>
            <textarea
              id="customer-summary"
              className="form-input"
              rows={5}
              value={customerSummary}
              disabled={saving}
              onChange={(event) => setCustomerSummary(event.target.value)}
              placeholder="Plain-language summary shown on the customer portal for this incident."
            />
            <label className="form-label" htmlFor="customer-recommended-action">
              Recommended action
            </label>
            <textarea
              id="customer-recommended-action"
              className="form-input"
              rows={4}
              value={recommendedAction}
              disabled={saving}
              onChange={(event) => setRecommendedAction(event.target.value)}
              placeholder="What the customer should do next (shown as Action required)."
            />
            <p className="page-subtitle">
              These fields are what the customer portal shows. Polish rule-driven defaults before sharing.
            </p>
            <div style={{ marginTop: "14px" }}>
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving..." : "Save triage"}
              </button>
            </div>
          </form>

          <h2 className="section-title">Timeline</h2>
          {incidentQuery.data.timeline.length === 0 ? (
            <div className="state-message">No timeline events yet.</div>
          ) : (
            <table className="data-table">
              <thead><tr><th>When</th><th>Type</th><th>Visibility</th><th>Title</th><th>Details</th><th>By</th></tr></thead>
              <tbody>
                {incidentQuery.data.timeline.map((event) => (
                  <tr key={event.id}>
                    <td>{event.created_at}</td><td>{event.event_type}</td><td>{event.visibility}</td>
                    <td>{event.title}</td><td>{event.details ?? "—"}</td><td>{event.created_by ?? "System"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="section-title">Comments</h2>
          {incidentQuery.data.comments.length === 0 ? (
            <div className="state-message">No comments yet.</div>
          ) : (
            <table className="data-table">
              <thead><tr><th>When</th><th>Visibility</th><th>Comment</th><th>By</th></tr></thead>
              <tbody>
                {incidentQuery.data.comments.map((comment) => (
                  <tr key={comment.id}>
                    <td>{comment.created_at}</td><td>{comment.visibility}</td>
                    <td>{comment.comment_text}</td><td>{comment.created_by ?? "Unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <form className="credential-panel" style={{ marginTop: "14px" }} onSubmit={handleCommentSubmit}>
            <label className="form-label" htmlFor="comment-visibility">Visibility</label>
            <select
              id="comment-visibility"
              className="form-input"
              value={commentVisibility}
              disabled={saving}
              onChange={(event) => setCommentVisibility(event.target.value as "internal" | "customer")}
            >
              <option value="internal">Internal SOC only</option>
              <option value="customer">Customer-visible classification</option>
            </select>
            <label className="form-label" htmlFor="incident-comment">Comment</label>
            <textarea
              id="incident-comment"
              className="form-input"
              rows={4}
              required
              value={commentText}
              disabled={saving}
              onChange={(event) => setCommentText(event.target.value)}
            />
            <div style={{ marginTop: "14px" }}>
              <button className="btn btn-primary" type="submit" disabled={saving || !commentText.trim()}>
                Add comment
              </button>
            </div>
          </form>
          {actionMessage && <div className="state-message" style={{ marginTop: "14px" }}>{actionMessage}</div>}
        </>
      )}
    </div>
  );
}
