import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  downloadCustomerReportPdf,
  downloadCustomerReportXlsx,
  getCustomerReportDetail,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

export default function ReportDetailPage() {
  const { user } = useAuth();
  const { reportId } = useParams<{ reportId: string }>();
  const shortCode = user?.tenant_short_code ?? null;
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerReportDetail(shortCode as string, reportId as string),
    Boolean(shortCode && reportId),
    [shortCode, reportId]
  );
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleDownload(kind: "pdf" | "xlsx") {
    if (!shortCode || !reportId) return;
    setBusy(true);
    setDownloadError(null);
    try {
      if (kind === "pdf") await downloadCustomerReportPdf(shortCode, reportId);
      else await downloadCustomerReportXlsx(shortCode, reportId);
    } catch (err) {
      setDownloadError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Download failed."
      );
    } finally {
      setBusy(false);
    }
  }

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Report</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so report detail cannot be loaded.
        </div>
      </div>
    );
  }

  if (!reportId) {
    return (
      <div>
        <h1 className="page-title">Report</h1>
        <div className="state-message state-error">Report id is missing from the URL.</div>
        <p>
          <Link to="/reports">Back to reports</Link>
        </p>
      </div>
    );
  }

  const sections = (data?.report.sections || {}) as Record<string, any>;
  const posture = sections.posture || {};
  const detection = sections.detection || {};
  const incidents = sections.incidents || {};
  const recs = sections.recommendations || {};
  const notif = sections.notifications || {};
  const narrative = sections.narrative || {};
  const cover = sections.cover || {};
  const period = sections.period || {};

  return (
    <div>
      <p>
        <Link to="/reports">← Back to reports</Link>
      </p>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Monthly Security Report</h1>
          <p className="page-subtitle">
            Customer-safe monthly service summary with downloadable PDF and Excel.
          </p>
        </div>
        {status === "success" && (
          <div className="confirm-actions" style={{ marginTop: 0 }}>
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
          </div>
        )}
      </div>

      {downloadError && <div className="state-message state-error">{downloadError}</div>}
      {status === "loading" && <div className="state-message">Loading report...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage ?? "Report was not found."}</div>
      )}

      {status === "success" && data && (
        <>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Title</th>
                <td>{data.report.title}</td>
              </tr>
              <tr>
                <th>Customer</th>
                <td>
                  {String(cover.customer_name || data.tenant.name)} (
                  {String(cover.short_code || data.tenant.short_code)})
                </td>
              </tr>
              <tr>
                <th>Period</th>
                <td>{String(period.label || data.report.report_month)}</td>
              </tr>
              <tr>
                <th>SLA / Criticality</th>
                <td>
                  {String(cover.sla_level || "—")} / {String(cover.business_criticality || "—")}
                </td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{data.report.status}</td>
              </tr>
              <tr>
                <th>Published</th>
                <td>{data.report.published_at ?? "—"}</td>
              </tr>
            </tbody>
          </table>

          <h2 className="section-title">1. Executive summary</h2>
          <p>{data.report.summary ?? "—"}</p>

          <h2 className="section-title">2. Security posture</h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Appliances online / total</th>
                <td>
                  {String(posture.appliances_online ?? 0)} / {String(posture.appliances_total ?? 0)}
                </td>
              </tr>
              <tr>
                <th>Protected assets</th>
                <td>{String(posture.assets_total ?? 0)}</td>
              </tr>
            </tbody>
          </table>

          <h2 className="section-title">3. Detection volume</h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Alerts total</th>
                <td>{String(detection.alerts_total ?? 0)}</td>
              </tr>
              {Object.entries(detection.by_severity || {}).map(([k, v]) => (
                <tr key={k}>
                  <th>Severity {k}</th>
                  <td>{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2 className="section-title">4. Incident outcomes</h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Opened</th>
                <td>{String(incidents.opened ?? 0)}</td>
              </tr>
              <tr>
                <th>Closed</th>
                <td>{String(incidents.closed ?? 0)}</td>
              </tr>
              <tr>
                <th>Still open</th>
                <td>{String(incidents.still_open ?? 0)}</td>
              </tr>
            </tbody>
          </table>
          {(incidents.notable || []).length > 0 && (
            <>
              <h3 className="section-title">Notable incidents</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {(incidents.notable || []).map((item: Record<string, string>) => (
                    <tr key={item.incident_number}>
                      <td>{item.incident_number}</td>
                      <td>{item.title}</td>
                      <td>{item.severity}</td>
                      <td>{item.status}</td>
                      <td>{item.customer_visible_summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h2 className="section-title">5. Recommendations</h2>
          <p>
            Open {String(recs.open_count ?? 0)} · Completed {String(recs.completed_count ?? 0)}
          </p>
          {(recs.items || []).length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Category</th>
                </tr>
              </thead>
              <tbody>
                {(recs.items || []).map((item: Record<string, string>, idx: number) => (
                  <tr key={`${item.title}-${idx}`}>
                    <td>{item.title}</td>
                    <td>{item.priority}</td>
                    <td>{item.status}</td>
                    <td>{item.category}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="section-title">6. Notifications</h2>
          <p>
            Sent {String(notif.sent_count ?? 0)} · Delivered {String(notif.delivered_count ?? 0)}
          </p>

          <h2 className="section-title">7. Period narrative</h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Highlights</th>
                <td>{narrative.period_highlights || "—"}</td>
              </tr>
              <tr>
                <th>Trends</th>
                <td>{narrative.trends || "—"}</td>
              </tr>
              <tr>
                <th>Next month focus</th>
                <td>{narrative.next_month_focus || "—"}</td>
              </tr>
              <tr>
                <th>Leadership asks</th>
                <td>{narrative.leadership_asks || "—"}</td>
              </tr>
            </tbody>
          </table>

          {sections.deferred_kpis_note && (
            <p className="page-subtitle">{String(sections.deferred_kpis_note)}</p>
          )}
        </>
      )}
    </div>
  );
}
