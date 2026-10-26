import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertDetail,
  AlertTriageUpdate,
  getAlertDetail,
  updateAlertTriage,
} from "../api/soc";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Severity from "../components/Severity";

const STATUSES: { value: NonNullable<AlertTriageUpdate["status"]>; label: string }[] = [
  { value: "new", label: "Open" },
  { value: "triaged", label: "In review" },
  { value: "incident_created", label: "Incident created" },
  { value: "false_positive", label: "False positive" },
  { value: "closed", label: "Closed" },
];

export default function AlertDetailWorkbench() {
  const { alertId } = useParams<{ alertId: string }>();
  const { user, logout } = useAuth();
  const canUpdate = user?.role === "platform_admin" || user?.role === "soc_manager";
  const [alert, setAlert] = useState<AlertDetail | null>(null);
  const [status, setStatus] = useState<NonNullable<AlertTriageUpdate["status"]>>("new");
  const [customerVisible, setCustomerVisible] = useState(false);
  const [summary, setSummary] = useState("");
  const [action, setAction] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function load() {
    if (!alertId) return;
    getAlertDetail(alertId)
      .then((r) => {
        setAlert(r.alert);
        setStatus((r.alert.status as NonNullable<AlertTriageUpdate["status"]>) || "new");
        setCustomerVisible(Boolean(r.alert.customer_visible));
        setSummary(r.alert.ai_plain_summary || "");
        setAction(r.alert.ai_recommended_action || "");
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Unable to load alert");
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertId, logout]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!alertId || !canUpdate) return;
    setSaving(true);
    setMsg(null);
    try {
      const r = await updateAlertTriage(alertId, {
        status,
        customer_visible: customerVisible,
        ai_plain_summary: summary || null,
        ai_recommended_action: action || null,
      });
      setAlert(r.alert);
      setMsg("Alert updated.");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout();
        return;
      }
      setMsg("Update failed.");
    } finally {
      setSaving(false);
    }
  }

  if (!alertId) return <div className="err">Missing alert id</div>;

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <Link className="muted" to="/alerts">
            ← All alerts
          </Link>
          <h2>{alert?.alert_title || alert?.title || "Alert"}</h2>
          <p className="muted">
            {alert?.short_code || "—"} · <Severity value={alert?.severity || ""} /> · {alert?.status}
          </p>
        </div>
      </div>
      <div className="workbench-b detail-grid">
        {err && <div className="err">{err}</div>}
        <section className="detail-card">
          <h3>Evidence</h3>
          <dl className="kv">
            <dt>Host</dt>
            <dd>{alert?.destination_host || "—"}</dd>
            <dt>Source</dt>
            <dd>{alert?.source_tool || "—"}</dd>
            <dt>AI verdict</dt>
            <dd>{alert?.ai_verdict || "—"}</dd>
            <dt>When</dt>
            <dd>{alert?.event_time ? new Date(alert.event_time).toLocaleString() : "—"}</dd>
          </dl>
        </section>
        <section className="detail-card">
          <h3>Triage</h3>
          <form onSubmit={onSave} className="triage-form">
            <label>
              Status
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as NonNullable<AlertTriageUpdate["status"]>)}
                disabled={!canUpdate}
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={customerVisible}
                onChange={(e) => setCustomerVisible(e.target.checked)}
                disabled={!canUpdate}
              />
              Visible to customer
            </label>
            <label>
              Customer summary
              <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} disabled={!canUpdate} />
            </label>
            <label>
              Recommended action
              <textarea rows={3} value={action} onChange={(e) => setAction(e.target.value)} disabled={!canUpdate} />
            </label>
            {canUpdate ? (
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save triage"}
              </button>
            ) : (
              <p className="muted">Analysts can view; managers/admins update status.</p>
            )}
            {msg && <p className="muted">{msg}</p>}
          </form>
        </section>
      </div>
    </div>
  );
}
