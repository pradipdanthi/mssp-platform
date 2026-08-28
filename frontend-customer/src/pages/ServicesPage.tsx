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
import type { SubscriptionTier } from "../config/tierConfig";
import { tierDisplayName } from "../data/subscriptionTierMatrix";
import SubscriptionTierMatrix from "../components/SubscriptionTierMatrix";
import { formatScopeSummary } from "../data/serviceCatalog";

const OPEN_STATUSES = new Set(["PENDING_CONSULTATION", "UNDER_REVIEW"]);

type UpgradeForm = {
  scope_notes: string;
};

const EMPTY_UPGRADE_FORM: UpgradeForm = { scope_notes: "" };

export default function ServicesPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [ent, setEnt] = useState<CustomerEntitlements | null>(null);
  const [requests, setRequests] = useState<ConsultationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [upgradeTier, setUpgradeTier] = useState<SubscriptionTier | null>(null);
  const [form, setForm] = useState<UpgradeForm>(EMPTY_UPGRADE_FORM);
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
        else setError("Could not load your subscription portfolio.");
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

  const openUpgradeRequests = useMemo(
    () => requests.filter((r) => OPEN_STATUSES.has(r.status) && r.service_key.startsWith("tier_")),
    [requests]
  );

  function openUpgrade(target: SubscriptionTier) {
    setUpgradeTier(target);
    setForm(EMPTY_UPGRADE_FORM);
    setFormError(null);
    setSuccess(null);
  }

  async function handleUpgradeSubmit(e: FormEvent) {
    e.preventDefault();
    if (!shortCode || !upgradeTier) return;
    const notes = form.scope_notes.trim();
    if (notes.length < 8) {
      setFormError("Please add a short note about what you need (at least 8 characters).");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const serviceKey =
        upgradeTier === "GOLD"
          ? "tier_gold"
          : upgradeTier === "PLATINUM"
            ? "tier_platinum"
            : "tier_silver";
      await createConsultationRequest(shortCode, {
        service_key: serviceKey,
        service_name: `${tierDisplayName(upgradeTier)} subscription upgrade`,
        pricing_tier: tierDisplayName(upgradeTier),
        endpoint_count: null,
        m365_seat_count: null,
        target_domains: [],
        scope_notes: notes,
        contact_name: user?.full_name || null,
        contact_email: user?.email || null,
      });
      setSuccess(
        `Upgrade request submitted for ${tierDisplayName(upgradeTier)}. Your MSSP team will follow up. Track it under Incidents → Service Requests & Upgrades.`
      );
      setUpgradeTier(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setFormError(err.detail);
      else setFormError("Could not submit the upgrade request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Service Portfolio</h1>
      <p className="page-subtitle">
        Silver, Gold, and Platinum packages aligned to your <code>subscription_tier</code>. Your
        active plan is highlighted — request a consultation to upgrade to higher tiers.
      </p>

      {loading && <div className="state-message">Loading portfolio…</div>}
      {error && <div className="state-message state-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {!loading && !error && (
        <SubscriptionTierMatrix
          activeTier={ent?.subscription_tier}
          onRequestUpgrade={openUpgrade}
        />
      )}

      {upgradeTier && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => !submitting && setUpgradeTier(null)}
        >
          <form
            className="modal-panel upgrade-request-form"
            onSubmit={handleUpgradeSubmit}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Request upgrade — {tierDisplayName(upgradeTier)}
            </h2>
            <p className="page-subtitle" style={{ marginTop: 0 }}>
              Tell us about your environment and timeline. We create a service ticket and notify
              sales. Enabling happens only after commercial agreement.
            </p>
            <label className="form-label" style={{ display: "block", marginTop: "0.75rem" }}>
              Notes / requirements
              <textarea
                className="form-input"
                required
                minLength={8}
                rows={5}
                value={form.scope_notes}
                onChange={(e) => setForm({ scope_notes: e.target.value })}
                placeholder="Environment details, compliance drivers, target go-live…"
              />
            </label>
            {formError && <div className="form-error">{formError}</div>}
            <div className="confirm-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                {submitting ? "Sending…" : "Submit upgrade request"}
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => setUpgradeTier(null)}
                disabled={submitting}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {!loading && openUpgradeRequests.length > 0 && (
        <section className="management-panel" style={{ marginTop: "1.25rem" }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Open upgrade requests
          </h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Target tier</th>
                <th>Status</th>
                <th>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {openUpgradeRequests.map((r) => (
                <tr key={r.id}>
                  <td className="cell-mono">{r.id.slice(0, 8)}…</td>
                  <td>{r.service_name}</td>
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
