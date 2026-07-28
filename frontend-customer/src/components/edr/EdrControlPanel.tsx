import { useState } from "react";
import { executeEdrAction, getEdrActionStatus, type EdrActionType } from "../../api/edr";

type Props = {
  tenantShortCode: string;
  incidentNumber: string;
  agentId?: string | null;
  canExecute: boolean;
  defaultPid?: number;
};

export default function EdrControlPanel({
  tenantShortCode,
  incidentNumber,
  agentId,
  canExecute,
  defaultPid,
}: Props) {
  const [pid, setPid] = useState(String(defaultPid ?? ""));
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
      const poll = await getEdrActionStatus(res.execution_id, tenantShortCode);
      setStatus(`${poll.status}: ${poll.result_message ?? res.message}`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="edr-control-panel card-surface">
      <h3 className="section-title" style={{ marginTop: 0 }}>
        EDR response
      </h3>
      {!canExecute ? (
        <p className="muted">Read-only. Contact your SOC or use a customer admin account for containment.</p>
      ) : (
        <>
          <label className="form-label">
            Target PID (kill)
            <input
              className="form-input"
              value={pid}
              onChange={(e) => setPid(e.target.value)}
              placeholder="e.g. 4242"
            />
          </label>
          <div className="edr-control-actions">
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    "Isolate this host? Network access will be restricted per your Wazuh active-response policy."
                  )
                ) {
                  void run("ISOLATE_HOST", { confirm_isolation: true });
                }
              }}
            >
              Isolate host
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy || !pid}
              onClick={() => void run("KILL_PROCESS")}
            >
              Kill process
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void run("COLLECT_FORENSICS")}
            >
              Collect forensics
            </button>
          </div>
        </>
      )}
      {status ? <p className="edr-action-status">{status}</p> : null}
    </div>
  );
}
