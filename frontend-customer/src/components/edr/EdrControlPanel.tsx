import { useEffect, useRef, useState } from "react";
import {
  executeEdrAction,
  getEdrActionStatus,
  statusBadgeLabel,
  type EdrActionType,
} from "../../api/edr";

type Props = {
  tenantShortCode: string;
  incidentNumber: string;
  agentId?: string | null;
  canExecute: boolean;
  defaultPid?: number;
  downloadUrl?: string | null;
};

const TERMINAL = new Set(["success", "failed", "verified", "executed"]);

export default function EdrControlPanel({
  tenantShortCode,
  incidentNumber,
  agentId,
  canExecute,
  defaultPid,
  downloadUrl: initialDownload,
}: Props) {
  const [pid, setPid] = useState(String(defaultPid ?? ""));
  const [status, setStatus] = useState<string | null>(null);
  const [badge, setBadge] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<EdrActionType | null>(null);
  const [lastExecutionId, setLastExecutionId] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(initialDownload ?? null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  async function pollStatus(executionId: string, action: EdrActionType) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    let attempts = 0;
    pollRef.current = window.setInterval(() => {
      void (async () => {
        attempts += 1;
        try {
          const poll = await getEdrActionStatus(executionId, tenantShortCode);
          setBadge(statusBadgeLabel(poll.status, action));
          setStatus(`${poll.status}: ${poll.result_message ?? ""}`);
          if (poll.download_url) setDownloadUrl(poll.download_url);
          if (TERMINAL.has(poll.status) || attempts >= 20) {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            setBusy(false);
          }
        } catch {
          if (attempts >= 5 && pollRef.current) {
            window.clearInterval(pollRef.current);
            pollRef.current = null;
            setBusy(false);
          }
        }
      })();
    }, 2000);
  }

  async function run(action: EdrActionType, extra: Record<string, unknown> = {}) {
    if (!canExecute) return;
    setBusy(true);
    setLastAction(action);
    setBadge("Executing…");
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
      setLastExecutionId(res.execution_id);
      setBadge(statusBadgeLabel(res.status, action));
      setStatus(`${res.status}: ${res.message}`);
      if (TERMINAL.has(res.status)) {
        setBusy(false);
        void getEdrActionStatus(res.execution_id, tenantShortCode).then((poll) => {
          if (poll.download_url) setDownloadUrl(poll.download_url);
          setBadge(statusBadgeLabel(poll.status, action));
        });
      } else {
        void pollStatus(res.execution_id, action);
      }
    } catch (e) {
      setBadge("Failed");
      setStatus(e instanceof Error ? e.message : "Action failed");
      setBusy(false);
    }
  }

  if (!canExecute && !downloadUrl) {
    return (
      <div className="edr-control-panel card-surface">
        <h3 className="section-title" style={{ marginTop: 0 }}>
          Endpoint response
        </h3>
        <p className="muted">Read-only. Contact your SOC or use a customer admin account for containment.</p>
      </div>
    );
  }

  return (
    <div className="edr-control-panel card-surface">
      <h3 className="section-title" style={{ marginTop: 0 }}>
        Endpoint response
      </h3>
      {canExecute ? (
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
                  "Quarantine this host?\n\n" +
                    "All network traffic will be blocked except the SOC Manager path " +
                    "(and DHCP/loopback). This is full network quarantine, not ping-only. " +
                    "The host stays isolated until you click Un-isolate."
                )
              ) {
                  void run("ISOLATE_HOST", { confirm_isolation: true });
                }
              }}
            >
              Isolate host (quarantine)
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => {
                if (window.confirm("Lift network quarantine and restore normal connectivity?")) {
                  void run("UNISOLATE_HOST");
                }
              }}
            >
              Un-isolate host
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
            {badge === "Failed" && lastAction ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() =>
                  void run(lastAction, {
                    confirm_isolation: lastAction === "ISOLATE_HOST",
                    retry_of_execution_id: lastExecutionId ?? undefined,
                  })
                }
              >
                Retry
              </button>
            ) : null}
          </div>
        </>
      ) : null}
      {badge ? (
        <p className="edr-action-status">
          <span className={`edr-status-badge edr-status-${badge.toLowerCase().replace(/[^a-z]/g, "")}`}>
            {badge}
          </span>
          {status ? <span className="muted"> — {status}</span> : null}
        </p>
      ) : null}
      {downloadUrl ? (
        <p className="edr-forensics-download">
          <a href={downloadUrl} target="_blank" rel="noreferrer">
            Download forensic package
          </a>
        </p>
      ) : null}
    </div>
  );
}
