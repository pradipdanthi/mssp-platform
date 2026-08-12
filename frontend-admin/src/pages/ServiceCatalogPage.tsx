import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  AdminCatalogService,
  Tenant,
  getAdminServiceCatalog,
  getTenants,
  patchCatalogPricing,
  rolloutCatalogService,
} from "../api/admin";
import { getCatalogItem } from "../data/serviceCatalog";

type PriceForm = {
  pricing_display: string;
  pricing_notes: string;
  competitor_value: string;
};

export default function ServiceCatalogPage() {
  const [services, setServices] = useState<AdminCatalogService[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "core" | "addons" | "requests">("all");

  const [priceItem, setPriceItem] = useState<AdminCatalogService | null>(null);
  const [priceForm, setPriceForm] = useState<PriceForm>({
    pricing_display: "",
    pricing_notes: "",
    competitor_value: "",
  });
  const [priceSaving, setPriceSaving] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);

  const [rolloutItem, setRolloutItem] = useState<AdminCatalogService | null>(null);
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);
  const [rolloutNotes, setRolloutNotes] = useState("");
  const [rolloutBusy, setRolloutBusy] = useState(false);
  const [rolloutError, setRolloutError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getAdminServiceCatalog(), getTenants({ page_size: 200 })])
      .then(([catalog, tenantRes]) => {
        setServices(catalog.services || []);
        setTenants(tenantRes.tenants || []);
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
  }, []);

  const filtered = useMemo(() => {
    return services.filter((s) => {
      if (filter === "core") return s.is_core;
      if (filter === "addons") return !s.is_core;
      if (filter === "requests") return s.open_request_count > 0;
      return true;
    });
  }, [services, filter]);

  const openTotal = useMemo(
    () => services.reduce((n, s) => n + (s.open_request_count || 0), 0),
    [services]
  );

  function openPriceEditor(item: AdminCatalogService) {
    setPriceItem(item);
    setPriceForm({
      pricing_display: item.pricing_display || "",
      pricing_notes: item.pricing_notes || "",
      competitor_value: item.competitor_value || "",
    });
    setPriceError(null);
  }

  async function savePrice(e: FormEvent) {
    e.preventDefault();
    if (!priceItem) return;
    if (!priceForm.pricing_display.trim()) {
      setPriceError("List price is required.");
      return;
    }
    setPriceSaving(true);
    setPriceError(null);
    try {
      await patchCatalogPricing(priceItem.service_key, {
        pricing_display: priceForm.pricing_display.trim(),
        pricing_notes: priceForm.pricing_notes.trim() || null,
        competitor_value: priceForm.competitor_value.trim() || null,
      });
      setSuccess(`Updated list price for ${priceItem.service_name}.`);
      setPriceItem(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setPriceError(err.detail);
      else setPriceError("Could not save pricing.");
    } finally {
      setPriceSaving(false);
    }
  }

  function openRollout(item: AdminCatalogService) {
    setRolloutItem(item);
    setSelectedTenantIds([]);
    setRolloutNotes("");
    setRolloutError(null);
  }

  function toggleTenant(id: string) {
    setSelectedTenantIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function submitRollout(e: FormEvent) {
    e.preventDefault();
    if (!rolloutItem) return;
    if (!selectedTenantIds.length) {
      setRolloutError("Select at least one customer.");
      return;
    }
    setRolloutBusy(true);
    setRolloutError(null);
    try {
      const res = await rolloutCatalogService(rolloutItem.service_key, {
        tenant_ids: selectedTenantIds,
        admin_notes: rolloutNotes.trim() || null,
        mark_requests_approved: true,
      });
      setSuccess(
        `Rolled out ${rolloutItem.service_name} to ${res.rolled_out} customer(s)` +
          (res.failed ? ` (${res.failed} failed)` : "") +
          "."
      );
      setRolloutItem(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setRolloutError(err.detail);
      else setRolloutError("Rollout failed.");
    } finally {
      setRolloutBusy(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Service Catalog</h1>
      <p className="page-subtitle">
        MSSP portfolio control — review offerings, edit list pricing, roll services out to customers,
        and act on consultation demand. Customer self-service consulting requests stay in the
        customer portal. Global queue: <Link to="/service-requests">Service Requests</Link>.
      </p>

      <div className="catalog-toolbar">
        <div className="catalog-filters">
          {(
            [
              ["all", "All services"],
              ["core", "Core"],
              ["addons", "Add-ons"],
              ["requests", "Has open requests"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={"btn btn-ghost" + (filter === key ? " is-active-filter" : "")}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {openTotal > 0 && (
          <Link className="catalog-open-strip" to="/service-requests?status=PENDING_CONSULTATION">
            <span className="request-pulse-dot" aria-hidden="true" />
            {openTotal} open customer request{openTotal === 1 ? "" : "s"} across the catalog
          </Link>
        )}
      </div>

      {loading && <div className="state-message">Loading catalog…</div>}
      {error && <div className="state-message state-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {!loading && (
        <div className="services-catalog">
          {filtered.map((item) => {
            const meta = getCatalogItem(item.service_key as never);
            const features = meta?.features?.slice(0, 4) || [];
            const summary = meta?.achieves || "";
            return (
              <article
                key={item.service_key}
                className={
                  "service-card glass-card" +
                  (item.open_request_count > 0 ? " service-card--has-requests" : "")
                }
              >
                <div className="service-card-top">
                  <h2 className="service-card-title">{item.service_name}</h2>
                  <div className="service-card-badges">
                    <span className={"service-status service-status--" + (item.is_core ? "included" : "available")}>
                      {item.is_core ? "Core" : "Add-on"}
                    </span>
                    {item.open_request_count > 0 && (
                      <Link
                        className="service-request-badge"
                        to={`/service-requests?service_key=${encodeURIComponent(item.service_key)}`}
                        title="Open customer requests for this service"
                      >
                        <span className="request-pulse-dot" aria-hidden="true" />
                        {item.open_request_count} request
                        {item.open_request_count === 1 ? "" : "s"}
                      </Link>
                    )}
                  </div>
                </div>

                <div className="service-pricing">
                  <strong>{item.pricing_display}</strong>
                  {item.competitor_value && (
                    <span className="service-pricing-comp">{item.competitor_value}</span>
                  )}
                </div>
                <p className="service-card-meta">
                  <strong>{item.active_tenant_count}</strong> active customer
                  {item.active_tenant_count === 1 ? "" : "s"}
                </p>
                {summary && <p className="service-card-summary">{summary}</p>}
                {features.length > 0 && (
                  <ul className="service-benefits">
                    {features.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                )}

                {item.open_requests.length > 0 && (
                  <div className="service-request-list">
                    <div className="service-request-list-label">Recent open requests</div>
                    {item.open_requests.slice(0, 3).map((r) => (
                      <Link
                        key={r.id}
                        className="service-request-row"
                        to={`/tenants?q=${encodeURIComponent(r.short_code || "")}`}
                      >
                        <span>{r.tenant_name || r.short_code || "Customer"}</span>
                        <span className="cell-mono">{r.status.replace(/_/g, " ")}</span>
                      </Link>
                    ))}
                  </div>
                )}

                <div className="service-card-actions">
                  <button
                    className="btn btn-ghost"
                    type="button"
                    onClick={() => openPriceEditor(item)}
                  >
                    Edit price
                  </button>
                  {item.rollout_supported && (
                    <button
                      className="btn btn-primary"
                      type="button"
                      onClick={() => openRollout(item)}
                    >
                      Roll out to customers
                    </button>
                  )}
                  {item.open_request_count > 0 && (
                    <Link
                      className="btn btn-ghost"
                      to={`/service-requests?service_key=${encodeURIComponent(item.service_key)}`}
                    >
                      View requests
                    </Link>
                  )}
                </div>
              </article>
            );
          })}
          {filtered.length === 0 && (
            <div className="state-message">No services match this filter.</div>
          )}
        </div>
      )}

      {priceItem && (
        <div className="modal-backdrop" onClick={() => !priceSaving && setPriceItem(null)}>
          <form className="modal-panel" onSubmit={savePrice} onClick={(e) => e.stopPropagation()}>
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Edit list price — {priceItem.service_name}
            </h2>
            <p className="page-subtitle">
              Updates the price shown on Admin and Customer Service Catalogs. Does not invent
              discounts per tenant.
            </p>
            <label className="form-label" style={{ display: "block" }}>
              List price display
              <input
                className="form-input"
                required
                maxLength={200}
                value={priceForm.pricing_display}
                onChange={(e) => setPriceForm({ ...priceForm, pricing_display: e.target.value })}
              />
            </label>
            <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
              Competitor / packaging note (optional)
              <input
                className="form-input"
                maxLength={400}
                value={priceForm.competitor_value}
                onChange={(e) => setPriceForm({ ...priceForm, competitor_value: e.target.value })}
              />
            </label>
            <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
              Internal pricing notes (optional)
              <textarea
                className="form-input"
                rows={3}
                maxLength={2000}
                value={priceForm.pricing_notes}
                onChange={(e) => setPriceForm({ ...priceForm, pricing_notes: e.target.value })}
              />
            </label>
            {priceError && <div className="form-error">{priceError}</div>}
            <div className="confirm-actions">
              <button className="btn btn-primary" type="submit" disabled={priceSaving}>
                {priceSaving ? "Saving…" : "Save price"}
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                disabled={priceSaving}
                onClick={() => setPriceItem(null)}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {rolloutItem && (
        <div className="modal-backdrop" onClick={() => !rolloutBusy && setRolloutItem(null)}>
          <form
            className="modal-panel modal-panel--wide"
            onSubmit={submitRollout}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Roll out — {rolloutItem.service_name}
            </h2>
            <p className="page-subtitle">
              Enables this add-on for selected customers and marks their open consulting requests as
              approved.
            </p>
            <div className="rollout-tenant-list">
              {tenants.map((t) => (
                <label key={t.id} className="rollout-tenant-row">
                  <input
                    type="checkbox"
                    checked={selectedTenantIds.includes(t.id)}
                    onChange={() => toggleTenant(t.id)}
                  />
                  <span>
                    {t.name} <span className="cell-mono">({t.short_code})</span>
                  </span>
                </label>
              ))}
              {tenants.length === 0 && <div className="state-message">No tenants found.</div>}
            </div>
            <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
              Notes (optional)
              <textarea
                className="form-input"
                rows={3}
                value={rolloutNotes}
                onChange={(e) => setRolloutNotes(e.target.value)}
              />
            </label>
            {rolloutError && <div className="form-error">{rolloutError}</div>}
            <div className="confirm-actions">
              <button className="btn btn-primary" type="submit" disabled={rolloutBusy}>
                {rolloutBusy
                  ? "Rolling out…"
                  : `Enable for ${selectedTenantIds.length || 0} customer(s)`}
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                disabled={rolloutBusy}
                onClick={() => setRolloutItem(null)}
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
