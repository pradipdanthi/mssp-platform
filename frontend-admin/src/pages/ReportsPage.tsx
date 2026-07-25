import { FormEvent, useEffect, useState } from "react";
import {
  AdminReport,
  ReportDetail,
  ReportStatus,
  Tenant,
  createReport,
  downloadReportPdf,
  downloadReportXlsx,
  getReportDetail,
  getReports,
  getTenants,
  refreshReportMetrics,
  updateReport,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

const STATUSES: ReportStatus[] = ["draft", "published", "archived"];

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) return "Access denied for this action.";
    if (err.status === 409) return "A report for that customer and month already exists.";
  }
  return fallback;
}

function SectionsView({ detail }: { detail: ReportDetail }) {
  const s = detail.sections;
  if (!s) return <div className="state-message">No snapshot yet — click Refresh metrics.</div>;
  const posture = s.posture || {};
  const detection = s.detection || {};
  const incidents = s.incidents || {};
  const recs = s.recommendations || {};
  const notif = s.notifications || {};
  const narrative = s.narrative || {};

  return (
    <div className="report-sections">
      <h3 className="section-title">On-screen preview (customer-safe)</h3>
      <p className="page-subtitle">
        Snapshot: {String(s.generated_at || "—")} · Period:{" "}
        {String((s.period as Record<string, unknown>)?.label || "—")}
      </p>
      <table className="data-table">
        <tbody>
          <tr>
            <th>Posture</th>
            <td>
              Appliances {String(posture.appliances_online)}/{String(posture.appliances_total)} online
              · Assets {String(posture.assets_total)}
            </td>
          </tr>
          <tr>
            <th>Detection</th>
            <td>Alerts total {String((detection as Record<string, unknown>).alerts_total || 0)}</td>
          </tr>
          <tr>
            <th>Incidents</th>
            <td>
              Opened {incidents.opened ?? 0} · Closed {incidents.closed ?? 0} · Still open{" "}
              {incidents.still_open ?? 0}
            </td>
          </tr>
          <tr>
            <th>Recommendations</th>
            <td>
              Open {recs.open_count ?? 0} · Completed {recs.completed_count ?? 0} · Items listed{" "}
              {(recs.items || []).length}
            </td>
          </tr>
          <tr>
            <th>Notifications</th>
            <td>
              Sent {String((notif as Record<string, unknown>).sent_count || 0)} · Delivered{" "}
              {String((notif as Record<string, unknown>).delivered_count || 0)}
            </td>
          </tr>
          <tr>
            <th>Highlights</th>
            <td>{narrative.period_highlights || "—"}</td>
          </tr>
          <tr>
            <th>Trends</th>
            <td>{narrative.trends || "—"}</td>
          </tr>
          <tr>
            <th>Next month</th>
            <td>{narrative.next_month_focus || "—"}</td>
          </tr>
          <tr>
            <th>Leadership asks</th>
            <td>{narrative.leadership_asks || "—"}</td>
          </tr>
        </tbody>
      </table>
      <p className="page-subtitle">{s.deferred_kpis_note}</p>
    </div>
  );
}

export default function ReportsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin" || user?.role === "soc_manager";
  const { status, data, errorMessage, refetch } = useAdminQuery(() => getReports(), []);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [tenantId, setTenantId] = useState("");
  const [reportMonth, setReportMonth] = useState("");
  const [summary, setSummary] = useState("");
  const [highlights, setHighlights] = useState("");
  const [trends, setTrends] = useState("");
  const [nextFocus, setNextFocus] = useState("");
  const [asks, setAsks] = useState("");
  const [createStatus, setCreateStatus] = useState<ReportStatus>("draft");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [editSummary, setEditSummary] = useState("");
  const [editHighlights, setEditHighlights] = useState("");
  const [editTrends, setEditTrends] = useState("");
  const [editNextFocus, setEditNextFocus] = useState("");
  const [editAsks, setEditAsks] = useState("");
  const [editStatus, setEditStatus] = useState<ReportStatus>("draft");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getTenants()
      .then((r) => setTenants(r.tenants))
      .catch(() => undefined);
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!canWrite) return;
    setCreating(true);
    setCreateError(null);
    setSuccess(null);
    try {
      const monthDate = reportMonth.length === 7 ? `${reportMonth}-01` : reportMonth;
      const created = await createReport({
        tenant_id: tenantId,
        report_month: monthDate,
        executive_summary: summary.trim() || null,
        status: createStatus,
        period_highlights: highlights.trim() || null,
        trends: trends.trim() || null,
        next_month_focus: nextFocus.trim() || null,
        leadership_asks: asks.trim() || null,
      });
      setSuccess(`Created ${created.title} (${created.status}) with auto metrics snapshot.`);
      setShowCreate(false);
      setTenantId("");
      setReportMonth("");
      setSummary("");
      setHighlights("");
      setTrends("");
      setNextFocus("");
      setAsks("");
      setCreateStatus("draft");
      refetch();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create report."));
    } finally {
      setCreating(false);
    }
  }

  async function openEdit(row: AdminReport) {
    setEditingId(row.id);
    setEditError(null);
    setSuccess(null);
    try {
      const d = await getReportDetail(row.id);
      setDetail(d);
      setEditSummary(d.executive_summary ?? "");
      setEditStatus(d.status as ReportStatus);
      const n = d.sections?.narrative || {};
      setEditHighlights(n.period_highlights || "");
      setEditTrends(n.trends || "");
      setEditNextFocus(n.next_month_focus || "");
      setEditAsks(n.leadership_asks || "");
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not load report."));
    }
  }

  async function handleEdit(e: FormEvent) {
    e.preventDefault();
    if (!canWrite || !editingId) return;
    setSaving(true);
    setEditError(null);
    try {
      const updated = await updateReport(editingId, {
        executive_summary: editSummary,
        status: editStatus,
        period_highlights: editHighlights,
        trends: editTrends,
        next_month_focus: editNextFocus,
        leadership_asks: editAsks,
      });
      setDetail(updated);
      setSuccess(`Saved ${updated.title} (${updated.status}).`);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update report."));
    } finally {
      setSaving(false);
    }
  }

  async function handleRefresh() {
    if (!canWrite || !editingId) return;
    setBusy(true);
    setEditError(null);
    try {
      const updated = await refreshReportMetrics(editingId);
      setDetail(updated);
      setSuccess("Metrics refreshed from live platform data.");
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not refresh metrics."));
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload(kind: "pdf" | "xlsx") {
    if (!editingId) return;
    setBusy(true);
    setEditError(null);
    try {
      if (kind === "pdf") await downloadReportPdf(editingId);
      else await downloadReportXlsx(editingId);
    } catch (err) {
      setEditError(apiErrorMessage(err, "Download failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Monthly Reports</h1>
          <p className="page-subtitle">
            Enterprise monthly deliverable: auto metrics from the platform, SOC narrative, on-screen
            preview, PDF and Excel download. Publish to share with the customer portal.
          </p>
        </div>
        {canWrite && (
          <button className="btn btn-primary" type="button" onClick={() => setShowCreate(true)}>
            Add Report
          </button>
        )}
      </div>

      {!canWrite && (
        <div className="state-message" style={{ marginBottom: "1rem" }}>
          View-only. Creating/publishing requires platform_admin or soc_manager.
        </div>
      )}
      {success && <div className="state-message state-success">{success}</div>}

      {showCreate && canWrite && (
        <form className="management-panel" onSubmit={handleCreate}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Add Report
          </h2>
          <div className="form-grid">
            <label className="form-label">
              Customer
              <select
                className="form-input"
                required
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
              >
                <option value="">Select…</option>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.short_code})
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Report month
              <input
                className="form-input"
                type="month"
                required
                value={reportMonth}
                onChange={(e) => setReportMonth(e.target.value)}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={createStatus}
                onChange={(e) => setCreateStatus(e.target.value as ReportStatus)}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label form-grid-full">
              Executive summary
              <textarea
                className="form-input"
                rows={3}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
              />
            </label>
            <label className="form-label form-grid-full">
              Period highlights
              <textarea
                className="form-input"
                rows={2}
                value={highlights}
                onChange={(e) => setHighlights(e.target.value)}
              />
            </label>
            <label className="form-label form-grid-full">
              Trends
              <textarea
                className="form-input"
                rows={2}
                value={trends}
                onChange={(e) => setTrends(e.target.value)}
              />
            </label>
            <label className="form-label form-grid-full">
              Next month focus
              <textarea
                className="form-input"
                rows={2}
                value={nextFocus}
                onChange={(e) => setNextFocus(e.target.value)}
              />
            </label>
            <label className="form-label form-grid-full">
              Leadership asks
              <textarea
                className="form-input"
                rows={2}
                value={asks}
                onChange={(e) => setAsks(e.target.value)}
              />
            </label>
          </div>
          {createError && <div className="form-error">{createError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create report"}
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {editingId && (
        <div className="management-panel">
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Edit / preview report
          </h2>
          {canWrite && (
            <form onSubmit={handleEdit}>
              <div className="form-grid">
                <label className="form-label">
                  Status
                  <select
                    className="form-input"
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value as ReportStatus)}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-label form-grid-full">
                  Executive summary
                  <textarea
                    className="form-input"
                    rows={3}
                    value={editSummary}
                    onChange={(e) => setEditSummary(e.target.value)}
                  />
                </label>
                <label className="form-label form-grid-full">
                  Period highlights
                  <textarea
                    className="form-input"
                    rows={2}
                    value={editHighlights}
                    onChange={(e) => setEditHighlights(e.target.value)}
                  />
                </label>
                <label className="form-label form-grid-full">
                  Trends
                  <textarea
                    className="form-input"
                    rows={2}
                    value={editTrends}
                    onChange={(e) => setEditTrends(e.target.value)}
                  />
                </label>
                <label className="form-label form-grid-full">
                  Next month focus
                  <textarea
                    className="form-input"
                    rows={2}
                    value={editNextFocus}
                    onChange={(e) => setEditNextFocus(e.target.value)}
                  />
                </label>
                <label className="form-label form-grid-full">
                  Leadership asks
                  <textarea
                    className="form-input"
                    rows={2}
                    value={editAsks}
                    onChange={(e) => setEditAsks(e.target.value)}
                  />
                </label>
              </div>
              {editError && <div className="form-error">{editError}</div>}
              <div className="confirm-actions">
                <button className="btn btn-primary" type="submit" disabled={saving || busy}>
                  {saving ? "Saving..." : "Save"}
                </button>
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={busy}
                  onClick={() => void handleRefresh()}
                >
                  Refresh metrics
                </button>
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={busy}
                  onClick={() => void handleDownload("pdf")}
                >
                  Download PDF
                </button>
                <button
                  className="btn btn-ghost"
                  type="button"
                  disabled={busy}
                  onClick={() => void handleDownload("xlsx")}
                >
                  Download Excel
                </button>
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => {
                    setEditingId(null);
                    setDetail(null);
                  }}
                >
                  Close
                </button>
              </div>
            </form>
          )}
          {!canWrite && (
            <div className="confirm-actions">
              <button
                className="btn btn-ghost"
                type="button"
                disabled={busy}
                onClick={() => void handleDownload("pdf")}
              >
                Download PDF
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                disabled={busy}
                onClick={() => void handleDownload("xlsx")}
              >
                Download Excel
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => {
                  setEditingId(null);
                  setDetail(null);
                }}
              >
                Close
              </button>
            </div>
          )}
          {detail && <SectionsView detail={detail} />}
        </div>
      )}

      {status === "loading" && <div className="state-message">Loading reports...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}
      {status === "success" && data && (
        data.reports.length === 0 ? (
          <div className="state-message">No reports yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Title</th>
                <th>Month</th>
                <th>Status</th>
                <th>Published</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.reports.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.tenant_name} ({row.short_code})
                  </td>
                  <td>{row.title}</td>
                  <td>{row.report_month}</td>
                  <td>
                    <span className={`badge badge-${row.status}`}>{row.status}</span>
                  </td>
                  <td>{row.published_at ?? "—"}</td>
                  <td>{row.created_at}</td>
                  <td>
                    <button className="btn btn-small" type="button" onClick={() => openEdit(row)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
