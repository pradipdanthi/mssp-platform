import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  ConsultationRequest,
  TenantEntitlements,
  createConsultationRequestOnBehalf,
  getTenantEntitlements,
  getTenants,
  listConsultationRequests,
  putTenantEntitlements,
  type Tenant,
} from "../api/admin";
import { getStoredTenantFilter } from "../components/TenantSwitcher";
import {
  SERVICE_CATALOG,
  ServiceCatalogItem,
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

export default function ServiceCatalogPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [shortCode, setShortCode] = useState(getStoredTenantFilter() || "");
  const [ent, setEnt] = useState<TenantEntitlements | null>(null);
  const [requests, setRequests] = useState<ConsultationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<ServiceCatalogItem | null>(null);
  const [form, setForm] = useState<ConsultForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [savingToggle, setSavingToggle] = useState<string | null>(null);

  const selectedTenant = useMemo(
    () => tenants.find((t) => t.short_code === shortCode) || null,
    [tenants, shortCode]
  );

  function refresh() {
    const pTenants = getTenants({ page_size: 200 });
    const pRequests = listConsultationRequests();
    Promise.all([pTenants, pRequests])
      .then(([tRes, rRes]) => {
        const list = tRes.tenants || [];
        setTenants(list);
        setRequests(rRes.requests || []);
        if (!shortCode && list.length) setShortCode(list[0].short_code);
        setError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
        else setError("Could not load service catalog.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedTenant) {
      setEnt(null);
      return;
    }
    getTenantEntitlements(selectedTenant.id)
      .then(setEnt)
      .catch(() => setEnt(null));
  }, [selectedTenant]);

  const openRequestKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const r of requests) {
      if (r.short_code === shortCode && OPEN_STATUSES.has(r.status)) keys.add(r.service_key);
    }
    return keys;
  }, [requests, shortCode]);

  async function toggleEntitlement(item: ServiceCatalogItem) {
    if (!selectedTenant || !ent) return;
    const patch: Partial<TenantEntitlements> = {};
    if (item.serviceKey === "vulnerability_management")
      patch.greenbone_enabled = !ent.greenbone_enabled;
    else if (item.serviceKey === "network_detection_response")
      patch.zeek_enabled = !ent.zeek_enabled;
    else if (item.serviceKey === "threat_intelligence") patch.misp_enabled = !ent.misp_enabled;
    else if (item.serviceKey === "endpoint_forensics_deception")
      patch.velociraptor_enabled = !ent.velociraptor_enabled;
    else if (item.serviceKey === "log_event_monitoring") patch.wazuh_siem = !ent.wazuh_siem;
    else return;
    setSavingToggle(item.id);
    try {
      const next = await putTenantEntitlements(selectedTenant.id, patch);
      setEnt(next);
      setSuccess(`Updated entitlements for ${selectedTenant.name}.`);
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
      else setError("Could not update entitlements.");
    } finally {
      setSavingToggle(null);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!activeItem || !shortCode) {
      setFormError("Select a customer tenant first.");
      return;
    }
    const notes = form.scope_notes.trim();
    if (notes.length < 8) {
      setFormError("Add at least 8 characters of scope notes.");
      return;
    }
    const domains = form.target_domains
      .split(/[\s,;]+/)
      .map((d) => d.trim())
      .filter(Boolean);
    setSubmitting(true);
    setFormError(null);
    try {
      await createConsultationRequestOnBehalf({
        tenant_short_code: shortCode,
        service_key: activeItem.serviceKey,
        service_name: activeItem.name,
        pricing_tier: activeItem.pricing,
        endpoint_count: form.endpoint_count ? Number(form.endpoint_count) : null,
        m365_seat_count: form.m365_seat_count ? Number(form.m365_seat_count) : null,
        target_domains: domains,
        scope_notes: notes,
      });
      setSuccess(`Consultation request created for ${selectedTenant?.name || shortCode}.`);
      setActiveItem(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setFormError(err.detail);
      else setFormError("Could not submit consultation request.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Service Catalog</h1>
      <p className="page-subtitle">
        Tenant-scoped portfolio view. Toggle supported entitlements and submit consulting requests on
        behalf of a customer. Global queue:{" "}
        <Link to="/service-requests">Service Requests</Link>.
      </p>

      <div className="form-grid" style={{ marginBottom: "1rem", maxWidth: 420 }}>
        <label className="form-label">
          Customer tenant
          <select
            className="form-input"
            value={shortCode}
            onChange={(e) => setShortCode(e.target.value)}
          >
            <option value="">Select tenant…</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.short_code}>
                {t.name} ({t.short_code})
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <div className="state-message">Loading catalog…</div>}
      {error && <div className="state-message state-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {!loading && (
        <div className="services-catalog">
          {SERVICE_CATALOG.map((item) => {
            const status = resolveServiceStatus(item, ent, openRequestKeys);
            const canToggle = [
              "log_event_monitoring",
              "vulnerability_management",
              "network_detection_response",
              "threat_intelligence",
              "endpoint_forensics_deception",
            ].includes(item.serviceKey);
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
                <p className="service-card-summary">{item.achieves}</p>
                <ul className="service-benefits">
                  {item.features.slice(0, 3).map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
                <div className="service-card-actions">
                  {canToggle && selectedTenant && (
                    <button
                      className="btn btn-ghost"
                      type="button"
                      disabled={!!savingToggle}
                      onClick={() => toggleEntitlement(item)}
                    >
                      {savingToggle === item.id ? "Saving…" : "Toggle entitlement"}
                    </button>
                  )}
                  {item.requestable && status === "available" && (
                    <button
                      className="btn btn-primary"
                      type="button"
                      disabled={!shortCode}
                      onClick={() => {
                        setActiveItem(item);
                        setForm(EMPTY_FORM);
                        setFormError(null);
                      }}
                    >
                      Request for Consulting
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {activeItem && (
        <div className="modal-backdrop" onClick={() => !submitting && setActiveItem(null)}>
          <form
            className="modal-panel"
            onSubmit={handleSubmit}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="section-title" style={{ marginTop: 0 }}>
              On-behalf request — {activeItem.name}
            </h2>
            <p className="page-subtitle">
              Tenant: <strong>{selectedTenant?.name || shortCode}</strong>
            </p>
            <div className="form-grid">
              {activeItem.scopeFields.includes("endpoints") && (
                <label className="form-label">
                  Endpoints
                  <input
                    className="form-input"
                    type="number"
                    min={0}
                    value={form.endpoint_count}
                    onChange={(e) => setForm({ ...form, endpoint_count: e.target.value })}
                  />
                </label>
              )}
              {activeItem.scopeFields.includes("m365_seats") && (
                <label className="form-label">
                  M365 seats
                  <input
                    className="form-input"
                    type="number"
                    min={0}
                    value={form.m365_seat_count}
                    onChange={(e) => setForm({ ...form, m365_seat_count: e.target.value })}
                  />
                </label>
              )}
              {activeItem.scopeFields.includes("domains") && (
                <label className="form-label" style={{ gridColumn: "1 / -1" }}>
                  Domains
                  <input
                    className="form-input"
                    value={form.target_domains}
                    onChange={(e) => setForm({ ...form, target_domains: e.target.value })}
                  />
                </label>
              )}
            </div>
            <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
              Notes
              <textarea
                className="form-input"
                required
                minLength={8}
                rows={4}
                value={form.scope_notes}
                onChange={(e) => setForm({ ...form, scope_notes: e.target.value })}
              />
            </label>
            {formError && <div className="form-error">{formError}</div>}
            <div className="confirm-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                {submitting ? "Sending…" : "Submit"}
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
    </div>
  );
}
