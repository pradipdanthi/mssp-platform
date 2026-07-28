/** Compact contracted-services matrix for Add Customer (KB-075). */

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
        Select the services in this customer&apos;s contract. Matching backend slots are
        provisioned automatically where the platform supports it.
      </p>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.wazuh_siem}
          onChange={(e) => onChange({ ...value, wazuh_siem: e.target.checked })}
        />
        <span>
          <strong>SIEM &amp; Log Management</strong>
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
        <span className="entitlement-label">Incident Response &amp; Casework</span>
        <select
          className="form-input"
          value={value.thehive_mode}
          onChange={(e) => onChange({ ...value, thehive_mode: e.target.value })}
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
          value={value.shuffle_mode}
          onChange={(e) => onChange({ ...value, shuffle_mode: e.target.value })}
        >
          <option value="standard">Standard Playbooks</option>
          <option value="custom">Custom Playbooks</option>
          <option value="off">Off</option>
        </select>
      </label>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.greenbone_enabled}
          onChange={(e) => onChange({ ...value, greenbone_enabled: e.target.checked })}
        />
        <span>
          <strong>Vulnerability Management (Nuclei + Vuls)</strong>
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
          checked={value.zeek_enabled}
          onChange={(e) => onChange({ ...value, zeek_enabled: e.target.checked })}
        />
        <span>
          <strong>Network Traffic Analysis</strong>
          <span className="entitlement-hint">Optional add-on</span>
        </span>
      </label>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.misp_enabled}
          onChange={(e) => onChange({ ...value, misp_enabled: e.target.checked })}
        />
        <span>
          <strong>Threat Intelligence Sharing</strong>
          <span className="entitlement-hint">Optional add-on</span>
        </span>
      </label>

      <label className="entitlement-row">
        <input
          type="checkbox"
          checked={value.velociraptor_enabled}
          onChange={(e) => onChange({ ...value, velociraptor_enabled: e.target.checked })}
        />
        <span>
          <strong>Endpoint Forensics &amp; Hunting</strong>
          <span className="entitlement-hint">Optional add-on</span>
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
