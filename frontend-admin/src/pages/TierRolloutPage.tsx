import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Tenant, getTenants, rolloutTenantTier } from "../api/admin";
import {
  TIER_CATALOG,
  tierDisplayName,
  type StandardSubscriptionTier,
} from "../data/subscriptionTierMatrix";

export default function TierRolloutPage() {
  const navigate = useNavigate();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [targetTier, setTargetTier] = useState<StandardSubscriptionTier>("GOLD");
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);
  const [orderNumber, setOrderNumber] = useState("");
  const [confirmEmail, setConfirmEmail] = useState("");
  const [adminNotes, setAdminNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    getTenants({ page_size: 200 })
      .then((res) => setTenants(res.tenants || []))
      .catch(() => setTenants([]))
      .finally(() => setLoading(false));
  }, []);

  const eligibleTenants = tenants.filter((t) => (t.subscription_tier || "SILVER") !== "CUSTOM");
  const tierMeta = TIER_CATALOG.find((t) => t.tier === targetTier);

  function toggleTenant(id: string) {
    setSelectedTenantIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedTenantIds.length) {
      setError("Select at least one customer.");
      return;
    }
    if (!orderNumber.trim()) {
      setError("Customer order number is required.");
      return;
    }
    if (!confirmEmail.trim() || !confirmEmail.includes("@")) {
      setError("Confirmation email is required.");
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await rolloutTenantTier({
        tenant_ids: selectedTenantIds,
        target_tier: targetTier,
        customer_order_number: orderNumber.trim(),
        confirmation_email: confirmEmail.trim(),
        admin_notes: adminNotes.trim() || null,
        mark_requests_approved: true,
      });
      setSuccess(
        `Provisioned ${tierDisplayName(targetTier)} for ${res.rolled_out} customer(s)` +
          (res.failed ? ` (${res.failed} failed)` : "") +
          ` · order ${orderNumber.trim()}.`
      );
      setSelectedTenantIds([]);
      setOrderNumber("");
      setConfirmEmail("");
      setAdminNotes("");
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
      else setError("Tier rollout failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="tier-provision-page">
      <p className="page-back-link">
        <Link to="/services">← Back to Tier Operations</Link>
      </p>

      <h1 className="page-title">Provision tier upgrade</h1>
      <p className="page-subtitle">
        Sets <code>subscription_tier</code>, syncs the entitlement bundle, runs cloud adapter syncs
        for included modules, pushes NikTiar Edge license jobs for appliance tenants, approves open
        tier upgrade requests, and sends a confirmation email.
      </p>

      {loading && <div className="state-message">Loading customers…</div>}
      {success && <div className="state-message state-success">{success}</div>}
      {error && <div className="form-error">{error}</div>}

      {!loading && (
        <form className="management-panel tier-provision-form" onSubmit={handleSubmit}>
          <section className="tier-provision-section">
            <h2 className="section-title">1. Target tier</h2>
            <label className="form-label">
              Subscription tier
              <select
                className="form-input"
                value={targetTier}
                onChange={(e) => setTargetTier(e.target.value as StandardSubscriptionTier)}
              >
                {TIER_CATALOG.map((t) => (
                  <option key={t.tier} value={t.tier}>
                    {t.name} — {t.subtitle}
                  </option>
                ))}
              </select>
            </label>
            {tierMeta && <p className="page-subtitle">{tierMeta.tagline}</p>}
          </section>

          <section className="tier-provision-section">
            <h2 className="section-title">2. Order details</h2>
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
                  No eligible customers — CUSTOM tier tenants must use Provision custom tier.
                </div>
              )}
            </div>
          </section>

          <div className="confirm-actions tier-provision-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy
                ? "Provisioning…"
                : `Provision ${tierDisplayName(targetTier)} for ${selectedTenantIds.length || 0} customer(s)`}
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
