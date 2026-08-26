import { useEffect, useRef, useState } from "react";
import {
  executeEdrAction,
  getEdrActionStatus,
  getLiveProcesses,
  statusBadgeLabel,
  type EdrActionType,
} from "../../api/edr";
import { NIKTIAR } from "../../config/niktiairBrands";

type Props = {
  tenantShortCode: string;
  incidentNumber: string;
  agentId?: string | null;
  canExecute: boolean;
};

const TERMINAL = new Set(["success", "failed", "verified", "executed"]);

export default function EdrControlPanel({
  tenantShortCode,
  incidentNumber,
  agentId,
  canExecute,
}: Props) {
  const [pid, setPid] = useState("");
  const [processName, setProcessName] = useState("");
  const [liveMatches, setLiveMatches] = useState<
    { pid: number; name?: string | null; path?: string | null }[]
  >([]);
  const [hash, setHash] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [badge, setBadge] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<EdrActionType | null>(null);
  const [lastExecutionId, setLastExecutionId] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
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
        process_name: processName.trim() || undefined,
        file_hash_sha256: hash || undefined,
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

  async function findLive() {
    if (!canExecute || !agentId || !processName.trim()) return;
    setBusy(true);
    setStatus("Asking endpoint for live processes…");
    try {
      const res = await getLiveProcesses({
        agentId,
        processName: processName.trim(),
        tenantShortCode,
      });
      setLiveMatches(res.processes || []);
      if (res.processes?.length === 1) {
        setPid(String(res.processes[0].pid));
      }
      setStatus(
        res.processes?.length
          ? `Live on endpoint: ${res.processes
              .map((p) => `${p.name || processName} pid=${p.pid}`)
              .join(", ")}`
          : res.message || "No live matching process on endpoint"
      );
      setBadge(res.processes?.length ? "Live inventory" : "Not found");
    } catch (e) {
      setBadge("Failed");
      setStatus(e instanceof Error ? e.message : "Live process lookup failed");
      setLiveMatches([]);
    } finally {
      setBusy(false);
    }
  }

  if (!canExecute) {
    return (
      <div className="edr-control-panel card-surface">
        <h3 className="section-title" style={{ marginTop: "1rem" }}>
          EDR control
        </h3>
        <p className="muted">
          Containment actions require platform admin, SOC manager, or SOC analyst role.
        </p>
      </div>
    );
  }

  const canKill = Boolean(pid || processName.trim());

  return (
    <div className="edr-control-panel card-surface">
      <h3 className="section-title" style={{ marginTop: "1rem" }}>
        EDR control
      </h3>
      <label className="form-label">
        Process name (live on endpoint)
        <input
          className="form-input"
          placeholder="notepad.exe"
          value={processName}
          onChange={(e) => setProcessName(e.target.value)}
        />
      </label>
      <div className="edr-control-actions" style={{ marginBottom: "0.75rem" }}>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy || !agentId || !processName.trim()}
          onClick={() => void findLive()}
        >
          Find live PID
        </button>
      </div>
      {liveMatches.length > 0 ? (
        <ul className="muted" style={{ marginTop: 0 }}>
          {liveMatches.map((m) => (
            <li key={m.pid}>
              <button type="button" className="btn btn-link" onClick={() => setPid(String(m.pid))}>
                {m.name || processName} pid={m.pid}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <label className="form-label">
        Target PID (optional if name set)
        <input className="form-input" value={pid} onChange={(e) => setPid(e.target.value)} />
      </label>
      <label className="form-label">
        File hash (SHA-256)
        <input className="form-input" value={hash} onChange={(e) => setHash(e.target.value)} />
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
                  "All network traffic will be blocked except " +
                  NIKTIAR.coreTelemetry +
                  " management ports 1514/1515 " +
                  "(plus DHCP/loopback so the agent can stay reachable for Un-isolate). " +
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
          disabled={busy || !canKill}
          onClick={() => void run("KILL_PROCESS")}
        >
          Kill process
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy || hash.length !== 64}
          onClick={() => void run("BLOCK_HASH")}
        >
          Block hash
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
