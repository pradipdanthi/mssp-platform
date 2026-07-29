import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  CustomerEntitlements,
  CustomerProtectedAsset,
  ServiceUpgradeRequest,
  ServiceUpgradeServiceKey,
  createServiceUpgradeRequest,
  getCustomerAssets,
  getCustomerEntitlements,
  listServiceUpgradeRequests,
} from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import {
  SERVICE_CATALOG,
  ServiceCatalogItem,
  resolveServiceStatus,
  statusLabel,
} from "../data/serviceCatalog";

type RequestForm = {
  urgency: "exploring" | "planning" | "needed_soon" | "urgent";
  requirements_summary: string;
  preferred_contact: "email" | "phone" | "either";
  contact_phone: string;
  preferred_cadence: "weekly" | "monthly" | "quarterly" | "unsure";
  selectedAssetIds: string[];
};

const EMPTY_FORM: RequestForm = {
  urgency: "planning",
  requirements_summary: "",
  preferred_contact: "email",
  contact_phone: "",
  preferred_cadence: "monthly",
  selectedAssetIds: [],
};

const OPEN_STATUSES = new Set(["submitted", "reviewing", "quoted"]);

export default function ServicesPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [ent, setEnt] = useState<CustomerEntitlements | null>(null);
  const [requests, setRequests] = useState<ServiceUpgradeRequest[]>([]);
  const [assets, setAssets] = useState<CustomerProtectedAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<ServiceCatalogItem | null>(null);
  const [form, setForm] = useState<RequestForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function refresh() {
    if (!shortCode) return;
    Promise.all([
      getCustomerEntitlements(shortCode),
      listServiceUpgradeRequests(shortCode),
      getCustomerAssets(shortCode),
    ])
      .then(([e, r, a]) => {
        setEnt(e);
        setRequests(r.requests || []);
        setAssets(a.assets || []);
        setError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
        else setError("Could not load services for your organization.");
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

  function openRequest(item: ServiceCatalogItem) {
    setActiveItem(item);
    setForm(EMPTY_FORM);
    setFormError(null);
    setSuccess(null);
  }

  function toggleAsset(id: string) {
    setForm((prev) => ({
      ...prev,
      selectedAssetIds: prev.selectedAssetIds.includes(id)
        ? prev.selectedAssetIds.filter((x) => x !== id)
        : [...prev.selectedAssetIds, id],
    }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!shortCode || !activeItem?.serviceKey) return;
    const needsAssets = activeItem.serviceKey === "vulnerability_management";
    if (needsAssets && form.selectedAssetIds.length === 0) {
      setFormError("Select at least one device for Vulnerability Management.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const serviceKey = activeItem.serviceKey as ServiceUpgradeServiceKey;
      await createServiceUpgradeRequest(shortCode, {
        service_key: serviceKey,
        preferred_cadence: form.preferred_cadence,
        scan_scope: serviceKey === "vulnerability_management" ? ["external_perimeter"] : [],
        environments: ["production"],
        urgency: form.urgency,
        compliance_drivers: [],
        requirements_summary: form.requirements_summary.trim(),
        preferred_contact: form.preferred_contact,
        contact_phone: form.contact_phone.trim() || null,
        requested_asset_ids: needsAssets ? form.selectedAssetIds : [],
        approximate_assets: needsAssets ? form.selectedAssetIds.length : null,
      });
      setSuccess(
        `Thanks — your request for ${activeItem.name}` +
          (needsAssets ? ` on ${form.selectedAssetIds.length} device(s)` : "") +
          ` was sent to your MSSP team.`
      );
      setActiveItem(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setFormError(err.detail);
      else setFormError("Could not submit the service request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Services</h1>
      <p className="page-subtitle">
        See what is included in your package, explore optional add-ons, and request upgrades. For
        Vulnerability Management you can pick specific devices — scanning does not have to cover
        your whole estate.
      </p>

      {loading && <div className="state-message">Loading services…</div>}
      {error && <div className="state-message state-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {!loading && !error && (
        <div className="services-catalog">
          {SERVICE_CATALOG.map((item) => {
            const status = resolveServiceStatus(item, ent, openRequestKeys);
            return (
              <article key={item.id} className={"service-card service-card--" + status}>
                <div className="service-card-top">
                  <h2 className="service-card-title">{item.name}</h2>
                  <span className={"service-status service-status--" + status}>
                    {statusLabel(status)}
                  </span>
                </div>
                <p className="service-card-summary">{item.summary}</p>
                <ul className="service-benefits">
                  {item.benefits.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
                <div className="service-card-actions">
                  {item.learnMorePath && (status === "included" || status === "active") && (
                    <Link className="btn btn-ghost" to={item.learnMorePath}>
                      Open in portal
                    </Link>
                  )}
                  {item.requestable && status === "available" && (
                    <button
                      className="btn btn-primary"
                      type="button"
                      onClick={() => openRequest(item)}
                    >
                      Request this service
                    </button>
                  )}
                  {status === "requested" && (
                    <span className="service-card-note">
                      Request received — your MSSP will follow up.
                    </span>
                  )}
                  {(status === "included" || status === "active") && !item.learnMorePath && (
                    <span className="service-card-note">Part of your active service package.</span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {activeItem && (
        <form className="management-panel upgrade-request-form" onSubmit={handleSubmit}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Request: {activeItem.name}
          </h2>
          <p className="page-subtitle" style={{ marginTop: 0 }}>
            Tell us what you need. Enabling happens only after commercial agreement with your MSSP.
          </p>

          {activeItem.serviceKey === "vulnerability_management" && (
            <fieldset className="upgrade-fieldset asset-picker">
              <legend>
                Devices to include in Vulnerability Management ({form.selectedAssetIds.length}{" "}
                selected)
              </legend>
              <p className="page-subtitle" style={{ marginTop: 0 }}>
                Pick only the hosts that should be scanned (for example 10 servers out of 200). Other
                devices stay on log monitoring only.
              </p>
              {assets.length === 0 ? (
                <div className="state-message">
                  No protected assets yet. Add/install endpoint agents under{" "}
                  <Link to="/assets">Assets</Link> first, then request this service.
                </div>
              ) : (
                <div className="asset-picker-list">
                  {assets.map((a) => (
                    <label key={a.asset_id} className="upgrade-check asset-picker-row">
                      <input
                        type="checkbox"
                        checked={form.selectedAssetIds.includes(a.asset_id)}
                        onChange={() => toggleAsset(a.asset_id)}
                      />
                      <span>
                        <strong>{a.hostname ?? "Unnamed asset"}</strong>
                        <span className="asset-picker-meta">
                          {a.asset_type}
                          {a.os_name ? ` · ${a.os_name}` : ""}
                          {a.status ? ` · ${a.status}` : ""}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </fieldset>
          )}

          <div className="form-grid">
            <label className="form-label">
              Urgency
              <select
                className="form-input"
                value={form.urgency}
                onChange={(e) =>
                  setForm({
                    ...form,
                    urgency: e.target.value as RequestForm["urgency"],
                  })
                }
              >
                <option value="exploring">Exploring / learning</option>
                <option value="planning">Planning for next quarter</option>
                <option value="needed_soon">Needed soon</option>
                <option value="urgent">Urgent</option>
              </select>
            </label>
            {activeItem.serviceKey === "vulnerability_management" && (
              <label className="form-label">
                Preferred scan cadence
                <select
                  className="form-input"
                  value={form.preferred_cadence}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      preferred_cadence: e.target.value as RequestForm["preferred_cadence"],
                    })
                  }
                >
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="unsure">Not sure yet</option>
                </select>
              </label>
            )}
            <label className="form-label">
              Preferred contact
              <select
                className="form-input"
                value={form.preferred_contact}
                onChange={(e) =>
                  setForm({
                    ...form,
                    preferred_contact: e.target.value as RequestForm["preferred_contact"],
                  })
                }
              >
                <option value="email">Email</option>
                <option value="phone">Phone</option>
                <option value="either">Either</option>
              </select>
            </label>
            <label className="form-label">
              Phone (if preferred)
              <input
                className="form-input"
                value={form.contact_phone}
                onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
              />
            </label>
          </div>
          <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
            What are you looking for?
            <textarea
              className="form-input"
              required
              minLength={10}
              rows={5}
              value={form.requirements_summary}
              onChange={(e) => setForm({ ...form, requirements_summary: e.target.value })}
              placeholder="Describe why these devices need scanning, compliance drivers, or timeline…"
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
      )}
    </div>
  );
}
