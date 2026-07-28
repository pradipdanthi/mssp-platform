import { useState } from "react";
import { executeEdrAction, type EdrActionType } from "../../api/edr";

type Props = {
  tenantShortCode: string;
  incidentNumber: string;
  agentId?: string | null;
  canExecute: boolean;
};

export default function EdrControlPanel({
  tenantShortCode,
  incidentNumber,
  agentId,
  canExecute,
}: Props) {
  const [pid, setPid] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: EdrActionType, extra: Record<string, unknown> = {}) {
    if (!canExecute) return;
    setBusy(true);
    setStatus("Pending…");
    try {
      const res = await executeEdrAction({
        action_type: action,
        tenant_short_code: tenantShortCode,
        incident_number: incidentNumber,
        agent_id: agentId ?? undefined,
        pid: pid ? Number(pid) : undefined,
        ...extra,
      });
      setStatus(`${res.status}: ${res.message}`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!canExecute) return null;

  return (
    <div className="edr-control-panel card-surface">
      <h3 className="section-title" style={{ marginTop: "1rem" }}>
        EDR control
      </h3>
      <label className="form-label">
        Target PID
        <input className="form-input" value={pid} onChange={(e) => setPid(e.target.value)} />
      </label>
      <div className="edr-control-actions">
        <button
          type="button"
          className="btn btn-danger"
          disabled={busy}
          onClick={() => {
            if (window.confirm("Isolate host via Wazuh active response?")) {
              void run("ISOLATE_HOST", { confirm_isolation: true });
            }
          }}
        >
          Isolate host
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy || !pid} onClick={() => void run("KILL_PROCESS")}>
          Kill process
        </button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void run("COLLECT_FORENSICS")}>
          Collect forensics
        </button>
      </div>
      {status ? <p className="edr-action-status">{status}</p> : null}
    </div>
  );
}
