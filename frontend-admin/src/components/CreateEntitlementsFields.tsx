/** Compact contracted-services matrix for Add Customer (KB-075).
 * Labels match Admin Service Catalog (`data/serviceCatalog.ts`).
 */

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
  value: CreateEntitlementsState;
  onChange: (next: CreateEntitlementsState) => void;
};

export default function CreateEntitlementsFields({ value, onChange }: Props) {
  return (
    <div className="entitlement-matrix" style={{ gridColumn: "1 / -1" }}>
      <p className="form-section-title" style={{ margin: "0.5rem 0 0" }}>
        Contracted services
      </p>
      <p className="page-subtitle" style={{ marginTop: 0 }}>
        Same names as the Service Catalog. New customers start with Core (log monitoring + incident
        response). Turn on add-ons only when they are in the contract; otherwise customers request
        consulting from the portal and Junexis sales approves in Admin.
      </p>

      <div className="entitlement-section-label">Core (included)</div>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.wazuh_siem}
          onChange={(e) => onChange({ ...value, wazuh_siem: e.target.checked })}
        />
        <span>
          <strong>{catalogDisplayName("log_event_monitoring")}</strong>
          <span className="entitlement-hint">{catalogShortHint("log_event_monitoring")}</span>
          <select
            className="form-input entitlement-inline"
            value={value.wazuh_retention_days}
            disabled={!value.wazuh_siem}
            onChange={(e) =>
              onChange({ ...value, wazuh_retention_days: Number(e.target.value) })
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
          value={value.thehive_mode}
          onChange={(e) => onChange({ ...value, thehive_mode: e.target.value })}
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
          value={value.shuffle_mode}
          onChange={(e) => onChange({ ...value, shuffle_mode: e.target.value })}
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
          checked={value.greenbone_enabled}
          onChange={(e) => onChange({ ...value, greenbone_enabled: e.target.checked })}
        />
        <span>
          <strong>{catalogDisplayName("vulnerability_management")}</strong>
          <span className="entitlement-hint">{catalogShortHint("vulnerability_management")}</span>
          <select
            className="form-input entitlement-inline"
            value={value.greenbone_cadence}
            disabled={!value.greenbone_enabled}
            onChange={(e) => onChange({ ...value, greenbone_cadence: e.target.value })}
          >
            <option value="weekly">Weekly scans</option>
            <option value="monthly">Monthly scans</option>
            <option value="off">Cadence off</option>
          </select>
        </span>
      </label>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={Boolean(value.continuous_compliance_enabled)}
          onChange={(e) =>
            onChange({ ...value, continuous_compliance_enabled: e.target.checked })
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
          checked={value.zeek_enabled}
          onChange={(e) => onChange({ ...value, zeek_enabled: e.target.checked })}
        />
        <span>
          <strong>{catalogDisplayName("network_detection_response")}</strong>
          <span className="entitlement-hint">{catalogShortHint("network_detection_response")}</span>
        </span>
      </label>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.misp_enabled}
          onChange={(e) => onChange({ ...value, misp_enabled: e.target.checked })}
        />
        <span>
          <strong>{catalogDisplayName("threat_intelligence")}</strong>
          <span className="entitlement-hint">{catalogShortHint("threat_intelligence")}</span>
        </span>
      </label>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.velociraptor_enabled}
          onChange={(e) => onChange({ ...value, velociraptor_enabled: e.target.checked })}
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
          checked={Boolean(value.external_attack_surface_enabled)}
          onChange={(e) =>
            onChange({ ...value, external_attack_surface_enabled: e.target.checked })
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
          checked={Boolean(value.cloud_identity_protection_enabled)}
          onChange={(e) =>
            onChange({ ...value, cloud_identity_protection_enabled: e.target.checked })
          }
        />
        <span>
          <strong>{catalogDisplayName("cloud_identity_protection")}</strong>
          <span className="entitlement-hint">{catalogShortHint("cloud_identity_protection")}</span>
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
    </div>
  );
}
