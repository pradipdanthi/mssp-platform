import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  createServiceUpgradeRequest,
  getCustomerEntitlements,
  getVulnerabilityServiceSummary,
  listServiceUpgradeRequests,
  ServiceUpgradeRequest,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const SCAN_SCOPE_OPTIONS = [
  { value: "external_perimeter", label: "External / internet-facing systems" },
  { value: "internal_network", label: "Internal network hosts" },
  { value: "authenticated_hosts", label: "Authenticated / credentialed host scans" },
  { value: "cloud_workloads", label: "Cloud workloads (IaaS / VMs)" },
  { value: "web_applications", label: "Web applications" },
];

const ENVIRONMENT_OPTIONS = [
  { value: "production", label: "Production" },
  { value: "non_production", label: "Non-production / staging" },
  { value: "remote_workforce", label: "Remote workforce endpoints" },
  { value: "ot_ics", label: "OT / ICS environments" },
];

const COMPLIANCE_OPTIONS = [
  { value: "iso27001", label: "ISO 27001" },
  { value: "soc2", label: "SOC 2" },
  { value: "pci_dss", label: "PCI DSS" },
  { value: "hipaa", label: "HIPAA" },
  { value: "gdpr", label: "GDPR / privacy" },
  { value: "other", label: "Other / internal policy" },
];

type FormState = {
  preferred_cadence: "weekly" | "monthly" | "quarterly" | "unsure";
  scan_scope: string[];
  approximate_assets: string;
  environments: string[];
  urgency: "exploring" | "planning" | "needed_soon" | "urgent";
  compliance_drivers: string[];
  requirements_summary: string;
  preferred_contact: "email" | "phone" | "either";
  contact_phone: string;
};

const EMPTY_FORM: FormState = {
  preferred_cadence: "monthly",
  scan_scope: [],
  approximate_assets: "",
  environments: ["production"],
  urgency: "planning",
  compliance_drivers: [],
  requirements_summary: "",
  preferred_contact: "email",
  contact_phone: "",
};

function toggleList(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * KB-071/KB-076: Vulnerabilities tab — adaptive UI based on entitlement.
 * When not entitled: upgrade request form. When entitled: customer-safe summary.
 */
export default function VulnerabilitiesPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [cadence, setCadence] = useState("monthly");
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [existing, setExisting] = useState<ServiceUpgradeRequest[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [publishedOpen, setPublishedOpen] = useState(0);
  const [lastActivity, setLastActivity] = useState<string | null>(null);

  function refreshRequests() {
    if (!shortCode) return;
    listServiceUpgradeRequests(shortCode)
      .then((res) => setExisting(res.requests || []))
      .catch(() => undefined);
  }

  useEffect(() => {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing from session.");
      return;
    }
    let cancelled = false;
    setLoading(true);
    getCustomerEntitlements(shortCode)
      .then((ent) => {
        if (cancelled) return;
        setEnabled(!!ent.vulnerability_management_enabled);
        setCadence(ent.vulnerability_scan_cadence || "monthly");
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && typeof err.detail === "string") setError(err.detail);
        else setError("Could not load subscription entitlements.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    refreshRequests();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    let cancelled = false;
    setSummaryLoading(true);
    getVulnerabilityServiceSummary(shortCode)
      .then((s) => {
        if (cancelled) return;
        setPublishedOpen(s.published_open_recommendations ?? 0);
        setLastActivity(s.last_scan_activity_at);
      })
      .catch(() => {
        if (!cancelled) {
          setPublishedOpen(0);
          setLastActivity(null);
        }
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shortCode, enabled]);

  const openVulnRequest = existing.find(
    (r) =>
      r.service_key === "vulnerability_management" &&
      ["submitted", "reviewing", "quoted"].includes(r.status)
  );
  const declinedVulnRequest = existing.find(
    (r) =>
      r.service_key === "vulnerability_management" && r.status === "declined"
  );

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!shortCode) return;
    if (form.requirements_summary.trim().length < 10) {
      setFormError("Please describe what you are looking for (at least a few sentences).");
      return;
    }
    if (form.scan_scope.length === 0) {
      setFormError("Select at least one scan scope.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    setSuccess(null);
    try {
      const assets = form.approximate_assets.trim()
        ? Number(form.approximate_assets)
        : null;
      await createServiceUpgradeRequest(shortCode, {
        service_key: "vulnerability_management",
        preferred_cadence: form.preferred_cadence,
        scan_scope: form.scan_scope,
        approximate_assets: assets && !Number.isNaN(assets) ? assets : null,
        environments: form.environments,
        urgency: form.urgency,
        compliance_drivers: form.compliance_drivers,
        requirements_summary: form.requirements_summary.trim(),
        preferred_contact: form.preferred_contact,
        contact_phone: form.contact_phone.trim() || null,
      });
      setSuccess(
        "Thank you. Your Vulnerability Management upgrade request was sent to your MSSP team. They will follow up with options and next steps."
      );
      setShowForm(false);
      setForm(EMPTY_FORM);
      refreshRequests();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") setFormError(err.detail);
      else setFormError("Could not submit your request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="state-message">Checking your subscription…</div>;
  }
  if (error) {
    return <div className="state-message state-error">{error}</div>;
  }

  if (!enabled) {
    return (
      <div className="feature-locked card-surface">
        <div className="feature-locked-badge">Subscription required</div>
        <h1 className="page-title">Vulnerability Management</h1>
        <p className="page-subtitle">
          Continuous vulnerability scanning is not included in your current service package. With
          this module your MSSP can discover security weaknesses on protected assets, prioritize
          remediation, and publish plain-English recommendations in your portal.
        </p>
        <ul className="feature-locked-list">
          <li>Weekly or monthly authenticated / network scans</li>
          <li>Customer-safe findings with remediation guidance</li>
          <li>Promotion into actionable recommendations</li>
        </ul>

        {success && <div className="state-message state-success">{success}</div>}

        {openVulnRequest && !showForm ? (
          <div className="upgrade-request-status">
            <p>
              You already have an open request (<strong>{openVulnRequest.status}</strong>) submitted{" "}
              {new Date(openVulnRequest.created_at).toLocaleString()}. Your MSSP will follow up on:
            </p>
            <p className="upgrade-request-quote">{openVulnRequest.requirements_summary}</p>
          </div>
        ) : null}

        {declinedVulnRequest && !openVulnRequest && !showForm ? (
          <div className="upgrade-request-status">
            <p>
              Your previous upgrade request was declined. Contact your MSSP account team if you would
              like to discuss options, or submit a new request below.
            </p>
          </div>
        ) : null}

        {!showForm && !openVulnRequest ? (
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            {declinedVulnRequest ? "Submit a new request" : "Upgrade Subscription"}
          </button>
        ) : null}

        {showForm && (
          <form className="upgrade-request-form" onSubmit={handleSubmit}>
            <h2 className="section-title">Tell us what you need</h2>
            <p className="page-subtitle">
              Share your goals and environment so your MSSP can propose the right Vulnerability
              Management package. Your MSSP team reviews requests before any scanning begins.
            </p>

            <label className="form-label">
              Preferred scan cadence
              <select
                className="form-input"
                value={form.preferred_cadence}
                onChange={(e) =>
                  setForm({
                    ...form,
                    preferred_cadence: e.target.value as FormState["preferred_cadence"],
                  })
                }
              >
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="unsure">Not sure yet</option>
              </select>
            </label>

            <fieldset className="upgrade-fieldset">
              <legend>Scan scope (select all that apply)</legend>
              {SCAN_SCOPE_OPTIONS.map((o) => (
                <label key={o.value} className="upgrade-check">
                  <input
                    type="checkbox"
                    checked={form.scan_scope.includes(o.value)}
                    onChange={() =>
                      setForm({ ...form, scan_scope: toggleList(form.scan_scope, o.value) })
                    }
                  />
                  {o.label}
                </label>
              ))}
            </fieldset>

            <label className="form-label">
              Approximate assets / endpoints to cover (optional)
              <input
                className="form-input"
                type="number"
                min={1}
                max={1000000}
                placeholder="e.g. 50"
                value={form.approximate_assets}
                onChange={(e) => setForm({ ...form, approximate_assets: e.target.value })}
              />
            </label>

            <fieldset className="upgrade-fieldset">
              <legend>Environments</legend>
              {ENVIRONMENT_OPTIONS.map((o) => (
                <label key={o.value} className="upgrade-check">
                  <input
                    type="checkbox"
                    checked={form.environments.includes(o.value)}
                    onChange={() =>
                      setForm({
                        ...form,
                        environments: toggleList(form.environments, o.value),
                      })
                    }
                  />
                  {o.label}
                </label>
              ))}
            </fieldset>

            <label className="form-label">
              Urgency
              <select
                className="form-input"
                value={form.urgency}
                onChange={(e) =>
                  setForm({ ...form, urgency: e.target.value as FormState["urgency"] })
                }
              >
                <option value="exploring">Just exploring options</option>
                <option value="planning">Planning for next quarter</option>
                <option value="needed_soon">Needed soon</option>
                <option value="urgent">Urgent / audit-driven</option>
              </select>
            </label>

            <fieldset className="upgrade-fieldset">
              <legend>Compliance / drivers (optional)</legend>
              {COMPLIANCE_OPTIONS.map((o) => (
                <label key={o.value} className="upgrade-check">
                  <input
                    type="checkbox"
                    checked={form.compliance_drivers.includes(o.value)}
                    onChange={() =>
                      setForm({
                        ...form,
                        compliance_drivers: toggleList(form.compliance_drivers, o.value),
                      })
                    }
                  />
                  {o.label}
                </label>
              ))}
            </fieldset>

            <label className="form-label">
              What are you looking for?
              <textarea
                className="form-input"
                required
                minLength={10}
                maxLength={4000}
                rows={5}
                placeholder="e.g. We need monthly authenticated scans of our production servers and a plain-English remediation list for IT. We have an ISO audit in 90 days."
                value={form.requirements_summary}
                onChange={(e) => setForm({ ...form, requirements_summary: e.target.value })}
              />
            </label>

            <label className="form-label">
              Preferred contact for follow-up
              <select
                className="form-input"
                value={form.preferred_contact}
                onChange={(e) =>
                  setForm({
                    ...form,
                    preferred_contact: e.target.value as FormState["preferred_contact"],
                  })
                }
              >
                <option value="email">Email</option>
                <option value="phone">Phone</option>
                <option value="either">Either</option>
              </select>
            </label>

            <label className="form-label">
              Contact phone (optional unless phone preferred)
              <input
                className="form-input"
                maxLength={40}
                value={form.contact_phone}
                onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
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
                disabled={submitting}
                onClick={() => {
                  setShowForm(false);
                  setFormError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Vulnerabilities</h1>
      <p className="page-subtitle">
        Vulnerability Management is active for your organization
        {cadence && cadence !== "off" ? ` (${cadence} cadence)` : ""}. Your MSSP runs
        managed vulnerability scanning on scoped targets. Customer-visible remediation items
        appear under Recommendations after SOC review — technical scan output is never shown here.
      </p>
      {summaryLoading ? (
        <div className="state-message">Loading service status…</div>
      ) : (
        <div className="card-surface" style={{ marginBottom: "1rem", padding: "1rem" }}>
          <p style={{ margin: 0 }}>
            <strong>Open published remediations:</strong> {publishedOpen}
            {lastActivity ? (
              <>
                {" "}
                · <strong>Last scan activity:</strong>{" "}
                {new Date(lastActivity).toLocaleString()}
              </>
            ) : null}
          </p>
        </div>
      )}
      {publishedOpen === 0 ? (
        <div className="state-message">
          No new customer-visible vulnerability recommendations right now. Check{" "}
          <Link to="/recommendations">Recommendations</Link> for remediation items your SOC has
          published.
        </div>
      ) : (
        <div className="state-message">
          You have {publishedOpen} open vulnerability recommendation
          {publishedOpen === 1 ? "" : "s"}. View details on the{" "}
          <Link to="/recommendations">Recommendations</Link> page.
        </div>
      )}
    </div>
  );
}
