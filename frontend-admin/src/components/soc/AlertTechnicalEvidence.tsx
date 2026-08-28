import { useMemo, useState } from "react";

export type AlertTelemetryEvidence = {
  process_name?: string | null;
  parent_process_name?: string | null;
  parent_process?: string | null;
  command_line?: string | null;
  parent_command_line?: string | null;
  current_directory?: string | null;
  file_path?: string | null;
  file_name?: string | null;
  process_id?: string | null;
  parent_process_id?: string | null;
  integrity_level?: string | null;
  user_sid?: string | null;
  logon_id?: string | null;
  logon_guid?: string | null;
  process_guid?: string | null;
  parent_process_guid?: string | null;
  hash_md5?: string | null;
  hash_sha256?: string | null;
  hash_imphash?: string | null;
  hashes_raw?: string | null;
  mitre_tactics?: string[] | null;
  mitre_techniques?: string[] | null;
  win_eventdata?: Record<string, unknown> | null;
};

type Props = {
  alert: AlertTelemetryEvidence;
  renderProcessLink?: (value: string | null | undefined) => React.ReactNode;
  renderPathLink?: (value: string | null | undefined) => React.ReactNode;
};

function display(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  return text || "—";
}

function isGuidLike(value: string): boolean {
  return /^[{]?[0-9a-fA-F-]{36}[}]?$/.test(value.trim());
}

function formatTelemetryValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  if (/time|date/i.test(key) && /^\d{4}-\d{2}-\d{2}/.test(text)) {
    const d = new Date(text);
    if (!Number.isNaN(d.getTime())) return d.toLocaleString();
  }
  return text;
}

function CopyableValue({ value }: { value: string }) {
  if (!value || value === "—") return <span>—</span>;
  const copy = () => navigator.clipboard?.writeText(value).catch(() => undefined);
  const guid = isGuidLike(value);
  return (
    <span className={`telemetry-value${guid ? " telemetry-value--guid" : ""}`}>
      <code>{value}</code>
      <button type="button" className="btn btn-ghost btn-small telemetry-copy" onClick={copy}>
        Copy
      </button>
    </span>
  );
}

export default function AlertTechnicalEvidence({
  alert,
  renderProcessLink,
  renderPathLink,
}: Props) {
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [metadataFilter, setMetadataFilter] = useState("");

  const parentProcess =
    alert.parent_process_name ?? alert.parent_process ?? null;

  const metadataEntries = useMemo(() => {
    const raw = alert.win_eventdata ?? {};
    return Object.entries(raw)
      .filter(([, v]) => v !== null && v !== undefined && String(v).trim() !== "")
      .filter(([k, v]) => {
        const q = metadataFilter.trim().toLowerCase();
        if (!q) return true;
        return (
          k.toLowerCase().includes(q) ||
          String(v).toLowerCase().includes(q)
        );
      })
      .sort(([a], [b]) => a.localeCompare(b));
  }, [alert.win_eventdata, metadataFilter]);

  return (
    <div className="alert-technical-evidence">
      <div className="telemetry-card">
        <h3 className="telemetry-card__title">Process ancestry</h3>
        <div className="telemetry-ancestry-grid">
          <div>
            <span className="telemetry-label">Process</span>
            <div className="telemetry-value-block">
              {renderProcessLink
                ? renderProcessLink(alert.process_name)
                : display(alert.process_name)}
            </div>
          </div>
          <div>
            <span className="telemetry-label">Parent process</span>
            <div className="telemetry-value-block cell-mono">{display(parentProcess)}</div>
          </div>
          <div className="telemetry-span-2">
            <span className="telemetry-label">Command line</span>
            <div className="telemetry-value-block cell-mono">{display(alert.command_line)}</div>
          </div>
          <div className="telemetry-span-2">
            <span className="telemetry-label">Parent command line</span>
            <div className="telemetry-value-block cell-mono">
              {display(alert.parent_command_line)}
            </div>
          </div>
          <div>
            <span className="telemetry-label">Current directory</span>
            <div className="telemetry-value-block cell-mono">
              {display(alert.current_directory)}
            </div>
          </div>
          <div>
            <span className="telemetry-label">File path</span>
            <div className="telemetry-value-block">
              {renderPathLink ? renderPathLink(alert.file_path) : display(alert.file_path)}
            </div>
          </div>
        </div>
      </div>

      <div className="telemetry-exec-strip">
        <span><strong>PID</strong> {display(alert.process_id)}</span>
        <span><strong>Parent PID</strong> {display(alert.parent_process_id)}</span>
        <span><strong>Integrity</strong> {display(alert.integrity_level)}</span>
        <span><strong>User SID</strong> <CopyableValue value={display(alert.user_sid)} /></span>
        <span><strong>Logon ID</strong> {display(alert.logon_id)}</span>
        <span><strong>Process GUID</strong> <CopyableValue value={display(alert.process_guid)} /></span>
      </div>

      <table className="data-table">
        <tbody>
          <tr><th>File name</th><td>{display(alert.file_name)}</td></tr>
          <tr>
            <th>SHA256</th>
            <td className="cell-mono"><CopyableValue value={display(alert.hash_sha256)} /></td>
          </tr>
          <tr>
            <th>MD5</th>
            <td className="cell-mono"><CopyableValue value={display(alert.hash_md5)} /></td>
          </tr>
          <tr>
            <th>IMPHASH</th>
            <td className="cell-mono"><CopyableValue value={display(alert.hash_imphash)} /></td>
          </tr>
          <tr>
            <th>MITRE tactics</th>
            <td>{alert.mitre_tactics?.length ? alert.mitre_tactics.join(", ") : "—"}</td>
          </tr>
          <tr>
            <th>MITRE techniques</th>
            <td>{alert.mitre_techniques?.length ? alert.mitre_techniques.join(", ") : "—"}</td>
          </tr>
        </tbody>
      </table>

      <div className="telemetry-metadata-panel">
        <button
          type="button"
          className="btn btn-ghost telemetry-metadata-toggle"
          onClick={() => setMetadataOpen((v) => !v)}
          aria-expanded={metadataOpen}
        >
          {metadataOpen ? "▾" : "▸"} Complete endpoint metadata
          {metadataEntries.length > 0 ? ` (${metadataEntries.length})` : ""}
        </button>
        {metadataOpen ? (
          <div className="telemetry-metadata-body">
            <input
              type="search"
              className="filter-input telemetry-metadata-search"
              placeholder="Search metadata keys or values…"
              value={metadataFilter}
              onChange={(e) => setMetadataFilter(e.target.value)}
            />
            {metadataEntries.length ? (
              <div className="telemetry-kv-grid">
                {metadataEntries.map(([key, value]) => (
                  <div key={key} className="telemetry-kv-row">
                    <div className="telemetry-kv-key">{key}</div>
                    <div className="telemetry-kv-val cell-mono">
                      {isGuidLike(String(value)) ? (
                        <CopyableValue value={String(value)} />
                      ) : (
                        formatTelemetryValue(key, value)
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="page-subtitle">No structured endpoint metadata for this alert.</p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
