import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  ConsultationRequest,
  CustomerEntitlements,
  createConsultationRequest,
  getCustomerEntitlements,
  listConsultationRequests,
} from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import {
  SERVICE_CATALOG,
  ServiceCatalogItem,
  formatScopeSummary,
  resolveServiceStatus,
  statusLabel,
} from "../data/serviceCatalog";

type ConsultForm = {
  endpoint_count: string;
  m365_seat_count: string;
  target_domains: string;
  scope_notes: string;
};

const EMPTY_FORM: ConsultForm = {
  endpoint_count: "",
  m365_seat_count: "",
  target_domains: "",
  scope_notes: "",
};

const OPEN_STATUSES = new Set(["PENDING_CONSULTATION", "UNDER_REVIEW"]);

export default function ServicesPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [ent, setEnt] = useState<CustomerEntitlements | null>(null);
  const [requests, setRequests] = useState<ConsultationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<ServiceCatalogItem | null>(null);
  const [form, setForm] = useState<ConsultForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function refresh() {
    if (!shortCode) return;
    Promise.all([getCustomerEntitlements(shortCode), listConsultationRequests(shortCode)])
      .then(([e, r]) => {
        setEnt(e);
        setRequests(r.requests || []);
        setError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
        else setError("Could not load the service portfolio for your organization.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (!shortCode) {
      setLoading(false);
      setError("This account is not linked to a customer organization.");
      return;
    }
    setLoading(true);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  const openRequestKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const r of requests) {
      if (OPEN_STATUSES.has(r.status)) keys.add(r.service_key);
    }
    return keys;
  }, [requests]);

  function openConsult(item: ServiceCatalogItem) {
    setActiveItem(item);
    setForm(EMPTY_FORM);
    setFormError(null);
    setSuccess(null);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!shortCode || !activeItem) return;
    const notes = form.scope_notes.trim();
    if (notes.length < 8) {
      setFormError("Please add a short note about what you need (at least 8 characters).");
      return;
    }
    const domains = form.target_domains
      .split(/[\s,;]+/)
      .map((d) => d.trim())
      .filter(Boolean);
    if (activeItem.scopeFields.includes("domains") && domains.length === 0) {
      setFormError("Enter at least one target domain for this service.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await createConsultationRequest(shortCode, {
        service_key: activeItem.serviceKey,
        service_name: activeItem.name,
        pricing_tier: activeItem.pricing,
        endpoint_count: form.endpoint_count ? Number(form.endpoint_count) : null,
        m365_seat_count: form.m365_seat_count ? Number(form.m365_seat_count) : null,
        target_domains: domains,
        scope_notes: notes,
        contact_name: user?.full_name || null,
        contact_email: user?.email || null,
      });
      setSuccess(
        `Request submitted for ${activeItem.name}. Your MSSP team will follow up. Track it under Incidents → Service Requests & Upgrades.`
      );
      setActiveItem(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setFormError(err.detail);
      else setFormError("Could not submit the consultation request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Service Portfolio</h1>
      <p className="page-subtitle">
        Transparent package of core and optional services. Request consulting on available add-ons —
        we capture scope, create a ticket, and notify our sales team.
      </p>

      {loading && <div className="state-message">Loading portfolio…</div>}
      {error && <div className="state-message state-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {!loading && !error && (
        <div className="services-catalog">
          {SERVICE_CATALOG.map((item) => {
            const status = resolveServiceStatus(item, ent, openRequestKeys);
            return (
              <article key={item.id} className={"service-card glass-card service-card--" + status}>
                <div className="service-card-top">
                  <h2 className="service-card-title">{item.name}</h2>
                  <span className={"service-status service-status--" + status}>
                    {statusLabel(status)}
                  </span>
                </div>
                <div className="service-pricing">
                  <strong>{item.pricing}</strong>
                  <span className="service-pricing-comp">{item.competitorValue}</span>
                </div>
                <p className="service-card-summary">
                  <strong>What it achieves.</strong> {item.achieves}
                </p>
                <p className="service-card-summary">
                  <strong>Where it fits.</strong> {item.whereItFits}
                </p>
                <ul className="service-benefits">
                  {item.features.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
                <div className="service-card-actions">
                  {item.learnMorePath && (status === "included" || status === "active") && (
                    <Link className="btn btn-ghost" to={item.learnMorePath}>
                      Open in portal
                    </Link>
                  )}
                  {(status === "included" || status === "active") &&
                    (item.extraLinks || []).map((link) => (
                      <Link key={link.path} className="btn btn-ghost" to={link.path}>
                        {link.label}
                      </Link>
                    ))}
                  {item.requestable && status === "available" && (
                    <button className="btn btn-primary" type="button" onClick={() => openConsult(item)}>
                      Request for Consulting
                    </button>
                  )}
                  {status === "requested" && (
                    <span className="service-card-note">
                      Request received — track under{" "}
                      <Link to="/incidents?tab=service-requests">Service Requests</Link>.
                    </span>
                  )}
                  {(status === "included" || status === "active") &&
                    !item.learnMorePath &&
                    !(item.extraLinks && item.extraLinks.length) && (
                    <span className="service-card-note">Part of your active service package.</span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {activeItem && (
        <div className="modal-backdrop" role="presentation" onClick={() => !submitting && setActiveItem(null)}>
          <form
            className="modal-panel upgrade-request-form"
            onSubmit={handleSubmit}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Request for Consulting — {activeItem.name}
            </h2>
            <p className="page-subtitle" style={{ marginTop: 0 }}>
              Tell us the target scope. We create a service ticket and notify sales. Enabling happens
              only after commercial agreement.
            </p>
            <div className="form-grid">
              {activeItem.scopeFields.includes("endpoints") && (
                <label className="form-label">
                  Estimated endpoints / devices
                  <input
                    className="form-input"
                    type="number"
                    min={0}
                    value={form.endpoint_count}
                    onChange={(e) => setForm({ ...form, endpoint_count: e.target.value })}
                    placeholder="e.g. 50"
                  />
                </label>
              )}
              {activeItem.scopeFields.includes("m365_seats") && (
                <label className="form-label">
                  Microsoft 365 / identity seats
                  <input
                    className="form-input"
                    type="number"
                    min={0}
                    value={form.m365_seat_count}
                    onChange={(e) => setForm({ ...form, m365_seat_count: e.target.value })}
                    placeholder="e.g. 120"
                  />
                </label>
              )}
              {activeItem.scopeFields.includes("domains") && (
                <label className="form-label" style={{ gridColumn: "1 / -1" }}>
                  Target domains
                  <input
                    className="form-input"
                    value={form.target_domains}
                    onChange={(e) => setForm({ ...form, target_domains: e.target.value })}
                    placeholder="example.com, api.example.com"
                    required
                  />
                </label>
              )}
            </div>
            <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
              Notes / requirements
              <textarea
                className="form-input"
                required
                minLength={8}
                rows={5}
                value={form.scope_notes}
                onChange={(e) => setForm({ ...form, scope_notes: e.target.value })}
                placeholder="Environment details, timeline, compliance drivers…"
              />
            </label>
            {formError && <div className="form-error">{formError}</div>}
            <div className="confirm-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                {submitting ? "Sending…" : "Submit request"}
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => setActiveItem(null)}
                disabled={submitting}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {!loading && requests.length > 0 && (
        <section className="management-panel" style={{ marginTop: "1.25rem" }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Recent service requests
          </h2>
          <p className="page-subtitle" style={{ marginTop: 0 }}>
            Full history lives under{" "}
            <Link to="/incidents?tab=service-requests">Incidents → Service Requests & Upgrades</Link>.
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Service</th>
                <th>Scope</th>
                <th>Status</th>
                <th>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {requests.slice(0, 5).map((r) => (
                <tr key={r.id}>
                  <td className="cell-mono">{r.id.slice(0, 8)}…</td>
                  <td>{r.service_name}</td>
                  <td>{formatScopeSummary(r)}</td>
                  <td>
                    <span className={"service-status service-status--" + r.status.toLowerCase()}>
                      {r.status}
                    </span>
                  </td>
                  <td className="cell-mono">{r.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
