import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  Tenant,
  getCustomTierCatalog,
  getTenants,
  provisionCustomTier,
  type CustomTierCatalogModule,
} from "../api/admin";
import { catalogDisplayName } from "../data/serviceCatalog";
import type { ConsultationServiceKey } from "../data/serviceCatalog";
import { includedInTierLabel } from "../data/tierCapabilityMap";
import { tierDisplayName } from "../data/subscriptionTierMatrix";

export default function CustomTierProvisionPage() {
  const navigate = useNavigate();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [modules, setModules] = useState<CustomTierCatalogModule[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);
  const [orderNumber, setOrderNumber] = useState("");
  const [adminNotes, setAdminNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getTenants({ page_size: 200 }), getCustomTierCatalog()])
      .then(([tenantRes, catalog]) => {
        setTenants(tenantRes.tenants || []);
        setModules(catalog.modules || []);
      })
      .catch(() => {
        setTenants([]);
        setModules([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const eligibleTenants = tenants.filter((t) => (t.subscription_tier || "SILVER") !== "CUSTOM");

  function toggleTenant(id: string) {
    setSelectedTenantIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function toggleKey(key: string) {
    setSelectedKeys((prev) =>
      prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedTenantIds.length) {
      setError("Select at least one customer.");
      return;
    }
    if (!selectedKeys.length) {
      setError("Select at least one capability module.");
      return;
    }
    if (!orderNumber.trim()) {
      setError("Customer order number is required.");
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await provisionCustomTier({
        tenant_ids: selectedTenantIds,
        catalog_keys: selectedKeys,
        customer_order_number: orderNumber.trim(),
        admin_notes: adminNotes.trim() || null,
      });
      setSuccess(
        `Provisioned CUSTOM tier for ${res.provisioned} customer(s)` +
          (res.failed ? ` (${res.failed} failed)` : "") +
          ` · ${selectedKeys.length} module(s) · order ${orderNumber.trim()}.`
      );
      setSelectedTenantIds([]);
      setSelectedKeys([]);
      setOrderNumber("");
      setAdminNotes("");
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
      else setError("Custom tier provision failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="tier-provision-page">
      <p className="page-back-link">
        <Link to="/services">← Back to Tier Operations</Link>
      </p>

      <h1 className="page-title">Provision custom tier</h1>
      <p className="page-subtitle">
        Admin-only bespoke bundle — not marketed publicly. Select capabilities from any standard tier
        mix; fulfillment uses the same router as Silver / Gold / Platinum (cloud adapters + NikTiar
        Edge license from entitlement flags).
      </p>

      {loading && <div className="state-message">Loading catalog…</div>}
      {success && <div className="state-message state-success">{success}</div>}
      {error && <div className="form-error">{error}</div>}

      {!loading && (
        <form className="management-panel tier-provision-form" onSubmit={handleSubmit}>
          <section className="tier-provision-section">
            <h2 className="section-title">1. Order details</h2>
            <label className="form-label">
              Customer order number
              <input
                className="form-input"
                value={orderNumber}
                onChange={(e) => setOrderNumber(e.target.value)}
                placeholder="PO-10482 / SOW-…"
                required
              />
            </label>
            <label className="form-label">
              Notes (optional)
              <textarea
                className="form-input"
                rows={3}
                value={adminNotes}
                onChange={(e) => setAdminNotes(e.target.value)}
              />
            </label>
          </section>

          <div className="tier-provision-grid">
            <section className="tier-provision-section">
              <h2 className="section-title">2. Capability modules</h2>
              <div className="rollout-tenant-list rollout-tenant-list--page">
                {modules.map((m) => (
                  <label key={m.catalog_key} className="rollout-tenant-row">
                    <input
                      type="checkbox"
                      checked={selectedKeys.includes(m.catalog_key)}
                      onChange={() => toggleKey(m.catalog_key)}
                    />
                    <span>
                      {catalogDisplayName(m.catalog_key as ConsultationServiceKey)}{" "}
                      <span className="cell-mono">
                        ({includedInTierLabel(m.catalog_key as ConsultationServiceKey)})
                      </span>
                    </span>
                  </label>
                ))}
                {modules.length === 0 && (
                  <div className="state-message">No capability modules available.</div>
                )}
              </div>
            </section>

            <section className="tier-provision-section">
              <h2 className="section-title">3. Customers</h2>
              <div className="rollout-tenant-list rollout-tenant-list--page">
                {eligibleTenants.map((t) => (
                  <label key={t.id} className="rollout-tenant-row">
                    <input
                      type="checkbox"
                      checked={selectedTenantIds.includes(t.id)}
                      onChange={() => toggleTenant(t.id)}
                    />
                    <span>
                      {t.name}{" "}
                      <span className="cell-mono">
                        ({t.short_code}) · {tierDisplayName(t.subscription_tier || "SILVER")}
                      </span>
                    </span>
                  </label>
                ))}
                {eligibleTenants.length === 0 && (
                  <div className="state-message">
                    No eligible customers (already CUSTOM or none loaded).
                  </div>
                )}
              </div>
            </section>
          </div>

          <div className="confirm-actions tier-provision-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy
                ? "Provisioning…"
                : `Provision CUSTOM for ${selectedTenantIds.length || 0} customer(s)`}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={busy}
              onClick={() => navigate("/services")}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
