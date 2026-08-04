import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AssetServiceCoverageAsset,
  TenantEntitlements,
  getTenantAssetServiceCoverage,
  getTenantEntitlements,
  putTenantAssetServiceCoverage,
  putTenantEntitlements,
} from "../api/admin";
import { ApiError } from "../api/client";
import { catalogDisplayName, catalogShortHint } from "../data/serviceCatalog";

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

function boolField(form: TenantEntitlements, key: keyof TenantEntitlements, fallback = false): boolean {
  const v = form[key];
  return typeof v === "boolean" ? v : fallback;
}

/**
 * Admin subscription matrix — names/descriptions match Service Catalog
 * (`frontend-admin/src/data/serviceCatalog.ts`). Capability names only.
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
  const [coverageAssets, setCoverageAssets] = useState<AssetServiceCoverageAsset[]>([]);
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [assetFilter, setAssetFilter] = useState("");
  const [pasteList, setPasteList] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      getTenantEntitlements(tenantId),
      getTenantAssetServiceCoverage(tenantId, "vulnerability_management"),
    ])
      .then(([row, cov]) => {
        if (cancelled) return;
        setForm({
          ...row,
          continuous_compliance_enabled: Boolean(row.continuous_compliance_enabled),
          external_attack_surface_enabled: Boolean(row.external_attack_surface_enabled),
          cloud_identity_protection_enabled: Boolean(row.cloud_identity_protection_enabled),
        });
        setCoverageAssets(cov.assets || []);
        setSelectedAssetIds(cov.covered_asset_ids || []);
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

  const filteredAssets = useMemo(() => {
    const q = assetFilter.trim().toLowerCase();
    if (!q) return coverageAssets;
    return coverageAssets.filter((a) => {
      const blob = `${a.hostname || ""} ${a.ip_address || ""} ${a.os_name || ""} ${a.asset_type || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [coverageAssets, assetFilter]);

  function toggleAsset(id: string) {
    setSelectedAssetIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function applyPasteList() {
    const tokens = pasteList
      .split(/[\n,;]+/)
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    if (tokens.length === 0) {
      setError("Paste hostnames or IPs from the customer email/contract (one per line).");
      return;
    }
    const matched = coverageAssets.filter((a) => {
      const host = (a.hostname || "").toLowerCase();
      const ip = (a.ip_address || "").toLowerCase();
      return tokens.some((t) => host === t || ip === t || host.includes(t) || ip.includes(t));
    });
    if (matched.length === 0) {
      setError(
        "No assets matched that list. Check hostnames/IPs against Assets for this customer."
      );
      return;
    }
    setSelectedAssetIds((prev) => {
      const next = new Set(prev);
      for (const a of matched) next.add(a.id);
      return Array.from(next);
    });
    setForm((f) => (f ? { ...f, greenbone_enabled: true } : f));
    setError(null);
    setSuccess(
      `Matched ${matched.length} asset(s) from the pasted list. Review the checkboxes, set cadence, then Save.`
    );
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    if (form.greenbone_enabled && selectedAssetIds.length === 0) {
      setError(
        "Vulnerability Management is on — select at least one asset to scan, or turn the service off."
      );
      return;
    }
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
        continuous_compliance_enabled: boolField(form, "continuous_compliance_enabled"),
        external_attack_surface_enabled: boolField(form, "external_attack_surface_enabled"),
        cloud_identity_protection_enabled: boolField(form, "cloud_identity_protection_enabled"),
        roadmap_notes: form.roadmap_notes,
      });
      setForm({
        ...saved,
        continuous_compliance_enabled: Boolean(saved.continuous_compliance_enabled),
        external_attack_surface_enabled: Boolean(saved.external_attack_surface_enabled),
        cloud_identity_protection_enabled: Boolean(saved.cloud_identity_protection_enabled),
      });

      if (form.greenbone_enabled) {
        const cov = await putTenantAssetServiceCoverage(tenantId, {
          service_key: "vulnerability_management",
          asset_ids: selectedAssetIds,
          enable_entitlement: true,
          greenbone_cadence: form.greenbone_cadence,
        });
        setCoverageAssets(cov.assets || []);
        setSelectedAssetIds(cov.covered_asset_ids || []);
        setSuccess(
          `Subscription updated for ${tenantName}. Vulnerability Management covers ${
            cov.covered_asset_ids?.length ?? 0
          } selected asset(s).`
        );
      } else {
        await putTenantAssetServiceCoverage(tenantId, {
          service_key: "vulnerability_management",
          asset_ids: [],
          enable_entitlement: false,
        });
        setSelectedAssetIds([]);
        setSuccess(
          `Subscription updated for ${tenantName}. Customer portal feature availability refreshes on next load.`
        );
      }
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
        Subscription / enable services — {tenantName}
      </h2>
      <p className="page-subtitle" style={{ marginBottom: "12px" }}>
        Names match the Admin <strong>Service Catalog</strong>. Use this when the customer signed
        offline and you enable coverage from the MSSP side — they do not need to click Request in
        their portal.
      </p>

      {loading && <div className="state-message">Loading entitlements…</div>}
      {error && <div className="form-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      {form && !loading && (
        <div className="entitlement-matrix">
          <div className="entitlement-section-label">Core (included)</div>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.wazuh_siem}
              onChange={(e) => setForm({ ...form, wazuh_siem: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("log_event_monitoring")}</strong>
              <span className="entitlement-hint">{catalogShortHint("log_event_monitoring")}</span>
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
            <span className="entitlement-label">
              <strong>{catalogDisplayName("incident_response")}</strong>
              <span className="entitlement-hint">{catalogShortHint("incident_response")}</span>
            </span>
            <select
              className="form-input"
              value={form.thehive_mode}
              onChange={(e) => setForm({ ...form, thehive_mode: e.target.value })}
            >
              <option value="full">Full managed SOC</option>
              <option value="read_only">Read-only case visibility</option>
              <option value="off">Off</option>
            </select>
          </label>

          <label className="entitlement-row">
            <span className="entitlement-label">
              <strong>{catalogDisplayName("security_automation")}</strong>
              <span className="entitlement-hint">{catalogShortHint("security_automation")}</span>
            </span>
            <select
              className="form-input"
              value={form.shuffle_mode}
              onChange={(e) => setForm({ ...form, shuffle_mode: e.target.value })}
            >
              <option value="standard">Standard containment playbooks</option>
              <option value="custom">Custom playbooks</option>
              <option value="off">Off</option>
            </select>
          </label>

          <div className="entitlement-section-label">Optional add-ons</div>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.greenbone_enabled}
              onChange={(e) => setForm({ ...form, greenbone_enabled: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("vulnerability_management")}</strong>
              <span className="entitlement-hint">{catalogShortHint("vulnerability_management")}</span>
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

          {form.greenbone_enabled && (
            <div className="asset-picker" style={{ margin: "0.5rem 0 1rem 1.5rem" }}>
              <div className="entitlement-hint" style={{ marginBottom: "0.35rem" }}>
                Devices covered by Vulnerability Management ({selectedAssetIds.length} selected)
              </div>
              <p className="page-subtitle" style={{ marginTop: 0 }}>
                Match the server list from the signed contract or email. Paste names/IPs below, or
                search and tick manually.
              </p>
              <label className="form-label">
                Paste hostnames / IPs from email or contract
                <textarea
                  className="form-input"
                  rows={3}
                  value={pasteList}
                  onChange={(e) => setPasteList(e.target.value)}
                  placeholder={"srv-db-01\nsrv-app-02\n192.168.0.50"}
                />
              </label>
              <div className="confirm-actions" style={{ marginBottom: "0.5rem" }}>
                <button className="btn btn-secondary" type="button" onClick={applyPasteList}>
                  Match pasted list
                </button>
              </div>
              <label className="form-label">
                Filter assets
                <input
                  className="form-input"
                  value={assetFilter}
                  onChange={(e) => setAssetFilter(e.target.value)}
                  placeholder="Search hostname, IP, OS…"
                />
              </label>
              {coverageAssets.length === 0 ? (
                <p className="muted">
                  No protected assets yet for this customer. Add/install agents under Assets first,
                  then select coverage here.
                </p>
              ) : (
                <div className="asset-picker-list">
                  {filteredAssets.map((a) => (
                    <label key={a.id} className="upgrade-check asset-picker-row">
                      <input
                        type="checkbox"
                        checked={selectedAssetIds.includes(a.id)}
                        onChange={() => toggleAsset(a.id)}
                      />
                      <span>
                        <strong>{a.hostname ?? a.id}</strong>
                        <span className="muted-text">
                          {" "}
                          · {a.asset_type}
                          {a.os_name ? ` · ${a.os_name}` : ""}
                          {a.ip_address ? ` · ${a.ip_address}` : ""}
                        </span>
                      </span>
                    </label>
                  ))}
                  {filteredAssets.length === 0 ? (
                    <p className="muted">No assets match this filter.</p>
                  ) : null}
                </div>
              )}
            </div>
          )}

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={boolField(form, "continuous_compliance_enabled")}
              onChange={(e) =>
                setForm({ ...form, continuous_compliance_enabled: e.target.checked })
              }
            />
            <span>
              <strong>{catalogDisplayName("continuous_compliance")}</strong>
              <span className="entitlement-hint">{catalogShortHint("continuous_compliance")}</span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.zeek_enabled}
              onChange={(e) => setForm({ ...form, zeek_enabled: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("network_detection_response")}</strong>
              <span className="entitlement-hint">{catalogShortHint("network_detection_response")}</span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.misp_enabled}
              onChange={(e) => setForm({ ...form, misp_enabled: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("threat_intelligence")}</strong>
              <span className="entitlement-hint">{catalogShortHint("threat_intelligence")}</span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={form.velociraptor_enabled}
              onChange={(e) => setForm({ ...form, velociraptor_enabled: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("endpoint_forensics_deception")}</strong>
              <span className="entitlement-hint">
                {catalogShortHint("endpoint_forensics_deception")}
              </span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={boolField(form, "external_attack_surface_enabled")}
              onChange={(e) =>
                setForm({ ...form, external_attack_surface_enabled: e.target.checked })
              }
            />
            <span>
              <strong>{catalogDisplayName("external_attack_surface")}</strong>
              <span className="entitlement-hint">{catalogShortHint("external_attack_surface")}</span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={boolField(form, "cloud_identity_protection_enabled")}
              onChange={(e) =>
                setForm({ ...form, cloud_identity_protection_enabled: e.target.checked })
              }
            />
            <span>
              <strong>{catalogDisplayName("cloud_identity_protection")}</strong>
              <span className="entitlement-hint">
                {catalogShortHint("cloud_identity_protection")}
              </span>
            </span>
          </label>

          <label className="form-label" style={{ gridColumn: "1 / -1" }}>
            Internal notes
            <textarea
              className="form-input"
              rows={3}
              value={form.roadmap_notes ?? ""}
              onChange={(e) => setForm({ ...form, roadmap_notes: e.target.value || null })}
            />
          </label>
        </div>
      )}

      <div className="confirm-actions">
        <button className="btn btn-primary" type="submit" disabled={saving || loading || !form}>
          {saving ? "Saving…" : "Save subscription"}
        </button>
        <button className="btn btn-ghost" type="button" onClick={onClose} disabled={saving}>
          Close
        </button>
      </div>
    </form>
  );
}
