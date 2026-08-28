/** Tier-first onboarding + optional MSSP entitlement overrides. */

import type { StandardSubscriptionTier } from "../data/subscriptionTierMatrix";
import { TIER_CATALOG } from "../data/subscriptionTierMatrix";
import { catalogDisplayName, catalogShortHint } from "../data/serviceCatalog";

export type CreateEntitlementsState = {
  wazuh_siem: boolean;
  wazuh_retention_days: number;
  thehive_mode: string;
  greenbone_enabled: boolean;
  greenbone_cadence: string;
  shuffle_mode: string;
  zeek_enabled: boolean;
  misp_enabled: boolean;
  velociraptor_enabled: boolean;
  continuous_compliance_enabled?: boolean;
  external_attack_surface_enabled?: boolean;
  cloud_identity_protection_enabled?: boolean;
  roadmap_notes: string;
};

type Props = {
  subscriptionTier: StandardSubscriptionTier;
  onTierChange: (tier: StandardSubscriptionTier) => void;
  value: CreateEntitlementsState;
  onChange: (next: CreateEntitlementsState) => void;
  showAdvanced?: boolean;
  onToggleAdvanced?: (open: boolean) => void;
};

export default function CreateEntitlementsFields({
  subscriptionTier,
  onTierChange,
  value,
  onChange,
  showAdvanced = false,
  onToggleAdvanced,
}: Props) {
  return (
    <div className="entitlement-matrix" style={{ gridColumn: "1 / -1" }}>
      <p className="form-section-title" style={{ margin: "0.5rem 0 0" }}>
        Subscription tier
      </p>
      <p className="page-subtitle" style={{ marginTop: 0 }}>
        New customers are provisioned from the tier bundle. Entitlements sync automatically on
        create — use advanced overrides only for MSSP exceptions.
      </p>

      <label className="form-label">
        Contracted tier
        <select
          className="form-input"
          value={subscriptionTier}
          onChange={(e) => onTierChange(e.target.value as StandardSubscriptionTier)}
        >
          {TIER_CATALOG.map((t) => (
            <option key={t.tier} value={t.tier}>
              {t.name} — {t.subtitle}
            </option>
          ))}
        </select>
      </label>
      <p className="page-subtitle" style={{ marginTop: "0.35rem" }}>
        {TIER_CATALOG.find((t) => t.tier === subscriptionTier)?.tagline}
      </p>

      {onToggleAdvanced && (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          style={{ marginTop: "0.75rem" }}
          onClick={() => onToggleAdvanced(!showAdvanced)}
        >
          {showAdvanced ? "Hide" : "Show"} advanced entitlement overrides (MSSP only)
        </button>
      )}

      {showAdvanced && (
        <>
          <div className="entitlement-section-label" style={{ marginTop: "1rem" }}>
            Advanced overrides
          </div>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={value.wazuh_siem}
              onChange={(e) => onChange({ ...value, wazuh_siem: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("log_event_monitoring")}</strong>
              <span className="entitlement-hint">{catalogShortHint("log_event_monitoring")}</span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={value.greenbone_enabled}
              onChange={(e) => onChange({ ...value, greenbone_enabled: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("vulnerability_management")}</strong>
              <span className="entitlement-hint">{catalogShortHint("vulnerability_management")}</span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={Boolean(value.cloud_identity_protection_enabled)}
              onChange={(e) =>
                onChange({ ...value, cloud_identity_protection_enabled: e.target.checked })
              }
            />
            <span>
              <strong>{catalogDisplayName("cloud_identity_protection")}</strong>
              <span className="entitlement-hint">
                {catalogShortHint("cloud_identity_protection")}
              </span>
            </span>
          </label>

          <label className="entitlement-row">
            <input
              type="checkbox"
              checked={value.zeek_enabled}
              onChange={(e) => onChange({ ...value, zeek_enabled: e.target.checked })}
            />
            <span>
              <strong>{catalogDisplayName("network_detection_response")}</strong>
              <span className="entitlement-hint">
                {catalogShortHint("network_detection_response")}
              </span>
            </span>
          </label>

          <label className="form-label form-grid-full">
            Contract / rollout notes (optional)
            <textarea
              className="form-input"
              rows={2}
              maxLength={2000}
              value={value.roadmap_notes}
              onChange={(e) => onChange({ ...value, roadmap_notes: e.target.value })}
            />
          </label>
        </>
      )}
    </div>
  );
}
