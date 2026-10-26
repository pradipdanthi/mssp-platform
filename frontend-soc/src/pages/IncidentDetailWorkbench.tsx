import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  addIncidentComment,
  getIncidentDetail,
  IncidentComment,
  IncidentDetail,
  IncidentTriageUpdate,
  updateIncidentTriage,
} from "../api/soc";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Severity from "../components/Severity";

const STATUSES: NonNullable<IncidentTriageUpdate["status"]>[] = [
  "open",
  "in_progress",
  "waiting_customer",
  "resolved",
  "closed",
];

export default function IncidentDetailWorkbench() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const { logout } = useAuth();
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [comments, setComments] = useState<IncidentComment[]>([]);
  const [status, setStatus] = useState<NonNullable<IncidentTriageUpdate["status"]>>("open");
  const [summary, setSummary] = useState("");
  const [action, setAction] = useState("");
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function load() {
    if (!incidentId) return;
    getIncidentDetail(incidentId)
      .then((r) => {
        setIncident(r.incident);
        setComments(r.comments || []);
        setStatus((r.incident.status as NonNullable<IncidentTriageUpdate["status"]>) || "open");
        setSummary(r.incident.customer_visible_summary || "");
        setAction(r.incident.customer_action_required || "");
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr("Unable to load incident");
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId, logout]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!incidentId) return;
    setSaving(true);
    setMsg(null);
    try {
      const r = await updateIncidentTriage(incidentId, {
        status,
        customer_visible_summary: summary || null,
        customer_action_required: action || null,
      });
      setIncident(r.incident);
      setMsg("Incident updated.");
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

  async function onComment(e: FormEvent) {
    e.preventDefault();
    if (!incidentId || comment.trim().length < 2) return;
    setSaving(true);
    try {
      await addIncidentComment(incidentId, {
        comment_text: comment.trim(),
        visibility: "internal",
      });
      setComment("");
      setMsg("Comment added.");
      load();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout();
        return;
      }
      setMsg("Could not add comment.");
    } finally {
      setSaving(false);
    }
  }

  if (!incidentId) return <div className="err">Missing incident id</div>;

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <Link className="muted" to="/incidents">
            ← All incidents
          </Link>
          <h2>
            {incident?.incident_number || "Incident"} — {incident?.title || ""}
          </h2>
          <p className="muted">
            {incident?.short_code || "—"} · <Severity value={incident?.severity || ""} /> ·{" "}
            {incident?.status}
          </p>
        </div>
      </div>
      <div className="workbench-b detail-grid">
        {err && <div className="err">{err}</div>}
        <section className="detail-card">
          <h3>Ticket update</h3>
          <form onSubmit={onSave} className="triage-form">
            <label>
              Status
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as NonNullable<IncidentTriageUpdate["status"]>)}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Customer summary
              <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
            </label>
            <label>
              Customer action required
              <textarea rows={3} value={action} onChange={(e) => setAction(e.target.value)} />
            </label>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save ticket"}
            </button>
            {msg && <p className="muted">{msg}</p>}
          </form>
        </section>
        <section className="detail-card">
          <h3>Internal comments</h3>
          <ul className="comment-list">
            {comments.length === 0 && <li className="muted">No comments yet.</li>}
            {comments.map((c) => (
              <li key={c.id}>
                <strong>{c.created_by || c.author || "SOC"}</strong>
                <span className="muted"> · {c.created_at ? new Date(c.created_at).toLocaleString() : ""}</span>
                <div>{c.comment_text}</div>
              </li>
            ))}
          </ul>
          <form onSubmit={onComment} className="triage-form">
            <label>
              Add comment
              <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
            <button className="btn btn-ghost" type="submit" disabled={saving || comment.trim().length < 2}>
              Post comment
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
