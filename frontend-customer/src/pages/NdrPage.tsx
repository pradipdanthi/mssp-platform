import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  NdrEvent,
  NdrSensor,
  NdrSummary,
  getCustomerEntitlements,
  getNdrEvents,
  getNdrSensors,
  getNdrSummary,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const SEV_FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

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
 * Network Detection & Response — customer network threat view.
 * Engine label: MSSP Network Detection & Response Engine.
 * Endpoint labels only (no raw IPs).
 */
export default function NdrPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [summary, setSummary] = useState<NdrSummary | null>(null);
  const [events, setEvents] = useState<NdrEvent[]>([]);
  const [sensors, setSensors] = useState<NdrSensor[]>([]);
  const [severity, setSeverity] = useState("ALL");
  const [tab, setTab] = useState<"events" | "sensors">("events");
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
      getNdrSummary(shortCode),
      getNdrEvents(shortCode, { page_size: 100 }),
      getNdrSensors(shortCode),
    ])
      .then(([ent, sum, evRes, sensorRes]) => {
        setEnabled(Boolean(ent.network_traffic_analysis_enabled || sum.has_data));
        setSummary(sum);
        setEvents(evRes.events || []);
        setSensors(sensorRes.sensors || []);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load network detection data.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getNdrEvents(shortCode, {
      severity: severity === "ALL" ? undefined : severity,
      page_size: 100,
    })
      .then((res) => setEvents(res.events || []))
      .catch(() => undefined);
  }, [shortCode, severity, enabled]);

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Network Detection & Response</h1>
        <p className="muted">Loading network telemetry…</p>
      </div>
    );
  }

  if (!enabled && !summary?.has_data) {
    return (
      <div className="page">
        <h1 className="page-title">Network Detection & Response</h1>
        <p className="page-lead">
          Monitor lateral movement, DNS anomalies, TLS risks, and suspicious network flows.
        </p>
        {error && <p className="form-error">{error}</p>}
        <div className="panel">
          <p>
            Network Detection &amp; Response is not active yet. Request it from your{" "}
            <Link to="/services">Service Portfolio</Link>, or ask your MSSP to enable network
            sensors for this tenant.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page ndr-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Network Detection & Response</h1>
          <p className="page-lead">
            Network threats detected by the{" "}
            {summary?.engine_label || "MSSP Network Detection & Response Engine"}.
          </p>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}

      <section className="easm-kpi-grid">
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Active network sensors</div>
          <div className="easm-kpi-value">{summary?.active_network_sensors ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">High-risk network alerts</div>
          <div className="easm-kpi-value">{summary?.high_risk_network_alerts ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Monitored flows</div>
          <div className="easm-kpi-value">
            {(summary?.monitored_flows ?? 0).toLocaleString()}
          </div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Protocol anomalies</div>
          <div className="easm-kpi-value">{summary?.protocol_anomaly_count ?? 0}</div>
        </div>
      </section>

      <p className="muted">
        Bandwidth observed: {formatBytes(summary?.monitored_bytes || 0)} · Open events:{" "}
        {summary?.open_events ?? 0}
      </p>

      <div className="tab-row" style={{ marginBottom: 12 }}>
        <button
          type="button"
          className={"tab-btn" + (tab === "events" ? " active" : "")}
          onClick={() => setTab("events")}
        >
          Network events
        </button>
        <button
          type="button"
          className={"tab-btn" + (tab === "sensors" ? " active" : "")}
          onClick={() => setTab("sensors")}
        >
          Sensor status & coverage
        </button>
      </div>

      {tab === "sensors" ? (
        <section className="panel">
          <h2 className="panel-title">Sensor status & coverage</h2>
          {sensors.length === 0 ? (
            <p className="muted">No sensors registered.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Sensor</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Interface</th>
                    <th>Flows</th>
                    <th>Volume</th>
                    <th>Last heartbeat</th>
                  </tr>
                </thead>
                <tbody>
                  {sensors.map((s) => (
                    <tr key={s.id}>
                      <td>{s.sensor_name}</td>
                      <td>{s.sensor_type_label}</td>
                      <td>{s.sensor_status}</td>
                      <td>{s.capture_interface || "—"}</td>
                      <td>{Number(s.flows_observed || 0).toLocaleString()}</td>
                      <td>{formatBytes(Number(s.bytes_observed || 0))}</td>
                      <td>{s.last_heartbeat || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : (
        <section className="panel">
          <h2 className="panel-title">Network threat events</h2>
          <div className="tab-row">
            {SEV_FILTERS.map((s) => (
              <button
                key={s}
                type="button"
                className={"tab-btn" + (severity === s ? " active" : "")}
                onClick={() => setSeverity(s)}
              >
                {s === "ALL" ? "All severities" : s}
              </button>
            ))}
          </div>
          {events.length === 0 ? (
            <p className="muted">No open network events for this filter.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Event</th>
                    <th>Source → Destination</th>
                    <th>Protocol</th>
                    <th>ATT&CK</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => {
                    const open = expanded === ev.id;
                    const path = `${ev.source_endpoint_label}${
                      ev.source_port != null ? `:${ev.source_port}` : ""
                    } → ${ev.destination_endpoint_label}${
                      ev.destination_port != null ? `:${ev.destination_port}` : ""
                    }`;
                    return (
                      <Fragment key={ev.id}>
                        <tr
                          className="clickable-row"
                          onClick={() => setExpanded(open ? null : ev.id)}
                        >
                          <td>
                            <span className={`severity-pill severity-${ev.severity.toLowerCase()}`}>
                              {ev.severity}
                            </span>
                          </td>
                          <td>
                            <div>{ev.signature_title}</div>
                            <div className="muted">{ev.event_category.replace(/_/g, " ")}</div>
                          </td>
                          <td>{path}</td>
                          <td>{ev.protocol}</td>
                          <td>{ev.mitre_technique || "—"}</td>
                        </tr>
                        {open && (
                          <tr className="detail-row">
                            <td colSpan={5}>
                              <div className="compliance-remediation">
                                <strong>What happened</strong>
                                <p>{ev.summary}</p>
                                <strong>Recommended containment</strong>
                                <p>{ev.remediation}</p>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
