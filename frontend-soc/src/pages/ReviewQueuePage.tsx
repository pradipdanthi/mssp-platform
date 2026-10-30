import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import {
  getReviewItem,
  getReviewQueue,
  getTiaReadiness,
  reviewAction,
  type ReviewDetail,
  type ReviewItem,
  type ReviewSummary,
  type TiaReadiness,
} from "../api/soc";
import Severity from "../components/Severity";

const MANAGER_ROLES = ["platform_admin", "soc_manager"];

function fmtAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

function fmtDeadline(item: Pick<ReviewItem, "seconds_to_deadline" | "overdue" | "status">): string {
  if (item.status === "resolved") return "—";
  return item.overdue ? `overdue by ${fmtAge(-item.seconds_to_deadline)}` : `in ${fmtAge(item.seconds_to_deadline)}`;
}

/** What the notification state means, without implying anything the evidence does not show. */
function notificationLabel(state: string): string {
  const labels: Record<string, string> = {
    not_required: "No page needed",
    no_recipients_configured: "NOT SENT — no on-call recipient configured",
    page_required: "Page waiting to be sent",
    page_queued: "Page being sent",
    page_submitted: "Page handed to provider (not confirmed received)",
    page_delivered: "Provider reports delivered",
    page_failed: "PAGE FAILED — delivery gave up",
    acknowledged: "Acknowledged by an analyst",
  };
  return labels[state] ?? state;
}

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string") return e.detail;
    return `Request failed (${e.status})`;
  }
  return "Request failed";
}

function ReadinessBanner({ readiness }: { readiness: TiaReadiness | null }) {
  if (!readiness) return null;
  const faults = readiness.faults.filter((f) => f.severity === "fault");
  const warnings = readiness.faults.filter((f) => f.severity === "warning");
  if (faults.length === 0 && warnings.length === 0) return null;
  return (
    <div className={faults.length ? "err" : "muted"} role="alert" style={{ marginBottom: "0.75rem" }}>
      <strong>{faults.length ? "TIA is not fully operational" : "TIA notices"}</strong>
      <ul style={{ margin: "0.25rem 0 0 1.1rem" }}>
        {[...faults, ...warnings].map((f) => (
          <li key={f.code}>{f.message}</li>
        ))}
      </ul>
    </div>
  );
}

export function ReviewQueuePage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [readiness, setReadiness] = useState<TiaReadiness | null>(null);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      getReviewQueue({ status: status || undefined, include_resolved: status === "resolved" }),
      getTiaReadiness().catch(() => null),
    ])
      .then(([q, r]) => {
        setItems(q.items);
        setSummary(q.summary);
        setReadiness(r);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr(e instanceof ApiError && e.status === 503 ? "The review queue is unavailable: a required database migration is missing." : errText(e));
      })
      .finally(() => setLoading(false));
  }, [logout, status]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 30000);
    return () => window.clearInterval(t);
  }, [load]);

  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <h2>Investigation review queue</h2>
          <p className="muted">
            Cases that need a person: the investigation failed, timed out, or found something serious. Deadlines are
            provisional targets, not approved customer SLAs.
          </p>
        </div>
        <div className="workbench-filters">
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">Open and acknowledged</option>
            <option value="open">Open (not acknowledged)</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
          <button type="button" className="btn btn-ghost" onClick={load}>
            Refresh
          </button>
          <Link className="btn btn-ghost" to="/">
            Back to feed
          </Link>
        </div>
      </div>
      <div className="workbench-b">
        <ReadinessBanner readiness={readiness} />
        {err && <div className="err">{err}</div>}
        {summary && (
          <p className="muted" style={{ marginTop: 0 }}>
            {summary.open_count} open · {summary.unacknowledged_count} not acknowledged · {summary.overdue_count} overdue ·{" "}
            {summary.unassigned_count} unassigned
            {summary.undeliverable_page_count ? ` · ${summary.undeliverable_page_count} page(s) not delivered` : ""}
          </p>
        )}
        {!loading && !err && items.length === 0 ? (
          <div className="empty">Nothing needs review.</div>
        ) : (
          <table className="wb-table">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Customer / case</th>
                <th>Why</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Age</th>
                <th>Deadline (provisional)</th>
                <th>Notification</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} onClick={() => navigate(`/reviews/${r.id}`)}>
                  <td>
                    <Severity value={r.assessed_priority === "P1" ? "critical" : r.assessed_priority === "P2" ? "high" : "medium"} />{" "}
                    {r.assessed_priority}
                  </td>
                  <td>
                    <div>{r.customer_name}</div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      {r.case_title || r.alert_id}
                    </div>
                  </td>
                  <td>
                    <div>{r.reason_code.replace(/_/g, " ")}</div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      {r.error_category || r.execution_status}
                    </div>
                  </td>
                  <td>
                    {r.status}
                    {r.reopened_count ? ` (reopened ${r.reopened_count}×)` : ""}
                    {r.analysis_available ? " · analysis available" : ""}
                  </td>
                  <td>{r.assigned_to || "unassigned"}</td>
                  <td>{fmtAge(r.age_seconds)}</td>
                  <td style={r.overdue ? { color: "#ff6b6b" } : undefined}>{fmtDeadline(r)}</td>
                  <td>{notificationLabel(r.notification_state)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function ReviewDetailPage() {
  const { itemId } = useParams<{ itemId: string }>();
  const { user, logout } = useAuth();
  const role = user?.role || "";
  const isManager = MANAGER_ROLES.includes(role);
  const [item, setItem] = useState<ReviewDetail | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!itemId) return;
    getReviewItem(itemId)
      .then((d) => {
        setItem(d);
        setErr(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logout();
        else setErr(errText(e));
      });
  }, [itemId, logout]);

  useEffect(load, [load]);

  async function act(action: "acknowledge" | "assign" | "resolve" | "reopen") {
    if (!itemId) return;
    setBusy(true);
    setMsg(null);
    try {
      await reviewAction(itemId, action, { note: note.trim() || undefined });
      setMsg(
        action === "acknowledge"
          ? "Acknowledged. The security case itself is unchanged."
          : action === "assign"
            ? "Assigned to you."
            : action === "resolve"
              ? "Resolved."
              : "Reopened."
      );
      setNote("");
      load();
    } catch (e) {
      setMsg(null);
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!item) return <div className="workbench"><div className="workbench-b">{err ? <div className="err">{err}</div> : <p className="muted">Loading…</p>}</div></div>;

  const canResolve = isManager || (role === "soc_analyst" && item.assigned_to === user?.email);
  return (
    <div className="workbench">
      <div className="workbench-h">
        <div>
          <h2>
            {item.customer_name} · {item.case_title || item.alert_id}
          </h2>
          <p className="muted">
            {item.assessed_priority} · {item.status} · owner {item.assigned_to || "unassigned"} · age {fmtAge(item.age_seconds)} · deadline{" "}
            {fmtDeadline(item)} (provisional)
          </p>
        </div>
        <div className="workbench-filters">
          <Link className="btn btn-ghost" to="/reviews">
            Back to queue
          </Link>
          <Link className="btn btn-ghost" to={`/alerts/${item.alert_id}`}>
            Open the case
          </Link>
        </div>
      </div>
      <div className="workbench-b">
        {err && <div className="err">{err}</div>}
        {msg && <div className="muted">{msg}</div>}

        <div className="detail-card" style={{ marginBottom: "0.75rem" }}>
          <h3>Actions</h3>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (required, at least 5 characters, to resolve or reopen)"
            rows={2}
            style={{ width: "100%", marginBottom: "0.5rem" }}
            aria-label="Note"
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button type="button" className="btn btn-primary" disabled={busy || item.status !== "open"} onClick={() => act("acknowledge")}>
              Acknowledge
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy || item.status === "resolved" || item.assigned_to === user?.email} onClick={() => act("assign")}>
              Assign to me
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy || item.status === "resolved" || !canResolve} onClick={() => act("resolve")}>
              Resolve
            </button>
            <button type="button" className="btn btn-ghost" disabled={busy || item.status !== "resolved" || !isManager} onClick={() => act("reopen")}>
              Reopen
            </button>
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            Acknowledging records that you own this page. It does not resolve the item or change the security case.
          </p>
        </div>

        <div className="detail-grid">
          <div className="detail-card">
            <h3>Why a person is needed</h3>
            <p>{item.reason_code.replace(/_/g, " ")}</p>
            <ul>
              {(item.reasons || []).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            {item.analysis_available && <p className="muted">A later analysis succeeded. It is shown below; a person still decides.</p>}
          </div>
          <div className="detail-card">
            <h3>Notification</h3>
            <p>{notificationLabel(item.notification_state)}</p>
            <table className="wb-table">
              <thead>
                <tr>
                  <th>Level</th>
                  <th>To</th>
                  <th>State</th>
                  <th>Tries</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {item.notifications.map((n) => (
                  <tr key={n.id} style={{ cursor: "default" }}>
                    <td>{n.level}</td>
                    <td>{n.recipient || (n.blocked_reason ? `none (${n.blocked_reason.replace(/_/g, " ")})` : "—")}</td>
                    <td>{n.state}</td>
                    <td>
                      {n.attempts}/{n.max_attempts}
                    </td>
                    <td>{n.last_error && n.state !== "submitted" ? n.last_error : n.delivery_evidence || "—"}</td>
                  </tr>
                ))}
                {item.notifications.length === 0 && (
                  <tr style={{ cursor: "default" }}>
                    <td colSpan={5} className="muted">
                      No page for this item.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="detail-card">
            <h3>Investigation attempts</h3>
            <table className="wb-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Status</th>
                  <th>Dispatched</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {item.attempts.map((a) => (
                  <tr key={a.id} style={{ cursor: "default" }}>
                    <td>{a.attempt_no}</td>
                    <td>{a.status.replace(/_/g, " ")}</td>
                    <td>{new Date(a.dispatched_at).toLocaleString()}</td>
                    <td>
                      {a.outcome_uncertain ? "Outcome uncertain — remote work may still finish" : a.transport_error || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="detail-card">
            <h3>Results received</h3>
            <table className="wb-table">
              <thead>
                <tr>
                  <th>Finding</th>
                  <th>Applied</th>
                  <th>Via</th>
                </tr>
              </thead>
              <tbody>
                {item.results.map((r) => (
                  <tr key={r.id} style={{ cursor: "default" }}>
                    <td>
                      {r.verdict ? `${r.verdict} (${r.confidence ?? "?"}%)` : `no verdict (${r.error_category || r.execution_status})`}
                      {r.late ? " · late" : ""}
                      {r.material && !r.applied ? " · serious, kept as history" : ""}
                    </td>
                    <td>{r.applied ? "yes" : r.apply_reason.replace(/_/g, " ")}</td>
                    <td>{r.first_source}</td>
                  </tr>
                ))}
                {item.results.length === 0 && (
                  <tr style={{ cursor: "default" }}>
                    <td colSpan={3} className="muted">
                      No result has been received.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="detail-card" style={{ marginTop: "0.75rem" }}>
          <h3>History</h3>
          <table className="wb-table">
            <tbody>
              {item.events.map((e, i) => (
                <tr key={i} style={{ cursor: "default" }}>
                  <td>{new Date(e.at).toLocaleString()}</td>
                  <td>{e.event_type.replace(/_/g, " ")}</td>
                  <td>{e.actor}</td>
                  <td>
                    {e.from_status && e.to_status && e.from_status !== e.to_status ? `${e.from_status} → ${e.to_status}` : ""}
                    {typeof e.detail?.note === "string" && e.detail.note ? ` “${e.detail.note}”` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
