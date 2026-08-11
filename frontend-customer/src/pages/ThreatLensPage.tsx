import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ThreatLensExtractResult,
  ThreatLensJob,
  extractThreatLensIocs,
  getCustomerEntitlements,
  getThreatLensJobs,
  getThreatLensJob,
  runThreatLensSweep,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

/**
 * Kevantic ThreatLens — paste advisory text, extract IOCs, run 90-day retrospective sweep.
 * Requires Threat Intelligence and/or Endpoint Forensics entitlement (Cards 7/8).
 * Works for appliance tenants (Modes 2/4) and cloud-direct tenants (Modes 1/3).
 */
export default function ThreatLensPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [sweeping, setSweeping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ThreatLensExtractResult | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<ThreatLensJob | null>(null);
  const [jobs, setJobs] = useState<ThreatLensJob[]>([]);

  function refreshJobs() {
    if (!shortCode || !enabled) return;
    getThreatLensJobs(shortCode, { page_size: 10 })
      .then((res) => setJobs(res.jobs || []))
      .catch(() => undefined);
  }

  useEffect(() => {
    if (!shortCode) {
      setLoading(false);
      return;
    }
    setLoading(true);
    getCustomerEntitlements(shortCode)
      .then((ent) => {
        const ok = Boolean(ent.threat_intelligence_enabled || ent.endpoint_forensics_enabled);
        setEnabled(ok);
        setError(null);
      })
      .catch((err) => {
        setEnabled(false);
        setError(
          err instanceof ApiError ? err.message : "Unable to load entitlements for ThreatLens."
        );
      })
      .finally(() => setLoading(false));
  }, [shortCode]);

  useEffect(() => {
    refreshJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode, enabled]);

  useEffect(() => {
    if (!shortCode || !jobId || !enabled) return;
    let cancelled = false;
    const tick = () => {
      getThreatLensJob(shortCode, jobId)
        .then((res) => {
          if (!cancelled) setJob(res.job);
          if (res.job?.status === "COMPLETED" || res.job?.status === "FAILED") {
            refreshJobs();
          }
        })
        .catch(() => undefined);
    };
    tick();
    const id = window.setInterval(tick, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode, jobId, enabled]);

  async function onExtract() {
    if (!shortCode) return;
    setExtracting(true);
    setError(null);
    try {
      const res = await extractThreatLensIocs(shortCode, { text, url: url || undefined });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to extract indicators.");
    } finally {
      setExtracting(false);
    }
  }

  async function onSweep() {
    if (!shortCode) return;
    setSweeping(true);
    setError(null);
    try {
      const res = await runThreatLensSweep(shortCode, {
        text,
        url: url || undefined,
        iocs: result?.ioc_values,
        lookback_days: 90,
      });
      setJobId(res.job_id);
      setJob({
        id: res.job_id,
        status: res.status,
        execution_mode: res.execution_mode,
        matches_count: 0,
        iocs: result?.ioc_values || [],
      });
      refreshJobs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to start retrospective sweep.");
    } finally {
      setSweeping(false);
    }
  }

  if (!shortCode) {
    return (
      <div className="page">
        <h1 className="page-title">ThreatLens</h1>
        <div className="state-message state-error">Tenant scope missing from session.</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Kevantic ThreatLens</h1>
        <p className="muted">Checking service entitlements…</p>
      </div>
    );
  }

  if (!enabled) {
    return (
      <div className="page">
        <h1 className="page-title">Kevantic ThreatLens</h1>
        <p className="page-lead">
          ThreatLens extracts IOCs from advisories and runs 90-day retrospective sweeps. It is part of
          Threat Intelligence and/or Endpoint Forensics &amp; Deception.
        </p>
        {error && <p className="form-error">{error}</p>}
        <div className="panel">
          <p>
            This capability is not active yet. Request{" "}
            <strong>Threat Intelligence</strong> or{" "}
            <strong>Endpoint Forensics &amp; Deception</strong> from your{" "}
            <Link to="/services">Service Portfolio</Link>, or ask your MSSP to enable them.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page threatlens-page">
      <h1 className="page-title">Kevantic ThreatLens</h1>
      <p className="page-lead">
        Paste a security advisory, report, or URL. ThreatLens extracts indicators and can run a
        90-day Kevantic Retrospective Engine sweep across your Data Lake — on-appliance or in the
        cloud SOC, depending on your deployment mode.
      </p>
      {error && <p className="form-error">{error}</p>}

      <div className="panel" style={{ marginBottom: "1.25rem" }}>
        <label className="form-label" htmlFor="tl-text">
          Advisory / report text
        </label>
        <textarea
          id="tl-text"
          className="form-input"
          rows={10}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste raw advisory text, IOC lists, or incident notes…"
        />
        <label className="form-label" htmlFor="tl-url" style={{ marginTop: "0.85rem" }}>
          Or advisory URL (optional)
        </label>
        <input
          id="tl-url"
          className="form-input"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…"
        />
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "1rem" }}>
          <button type="button" className="btn btn-ghost" disabled={extracting} onClick={onExtract}>
            {extracting ? "Extracting…" : "Extract IOCs"}
          </button>
          <button type="button" className="btn btn-primary" disabled={sweeping} onClick={onSweep}>
            {sweeping ? "Queuing…" : "Run 90-Day Retrospective Sweep"}
          </button>
        </div>
      </div>

      {result && (
        <div className="panel" style={{ marginBottom: "1.25rem" }}>
          <h2 className="page-subtitle" style={{ marginTop: 0 }}>
            Parsed IOC tags
          </h2>
          <p className="muted">
            {result.counts.total} indicators · {result.counts.ips} IPs · {result.counts.domains}{" "}
            domains · {result.counts.hashes} hashes · {result.counts.cves} CVEs
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
            {(result.iocs || []).slice(0, 80).map((ioc) => (
              <span
                key={`${ioc.type}-${ioc.value}`}
                className="badge"
                title={ioc.type}
                style={{ fontFamily: "ui-monospace, monospace" }}
              >
                {ioc.type}: {ioc.value}
              </span>
            ))}
          </div>
        </div>
      )}

      {job && (
        <div className="panel" style={{ marginBottom: "1.25rem" }}>
          <h2 className="page-subtitle" style={{ marginTop: 0 }}>
            Active sweep
          </h2>
          <table className="data-table">
            <tbody>
              <tr>
                <th>Job</th>
                <td className="cell-mono">{job.id}</td>
              </tr>
              <tr>
                <th>Status</th>
                <td>{job.status}</td>
              </tr>
              <tr>
                <th>Execution mode</th>
                <td>{job.execution_mode}</td>
              </tr>
              <tr>
                <th>Matches</th>
                <td>{job.matches_count ?? 0}</td>
              </tr>
            </tbody>
          </table>
          {job.status === "COMPLETED" && (job.matched_details?.length || 0) > 0 ? (
            <p className="muted" style={{ marginTop: "0.75rem" }}>
              {job.matches_count} historical hit(s) returned. Details are tenant-scoped for your SOC
              review.
            </p>
          ) : null}
        </div>
      )}

      <div className="panel">
        <h2 className="page-subtitle" style={{ marginTop: 0 }}>
          Recent retrospective jobs
        </h2>
        {jobs.length === 0 ? (
          <p className="muted">No sweeps yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Created</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Matches</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td className="cell-mono">{j.created_at ?? "—"}</td>
                  <td>{j.execution_mode}</td>
                  <td>{j.status}</td>
                  <td>{j.matches_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
