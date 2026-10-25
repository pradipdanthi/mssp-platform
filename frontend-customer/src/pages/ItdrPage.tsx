import { FormEvent, Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ItdrConfig,
  ItdrEvent,
  ItdrRemediateResult,
  ItdrSummary,
  connectItdrProvider,
  getCustomerEntitlements,
  getItdrConfigs,
  getItdrEvents,
  getItdrSummary,
  remediateItdrIdentity,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import RadialGauge from "../components/RadialGauge";

const SEV_FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

function eventTypeLabel(t: string): string {
  return t.replace(/_/g, " ");
}

/**
 * Cloud & Identity Threat Protection — customer SaaS identity view.
 * Engine label: MSSP Cloud Identity Protection Engine.
 */
export default function ItdrPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const isAdmin = user?.role === "customer_admin";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [summary, setSummary] = useState<ItdrSummary | null>(null);
  const [events, setEvents] = useState<ItdrEvent[]>([]);
  const [configs, setConfigs] = useState<ItdrConfig[]>([]);
  const [severity, setSeverity] = useState("ALL");
  const [showModal, setShowModal] = useState(false);
  const [domain, setDomain] = useState("");
  const [seats, setSeats] = useState("25");
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [remediatingId, setRemediatingId] = useState<string | null>(null);
  const [remediateResult, setRemediateResult] = useState<ItdrRemediateResult | null>(null);

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
      getItdrSummary(shortCode),
      getItdrEvents(shortCode, { page_size: 100 }),
      getItdrConfigs(shortCode),
    ])
      .then(([ent, sum, evRes, cfgRes]) => {
        setEnabled(Boolean(ent.cloud_identity_protection_enabled || sum.has_data));
        setSummary(sum);
        setEvents(evRes.events || []);
        setConfigs(cfgRes.configs || []);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load identity protection data.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getItdrEvents(shortCode, {
      severity: severity === "ALL" ? undefined : severity,
      page_size: 100,
    })
      .then((res) => setEvents(res.events || []))
      .catch(() => undefined);
  }, [shortCode, severity, enabled]);

  async function onContainIdentity(ev: ItdrEvent) {
    if (!shortCode || !isAdmin) return;
    const ok = window.confirm(
      `Contain identity for ${ev.user_principal_name}?\n\n` +
        "This will in Microsoft Entra:\n" +
        "1) Revoke all sessions\n" +
        "2) Set a temporary password (force change at next sign-in)\n" +
        "3) Disable the account\n\n" +
        "Only your designated admin should do this. Continue?"
    );
    if (!ok) return;
    setRemediatingId(ev.id);
    setError(null);
    setRemediateResult(null);
    try {
      const res = await remediateItdrIdentity(shortCode, {
        user_principal_name: ev.user_principal_name,
        event_id: ev.id,
        revoke_sessions: true,
        reset_password: true,
        disable_account: true,
        confirm: true,
      });
      setRemediateResult(res);
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Identity containment failed.");
    } finally {
      setRemediatingId(null);
    }
  }

  async function onConnect(e: FormEvent) {
    e.preventDefault();
    if (!shortCode || !domain.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await connectItdrProvider(shortCode, {
        provider: "M365_ENTRA",
        tenant_domain: domain.trim(),
        monitored_seat_count: Math.max(1, parseInt(seats || "25", 10) || 25),
        run_sync: true,
      });
      setShowModal(false);
      setDomain("");
      loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not connect cloud identity tenant.");
    } finally {
      setSubmitting(false);
    }
  }

  function renderModal() {
    return (
      <div className="modal-backdrop" role="dialog" aria-modal="true">
        <div className="modal-panel">
          <h2 className="panel-title">Connect Microsoft 365 Tenant</h2>
          <p className="muted">
            Register your Microsoft 365 / Entra ID domain for monitoring by the{" "}
            {summary?.engine_label || "MSSP Cloud Identity Protection Engine"}.
          </p>
          <form onSubmit={onConnect} className="form-stack">
            <label>
              Tenant domain
              <input
                value={domain}
                onChange={(ev) => setDomain(ev.target.value)}
                placeholder="contoso.com"
                required
                autoFocus
              />
            </label>
            <label>
              Approximate monitored seats
              <input
                type="number"
                min={1}
                value={seats}
                onChange={(ev) => setSeats(ev.target.value)}
              />
            </label>
            <div className="page-header-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setShowModal(false)}
                disabled={submitting}
              >
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? "Connecting…" : "Connect & analyze"}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Cloud & Identity</h1>
        <p className="muted">Loading identity protection…</p>
      </div>
    );
  }

  if (!enabled && !summary?.has_data) {
    return (
      <div className="page">
        <h1 className="page-title">Cloud & Identity</h1>
        <p className="page-lead">
          Monitor Microsoft 365 / Entra ID for impossible travel, MFA abuse, rogue admins, and
          risky mail forwarding.
        </p>
        {error && <p className="form-error">{error}</p>}
        <div className="panel">
          <p>
            Cloud identity monitoring is not connected yet.{" "}
            {isAdmin ? (
              <>Use <strong>Connect Microsoft 365 Tenant</strong> to begin.</>
            ) : (
              <>
                Ask a customer admin to connect your tenant, or request the service from{" "}
                <Link to="/services">Service Portfolio</Link>.
              </>
            )}
          </p>
          {isAdmin && (
            <button type="button" className="btn btn-primary" onClick={() => setShowModal(true)}>
              Connect Microsoft 365 Tenant
            </button>
          )}
        </div>
        {showModal && renderModal()}
      </div>
    );
  }

  const posture = Math.round(Number(summary?.identity_posture_score || 0));

  return (
    <div className="page itdr-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Cloud & Identity</h1>
          <p className="page-lead">
            Identity threats detected by the{" "}
            {summary?.engine_label || "MSSP Cloud Identity Protection Engine"}.
          </p>
        </div>
        {isAdmin && (
          <button type="button" className="btn btn-primary" onClick={() => setShowModal(true)}>
            Connect Microsoft 365 Tenant
          </button>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}
      {remediateResult && (
        <div className="panel" style={{ borderColor: "rgba(16, 185, 129, 0.45)" }}>
          <h2 className="panel-title">Identity containment completed</h2>
          <p>
            User <strong>{remediateResult.upn}</strong> — steps:{" "}
            {(remediateResult.steps || []).map((s) => s.action).join(", ")}
          </p>
          {remediateResult.temporary_password && (
            <>
              <p>
                <strong>Temporary password</strong> (shown once — copy now, share out-of-band only after
                re-enabling the account):
              </p>
              <code
                style={{
                  display: "block",
                  padding: "0.75rem",
                  background: "rgba(15, 23, 42, 0.8)",
                  borderRadius: 8,
                  userSelect: "all",
                }}
              >
                {remediateResult.temporary_password}
              </code>
              <p className="muted">{remediateResult.password_note}</p>
            </>
          )}
          {remediateResult.next_steps && (
            <ul>
              {remediateResult.next_steps.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <button type="button" className="btn btn-secondary" onClick={() => setRemediateResult(null)}>
            Dismiss
          </button>
        </div>
      )}

      <section className="compliance-hero panel">
        <div className="compliance-hero-gauge">
          <RadialGauge percent={posture} label="Identity posture" size={110} />
          <div>
            <div className="compliance-hero-label">Identity posture score</div>
            <div className="compliance-hero-score">{posture}%</div>
            <p className="muted">
              {summary?.monitored_cloud_seats ?? 0} seats monitored ·{" "}
              {summary?.connected_providers ?? 0} provider
              {(summary?.connected_providers || 0) === 1 ? "" : "s"} connected
            </p>
          </div>
        </div>
      </section>

      <section className="easm-kpi-grid">
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Monitored cloud seats</div>
          <div className="easm-kpi-value">{summary?.monitored_cloud_seats ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Identity threat alerts</div>
          <div className="easm-kpi-value">{summary?.identity_threat_alerts ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Suspicious logins</div>
          <div className="easm-kpi-value">{summary?.suspicious_logins ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Risky mail rules</div>
          <div className="easm-kpi-value">{summary?.risky_mail_rules ?? 0}</div>
        </div>
      </section>

      {configs.length > 0 && (
        <section className="panel">
          <h2 className="panel-title">Connected identity tenants</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Domain</th>
                  <th>Seats</th>
                  <th>Status</th>
                  <th>Last sync</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr key={c.id}>
                    <td>{c.provider_label}</td>
                    <td>{c.tenant_domain}</td>
                    <td>{c.monitored_seat_count}</td>
                    <td>{c.status}</td>
                    <td>{c.last_synced_at || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel">
        <h2 className="panel-title">Identity threat events</h2>
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
          <p className="muted">No open identity threats for this filter.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>User</th>
                  <th>Event</th>
                  <th>Location</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => {
                  const open = expanded === ev.id;
                  const loc = [ev.location_city, ev.location_country].filter(Boolean).join(", ");
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
                        <td>{ev.user_principal_name}</td>
                        <td>
                          <div>{ev.title || eventTypeLabel(ev.event_type)}</div>
                          <div className="muted">{eventTypeLabel(ev.event_type)}</div>
                        </td>
                        <td>{loc || "—"}</td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={4}>
                            <div className="compliance-remediation">
                              <strong>What happened</strong>
                              <p>{ev.summary}</p>
                              <strong>Remediation</strong>
                              <p>{ev.remediation}</p>
                              {isAdmin && (
                                <div style={{ marginTop: "0.75rem" }}>
                                  <button
                                    type="button"
                                    className="btn btn-danger"
                                    disabled={remediatingId === ev.id}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      void onContainIdentity(ev);
                                    }}
                                  >
                                    {remediatingId === ev.id
                                      ? "Containing in Entra…"
                                      : "Contain identity (revoke · reset · disable)"}
                                  </button>
                                  <p className="muted" style={{ marginTop: "0.35rem" }}>
                                    Runs in your Microsoft Entra tenant via consented Graph permissions.
                                    Your admin keeps control — this button is for designated customer admins.
                                  </p>
                                </div>
                              )}
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

      {showModal && renderModal()}
    </div>
  );
}
