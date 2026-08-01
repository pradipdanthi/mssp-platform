import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ForensicsCollection,
  ForensicsEvent,
  ForensicsSummary,
  ForensicsTripwire,
  getCustomerEntitlements,
  getForensicsCollections,
  getForensicsEvents,
  getForensicsSummary,
  getForensicsTripwires,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const SEV_FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

function formatBytes(n: number): string {
  if (!n || n < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/**
 * Endpoint Forensics & Deception — customer view.
 * Engine label: MSSP Endpoint Forensics & Deception Engine.
 */
export default function ForensicsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [summary, setSummary] = useState<ForensicsSummary | null>(null);
  const [tripwires, setTripwires] = useState<ForensicsTripwire[]>([]);
  const [events, setEvents] = useState<ForensicsEvent[]>([]);
  const [collections, setCollections] = useState<ForensicsCollection[]>([]);
  const [severity, setSeverity] = useState("ALL");
  const [tab, setTab] = useState<"events" | "tripwires" | "collections">("events");
  const [expanded, setExpanded] = useState<string | null>(null);

  function loadAll() {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing from session.");
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      getCustomerEntitlements(shortCode),
      getForensicsSummary(shortCode),
      getForensicsTripwires(shortCode),
      getForensicsEvents(shortCode, { page_size: 100 }),
      getForensicsCollections(shortCode),
    ])
      .then(([ent, sum, tw, evRes, col]) => {
        setEnabled(Boolean(ent.endpoint_forensics_enabled || sum.has_data));
        setSummary(sum);
        setTripwires(tw.tripwires || []);
        setEvents(evRes.events || []);
        setCollections(col.collections || []);
      })
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Unable to load endpoint forensics and deception data."
        );
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getForensicsEvents(shortCode, {
      severity: severity === "ALL" ? undefined : severity,
      page_size: 100,
    })
      .then((res) => setEvents(res.events || []))
      .catch(() => undefined);
  }, [shortCode, severity, enabled]);

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Endpoint Forensics & Deception</h1>
        <p className="muted">Loading deception and forensics posture…</p>
      </div>
    );
  }

  if (!enabled && !summary?.has_data) {
    return (
      <div className="page">
        <h1 className="page-title">Endpoint Forensics & Deception</h1>
        <p className="muted">
          This service is not active for your tenant yet. Request it from the{" "}
          <Link to="/services">Service Catalog</Link>, or ask your MSSP administrator to enable
          Endpoint Forensics & Deception Hunting.
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Endpoint Forensics & Deception</h1>
          <p className="muted">
            {summary?.engine_label || "MSSP Endpoint Forensics & Deception Engine"} — tripwire
            detections, isolation actions, and triage collections.
          </p>
        </div>
        <button type="button" className="btn secondary" onClick={loadAll}>
          Refresh
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="kpi-grid">
        <div className="stat-card">
          <div className="stat-label">Active tripwires</div>
          <div className="stat-value">{summary?.active_tripwires ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open deception events</div>
          <div className="stat-value">{summary?.open_deception_events ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">High-severity events</div>
          <div className="stat-value">{summary?.high_severity_events ?? 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Ready downloads</div>
          <div className="stat-value">{summary?.ready_downloads ?? 0}</div>
        </div>
      </div>

      <div className="tab-row">
        <button
          type="button"
          className={"tab-btn" + (tab === "events" ? " active" : "")}
          onClick={() => setTab("events")}
        >
          Deception events
        </button>
        <button
          type="button"
          className={"tab-btn" + (tab === "tripwires" ? " active" : "")}
          onClick={() => setTab("tripwires")}
        >
          Tripwires
        </button>
        <button
          type="button"
          className={"tab-btn" + (tab === "collections" ? " active" : "")}
          onClick={() => setTab("collections")}
        >
          Forensics collections
        </button>
      </div>

      {tab === "events" && (
        <>
          <div className="filter-row">
            {SEV_FILTERS.map((s) => (
              <button
                key={s}
                type="button"
                className={"chip" + (severity === s ? " active" : "")}
                onClick={() => setSeverity(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Event</th>
                  <th>Host</th>
                  <th>Isolation</th>
                  <th>Detected</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 && (
                  <tr>
                    <td colSpan={5} className="muted">
                      No open deception events.
                    </td>
                  </tr>
                )}
                {events.map((ev) => (
                  <Fragment key={ev.id}>
                    <tr
                      className="clickable-row"
                      onClick={() => setExpanded(expanded === ev.id ? null : ev.id)}
                    >
                      <td>
                        <span className={"severity-pill sev-" + ev.severity.toLowerCase()}>
                          {ev.severity}
                        </span>
                      </td>
                      <td>{ev.event_title}</td>
                      <td>{ev.host_label}</td>
                      <td>{ev.isolation_status.split("_").join(" ")}</td>
                      <td>{ev.detected_at ? new Date(ev.detected_at).toLocaleString() : "—"}</td>
                    </tr>
                    {expanded === ev.id && (
                      <tr className="detail-row">
                        <td colSpan={5}>
                          <p>
                            <strong>Actor:</strong> {ev.actor_label}
                          </p>
                          {ev.tripwire_name && (
                            <p>
                              <strong>Tripwire:</strong> {ev.tripwire_name}
                            </p>
                          )}
                          <p>{ev.summary}</p>
                          <p>
                            <strong>Recommended action:</strong> {ev.recommended_action}
                          </p>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "tripwires" && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Sensitivity</th>
                <th>Auto-isolate</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {tripwires.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    No active tripwires.
                  </td>
                </tr>
              )}
              {tripwires.map((tw) => (
                <Fragment key={tw.id}>
                  <tr
                    className="clickable-row"
                    onClick={() => setExpanded(expanded === tw.id ? null : tw.id)}
                  >
                    <td>{tw.tripwire_name}</td>
                    <td>{tw.tripwire_type.split("_").join(" ")}</td>
                    <td>{tw.sensitivity}</td>
                    <td>{tw.auto_isolate_on_trip ? "Yes" : "No"}</td>
                    <td>{tw.deployment_status}</td>
                  </tr>
                  {expanded === tw.id && (
                    <tr className="detail-row">
                      <td colSpan={5}>
                        <p>
                          <strong>Host label:</strong> {tw.host_label}
                        </p>
                        <p>{tw.summary}</p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "collections" && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Collection</th>
                <th>Scope</th>
                <th>Host</th>
                <th>Status</th>
                <th>Size</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {collections.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    No forensics collections yet.
                  </td>
                </tr>
              )}
              {collections.map((c) => (
                <Fragment key={c.id}>
                  <tr
                    className="clickable-row"
                    onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                  >
                    <td>{c.collection_name}</td>
                    <td>{c.collection_scope.split("_").join(" ")}</td>
                    <td>{c.host_label}</td>
                    <td>{c.status}</td>
                    <td>{formatBytes(c.package_size_bytes || 0)}</td>
                    <td>{c.download_available ? "Available" : "Not ready"}</td>
                  </tr>
                  {expanded === c.id && (
                    <tr className="detail-row">
                      <td colSpan={6}>
                        <p>{c.summary}</p>
                        {c.related_event_title && (
                          <p>
                            <strong>Related event:</strong> {c.related_event_title}
                          </p>
                        )}
                        <p className="muted">
                          Secure download links are issued by your MSSP analyst when the package is
                          approved for customer retrieval.
                        </p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
