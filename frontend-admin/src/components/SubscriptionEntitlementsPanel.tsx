import { FormEvent, useEffect, useState } from "react";
import {
  TenantEntitlements,
  getTenantEntitlements,
  putTenantEntitlements,
} from "../api/admin";
import { ApiError } from "../api/client";

type Props = {
  tenantId: string;
  tenantName: string;
  onClose: () => void;
  onSaved?: () => void;
};

function errMsg(err: unknown): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  return "Could not save subscription entitlements.";
}

/**
 * Admin service catalog — labels use capability names only
 * (never third-party engine brand names in the UI).
 */
export default function SubscriptionEntitlementsPanel({
  tenantId,
  tenantName,
  onClose,
  onSaved,
}: Props) {
  const [form, setForm] = useState<TenantEntitlements | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTenantEntitlements(tenantId)
      .then((row) => {
        if (!cancelled) setForm(row);
      })
      .catch((err) => {
        if (!cancelled) setError(errMsg(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const saved = await putTenantEntitlements(tenantId, {
        wazuh_siem: form.wazuh_siem,
        wazuh_retention_days: form.wazuh_retention_days,
        thehive_mode: form.thehive_mode,
        greenbone_enabled: form.greenbone_enabled,
        greenbone_cadence: form.greenbone_cadence,
        shuffle_mode: form.shuffle_mode,
        zeek_enabled: form.zeek_enabled,
        misp_enabled: form.misp_enabled,
        velociraptor_enabled: form.velociraptor_enabled,
        roadmap_notes: form.roadmap_notes,
      });
      setForm(saved);
      setSuccess(
        `Subscription updated for ${tenantName}. Customer portal feature availability refreshes on next load.`
      );
      onSaved?.();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="management-panel subscription-panel" onSubmit={handleSave}>
      <h2 className="section-title" style={{ marginTop: 0 }}>
        Subscription / service entitlements — {tenantName}
      </h2>
      <p className="page-subtitle" style={{ marginBottom: "12px" }}>
        Choose which security services this customer is entitled to. Optional add-on services can be
        marked as requested; they are activated according to subscription and capacity planning.
      </p>

      {loading && <div className="state-message">Loading entitlements…</div>}
      {error && <div className="form-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {form && !loading && (
        <div className="entitlement-matrix">
          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.wazuh_siem}
              onChange={(e) => setForm({ ...form, wazuh_siem: e.target.checked })}
            />
            <span>
              <strong>SIEM &amp; Log Management</strong>
              <span className="entitlement-hint">Log retention &amp; detection correlation</span>
              <select
                className="form-input entitlement-inline"
                value={form.wazuh_retention_days}
                disabled={!form.wazuh_siem}
                onChange={(e) =>
                  setForm({ ...form, wazuh_retention_days: Number(e.target.value) })
                }
              >
                <option value={30}>30 Days retention</option>
                <option value={90}>90 Days retention</option>
                <option value={365}>365 Days retention</option>
              </select>
            </span>
          </label>

          <label className="entitlement-row">
            <span className="entitlement-label">Incident Response &amp; Casework</span>
            <select
              className="form-input"
              value={form.thehive_mode}
              onChange={(e) => setForm({ ...form, thehive_mode: e.target.value })}
            >
              <option value="full">Full Auto-SOC</option>
              <option value="read_only">Read-Only Alerts</option>
              <option value="off">Off</option>
            </select>
          </label>

          <label className="entitlement-row">
            <span className="entitlement-label">Security Automation (SOAR)</span>
            <select
              className="form-input"
              value={form.shuffle_mode}
              onChange={(e) => setForm({ ...form, shuffle_mode: e.target.value })}
            >
              <option value="standard">Standard Playbooks</option>
              <option value="custom">Custom Playbooks</option>
              <option value="off">Off</option>
            </select>
          </label>

          <div className="entitlement-section-label">
            Core + optional services
          </div>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.greenbone_enabled}
              onChange={(e) => setForm({ ...form, greenbone_enabled: e.target.checked })}
            />
            <span>
              <strong>Vulnerability Management</strong>
              <span className="entitlement-hint">
                Continuous CVE discovery &amp; remediation guidance
              </span>
              <select
                className="form-input entitlement-inline"
                value={form.greenbone_cadence}
                disabled={!form.greenbone_enabled}
                onChange={(e) => setForm({ ...form, greenbone_cadence: e.target.value })}
              >
                <option value="weekly">Weekly scans</option>
                <option value="monthly">Monthly scans</option>
                <option value="off">Cadence off</option>
              </select>
            </span>
          </label>

          <div className="entitlement-section-label">
            Optional add-on services
          </div>
          <p className="entitlement-roadmap-note">
            Request these capabilities for the customer. Activation follows subscription scope and
            platform capacity — not a separate manual setup in third-party tool UIs.
          </p>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={!!form.zeek_enabled}
              onChange={(e) => setForm({ ...form, zeek_enabled: e.target.checked })}
            />
            <span>
              <strong>Network Traffic Analysis</strong>
              <span className="entitlement-hint">
                Protocol &amp; east-west traffic visibility · Optional add-on
              </span>
              {form.zeek_enabled ? (
                <span className="entitlement-badge">Requested / queued</span>
              ) : null}
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={!!form.misp_enabled}
              onChange={(e) => setForm({ ...form, misp_enabled: e.target.checked })}
            />
            <span>
              <strong>Threat Intelligence Sharing</strong>
              <span className="entitlement-hint">
                IOC enrichment &amp; community intel feeds · Optional add-on
              </span>
              {form.misp_enabled ? (
                <span className="entitlement-badge">Requested / queued</span>
              ) : null}
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={!!form.velociraptor_enabled}
              onChange={(e) => setForm({ ...form, velociraptor_enabled: e.target.checked })}
            />
            <span>
              <strong>Endpoint Forensics &amp; Hunting</strong>
              <span className="entitlement-hint">
                Live response, artifact collection, hunt campaigns · Optional add-on
              </span>
              {form.velociraptor_enabled ? (
                <span className="entitlement-badge">Requested / queued</span>
              ) : null}
            </span>
          </label>

          <label className="form-label form-grid-full" style={{ marginTop: 8 }}>
            Internal notes (demand / rollout planning)
            <textarea
              className="form-input"
              rows={2}
              maxLength={2000}
              placeholder="e.g. Customer needs Network Traffic Analysis for OT segment — prioritize when 5+ tenants request."
              value={form.roadmap_notes ?? ""}
              onChange={(e) => setForm({ ...form, roadmap_notes: e.target.value || null })}
            />
          </label>
        </div>
      )}

      <div className="confirm-actions">
        <button className="btn btn-primary" type="submit" disabled={saving || !form || loading}>
          {saving ? "Saving…" : "Save subscription"}
        </button>
        <button className="btn btn-ghost" type="button" disabled={saving} onClick={onClose}>
          Close
        </button>
      </div>
    </form>
  );
}
