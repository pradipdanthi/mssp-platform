import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  AdminCatalogService,
  Tenant,
  getAdminServiceCatalog,
  getTenants,
  patchCatalogPricing,
} from "../api/admin";
import { getCatalogItem } from "../data/serviceCatalog";
import { includedInTierLabel, SERVICE_KEY_MIN_TIER } from "../data/tierCapabilityMap";
import { normalizeTier, tierDisplayName } from "../data/subscriptionTierMatrix";
import SubscriptionTierMatrix from "../components/SubscriptionTierMatrix";

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
  const [filter, setFilter] = useState<"all" | "silver" | "gold" | "platinum" | "requests">("all");

  const [priceItem, setPriceItem] = useState<AdminCatalogService | null>(null);
  const [priceForm, setPriceForm] = useState<PriceForm>({
    pricing_display: "",
    pricing_notes: "",
    competitor_value: "",
  });
  const [priceSaving, setPriceSaving] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);

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
      const minTier = SERVICE_KEY_MIN_TIER[s.service_key as keyof typeof SERVICE_KEY_MIN_TIER];
      if (filter === "silver") return minTier === "SILVER";
      if (filter === "gold") return minTier === "GOLD";
      if (filter === "platinum") return minTier === "PLATINUM";
      if (filter === "requests") return s.open_request_count > 0;
      return true;
    });
  }, [services, filter]);

  const tierCounts = useMemo(() => {
    const counts = { SILVER: 0, GOLD: 0, PLATINUM: 0, CUSTOM: 0 };
    for (const t of tenants) {
      const tier = normalizeTier(t.subscription_tier);
      counts[tier] += 1;
    }
    return counts;
  }, [tenants]);

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

  return (
    <div>
      <h1 className="page-title">Tier Operations</h1>
      <p className="page-subtitle">
        MSSP tier control — provision Silver / Gold / Platinum upgrades (or downgrades) and custom
        bundles via the provision pages above. Tier rollout syncs entitlements, cloud adapters, and
        NikTiar Edge licenses automatically. Per-module{" "}
        <code>POST /admin/service-catalog/&#123;key&#125;/rollout</code> is break-glass only (MSSP
        exceptions) — not shown in this UI. Customer tier upgrade requests:{" "}
        <Link to="/service-requests">Service Requests</Link>.
      </p>

      <div className="catalog-toolbar">
        <div className="catalog-filters">
          {(
            [
              ["all", "All modules"],
              ["silver", "Silver tier"],
              ["gold", "Gold tier"],
              ["platinum", "Platinum tier"],
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
        <section className="management-panel" style={{ marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
            <div>
              <h2 className="section-title" style={{ marginTop: 0 }}>
                Subscription tiers
              </h2>
              <p className="page-subtitle" style={{ marginTop: 0 }}>
                Silver (Identity ITDR), Gold (Core MDR), Platinum (Full MXDR). Custom is admin-only —
                pick modules à la carte without a public SKU.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <Link className="btn btn-primary" to="/services/tier-rollout">
                Provision tier upgrade
              </Link>
              <Link className="btn btn-ghost" to="/services/custom-tier">
                Provision custom tier
              </Link>
            </div>
          </div>
          <div className="tier-ops-stats">
            {(["SILVER", "GOLD", "PLATINUM", "CUSTOM"] as const).map((tier) => (
              <div key={tier} className="tier-ops-stat">
                <span className="tier-ops-stat-label">{tierDisplayName(tier)}</span>
                <strong>{tierCounts[tier]}</strong>
                <span className="muted-text">active customers</span>
              </div>
            ))}
          </div>
          <SubscriptionTierMatrix />
        </section>
      )}

      {!loading && (
        <>
          <h2 className="section-title">Capability modules (internal ops)</h2>
          <p className="page-subtitle">
            Same catalog as customer-facing tiers — not separate SKUs. Provision the tier above to
            enable all included modules. For NikTiar Edge tenants, check{" "}
            <Link to="/appliances">Appliances → Local engines</Link> for on-box license status.
          </p>
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
                    <span className="tier-badge tier-badge--active">
                      {includedInTierLabel(item.service_key as never)}
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
            <div className="state-message">No capability modules match this filter.</div>
          )}
        </div>
        </>
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

    </div>
  );
}
