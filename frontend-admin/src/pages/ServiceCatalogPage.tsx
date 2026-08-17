import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  AdminCatalogService,
  Tenant,
  getAdminServiceCatalog,
  getTenantAssetServiceCoverage,
  getTenants,
  patchCatalogPricing,
  rolloutCatalogService,
  type AssetServiceCoverageAsset,
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
  const [rolloutAction, setRolloutAction] = useState<"enable" | "disable">("enable");
  const [orderNumber, setOrderNumber] = useState("");
  const [confirmEmail, setConfirmEmail] = useState("");
  const [assetIds, setAssetIds] = useState<string[]>([]);
  const [assetOptions, setAssetOptions] = useState<AssetServiceCoverageAsset[]>([]);
  const [assetsLoading, setAssetsLoading] = useState(false);

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
    setRolloutAction("enable");
    setOrderNumber("");
    setConfirmEmail("");
    setAssetIds([]);
    setAssetOptions([]);
  }

  useEffect(() => {
    if (!rolloutItem || selectedTenantIds.length !== 1) {
      setAssetOptions([]);
      setAssetIds([]);
      return;
    }
    let cancelled = false;
    setAssetsLoading(true);
    getTenantAssetServiceCoverage(selectedTenantIds[0], rolloutItem.service_key)
      .then((res) => {
        if (cancelled) return;
        setAssetOptions(res.assets || []);
        setAssetIds(res.covered_asset_ids || []);
      })
      .catch(() => {
        if (!cancelled) setAssetOptions([]);
      })
      .finally(() => {
        if (!cancelled) setAssetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [rolloutItem, selectedTenantIds]);

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
    if (!orderNumber.trim()) {
      setRolloutError("Customer order number is required.");
      return;
    }
    if (!confirmEmail.trim() || !confirmEmail.includes("@")) {
      setRolloutError("Confirmation email is required.");
      return;
    }
    setRolloutBusy(true);
    setRolloutError(null);
    try {
      const res = await rolloutCatalogService(rolloutItem.service_key, {
        tenant_ids: selectedTenantIds,
        admin_notes: rolloutNotes.trim() || null,
        mark_requests_approved: rolloutAction === "enable",
        action: rolloutAction,
        customer_order_number: orderNumber.trim(),
        confirmation_email: confirmEmail.trim(),
        asset_ids: selectedTenantIds.length === 1 ? assetIds : [],
      });
      setSuccess(
        `${rolloutAction === "disable" ? "Disabled" : "Rolled out"} ${rolloutItem.service_name} for ${res.rolled_out} customer(s)` +
          (res.failed ? ` (${res.failed} failed)` : "") +
          ` · order ${orderNumber.trim()}.`
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
              Controlled change: customer order number and confirmation email are required. Leave
              assets unchecked for the whole account, or pick hosts when one customer is selected.
            </p>
            <label className="form-label">
              Action
              <select
                className="form-input"
                value={rolloutAction}
                onChange={(e) => setRolloutAction(e.target.value as "enable" | "disable")}
              >
                <option value="enable">Enable / roll out</option>
                <option value="disable">Disable / remove</option>
              </select>
            </label>
            <label className="form-label">
              Customer order number
              <input
                className="form-input"
                value={orderNumber}
                onChange={(e) => setOrderNumber(e.target.value)}
                placeholder="PO-10482 / SO-…"
                required
              />
            </label>
            <label className="form-label">
              Confirmation email
              <input
                className="form-input"
                type="email"
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                placeholder="customer.admin@example.com"
                required
              />
            </label>
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
            {selectedTenantIds.length === 1 ? (
              <div className="rollout-tenant-list" style={{ marginTop: "0.75rem" }}>
                <div className="form-label">Assets (optional — empty = whole account)</div>
                {assetsLoading && <div className="state-message">Loading assets…</div>}
                {!assetsLoading && assetOptions.length === 0 && (
                  <div className="state-message">No assets for this customer yet.</div>
                )}
                {assetOptions.map((a) => (
                  <label key={a.id} className="rollout-tenant-row">
                    <input
                      type="checkbox"
                      checked={assetIds.includes(a.id)}
                      onChange={() =>
                        setAssetIds((prev) =>
                          prev.includes(a.id) ? prev.filter((x) => x !== a.id) : [...prev, a.id]
                        )
                      }
                    />
                    <span>
                      {a.hostname || a.id}
                      {a.asset_type ? ` · ${a.asset_type}` : ""}
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="page-subtitle" style={{ marginTop: "0.75rem" }}>
                Select a single customer to target individual assets. Multiple customers apply at
                account level.
              </p>
            )}
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
                    ? "Saving…"
                    : `${rolloutAction === "disable" ? "Disable" : "Enable"} for ${selectedTenantIds.length || 0} customer(s)`}
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
