import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ThreatIntelCampaign,
  ThreatIntelIoc,
  ThreatIntelSummary,
  getCustomerEntitlements,
  getThreatIntelCampaigns,
  getThreatIntelIocs,
  getThreatIntelSummary,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const REP_FILTERS = ["ALL", "MALICIOUS", "SUSPICIOUS", "BENIGN"];
const TYPE_FILTERS = ["ALL", "IP", "DOMAIN", "FILE_HASH", "URL"];

/**
 * Threat Intelligence & Enrichment — customer enrichment view.
 * Engine label: MSSP Global Threat Intelligence Engine.
 */
export default function ThreatIntelPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [summary, setSummary] = useState<ThreatIntelSummary | null>(null);
  const [iocs, setIocs] = useState<ThreatIntelIoc[]>([]);
  const [campaigns, setCampaigns] = useState<ThreatIntelCampaign[]>([]);
  const [reputation, setReputation] = useState("ALL");
  const [iocType, setIocType] = useState("ALL");
  const [tab, setTab] = useState<"iocs" | "campaigns">("iocs");
  const [expanded, setExpanded] = useState<string | null>(null);

  function loadAll() {
    if (!shortCode) {
      setLoading(false);
      setError("Tenant scope missing from session.");
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      getCustomerEntitlements(shortCode),
      getThreatIntelSummary(shortCode),
      getThreatIntelIocs(shortCode, { page_size: 100 }),
      getThreatIntelCampaigns(shortCode),
    ])
      .then(([ent, sum, iocRes, campRes]) => {
        setEnabled(Boolean(ent.threat_intelligence_enabled || sum.has_data));
        setSummary(sum);
        setIocs(iocRes.iocs || []);
        setCampaigns(campRes.campaigns || []);
      })
      .catch((err) => {
        setError(
          err instanceof ApiError ? err.message : "Unable to load threat intelligence data."
        );
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortCode]);

  useEffect(() => {
    if (!shortCode || !enabled) return;
    getThreatIntelIocs(shortCode, {
      reputation_status: reputation === "ALL" ? undefined : reputation,
      ioc_type: iocType === "ALL" ? undefined : iocType,
      page_size: 100,
    })
      .then((res) => setIocs(res.iocs || []))
      .catch(() => undefined);
  }, [shortCode, reputation, iocType, enabled]);

  if (loading) {
    return (
      <div className="page">
        <h1 className="page-title">Threat Intelligence</h1>
        <p className="muted">Loading enrichment data…</p>
      </div>
    );
  }

  if (!enabled && !summary?.has_data) {
    return (
      <div className="page">
        <h1 className="page-title">Threat Intelligence</h1>
        <p className="page-lead">
          Enrich alerts with global indicator reputation, adversary context, and ATT&amp;CK mapping.
        </p>
        {error && <p className="form-error">{error}</p>}
        <div className="panel">
          <p>
            Threat Intelligence &amp; Enrichment is not active yet. Request it from your{" "}
            <Link to="/services">Service Portfolio</Link>, or ask your MSSP to enable enrichment
            for this tenant.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page threat-intel-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Threat Intelligence</h1>
          <p className="page-lead">
            Indicator enrichment from the{" "}
            {summary?.engine_label || "MSSP Global Threat Intelligence Engine"}.
          </p>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}

      <section className="easm-kpi-grid">
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Matched threat indicators</div>
          <div className="easm-kpi-value">{summary?.matched_threat_indicators ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">High-confidence malicious IOCs</div>
          <div className="easm-kpi-value">{summary?.high_confidence_malicious_iocs ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">MITRE ATT&amp;CK coverage</div>
          <div className="easm-kpi-value">{summary?.mitre_attack_coverage_count ?? 0}</div>
        </div>
        <div className="panel easm-kpi">
          <div className="easm-kpi-label">Active campaign advisories</div>
          <div className="easm-kpi-value">{summary?.active_campaign_advisories ?? 0}</div>
        </div>
      </section>

      <p className="muted">
        High-risk actor detections: {summary?.high_risk_actor_detections ?? 0}
        {summary?.mitre_tactics && summary.mitre_tactics.length > 0
          ? ` · Tactics: ${summary.mitre_tactics.slice(0, 6).join(", ")}`
          : ""}
      </p>

      <div className="tab-row" style={{ marginBottom: 12 }}>
        <button
          type="button"
          className={"tab-btn" + (tab === "iocs" ? " active" : "")}
          onClick={() => setTab("iocs")}
        >
          Matched indicators
        </button>
        <button
          type="button"
          className={"tab-btn" + (tab === "campaigns" ? " active" : "")}
          onClick={() => setTab("campaigns")}
        >
          Threat campaign bulletins
        </button>
      </div>

      {tab === "campaigns" ? (
        <section className="panel">
          <h2 className="panel-title">Threat campaign bulletins</h2>
          {campaigns.length === 0 ? (
            <p className="muted">No active campaign advisories.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Campaign</th>
                    <th>Industry</th>
                    <th>Actor</th>
                    <th>Published</th>
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c) => {
                    const open = expanded === c.id;
                    return (
                      <Fragment key={c.id}>
                        <tr
                          className="clickable-row"
                          onClick={() => setExpanded(open ? null : c.id)}
                        >
                          <td>
                            <span className={`severity-pill severity-${c.severity.toLowerCase()}`}>
                              {c.severity}
                            </span>
                          </td>
                          <td>{c.campaign_name}</td>
                          <td>{c.target_industry}</td>
                          <td>{c.threat_actor || "—"}</td>
                          <td>{c.published_at || "—"}</td>
                        </tr>
                        {open && (
                          <tr className="detail-row">
                            <td colSpan={5}>
                              <div className="compliance-remediation">
                                <strong>Advisory</strong>
                                <p>{c.summary}</p>
                                <strong>Recommended defenses</strong>
                                <p>{c.recommended_defenses}</p>
                                {c.mitre_techniques?.length > 0 && (
                                  <>
                                    <strong>ATT&amp;CK techniques</strong>
                                    <p>{c.mitre_techniques.join(" · ")}</p>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : (
        <section className="panel">
          <h2 className="panel-title">Enriched indicators</h2>
          <div className="tab-row">
            {REP_FILTERS.map((s) => (
              <button
                key={s}
                type="button"
                className={"tab-btn" + (reputation === s ? " active" : "")}
                onClick={() => setReputation(s)}
              >
                {s === "ALL" ? "All reputations" : s}
              </button>
            ))}
          </div>
          <div className="tab-row" style={{ marginTop: 8 }}>
            {TYPE_FILTERS.map((s) => (
              <button
                key={s}
                type="button"
                className={"tab-btn" + (iocType === s ? " active" : "")}
                onClick={() => setIocType(s)}
              >
                {s === "ALL" ? "All types" : s.replace("_", " ")}
              </button>
            ))}
          </div>
          {iocs.length === 0 ? (
            <p className="muted">No matched indicators for this filter.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Reputation</th>
                    <th>Indicator</th>
                    <th>Confidence</th>
                    <th>Threat actor</th>
                    <th>ATT&amp;CK</th>
                  </tr>
                </thead>
                <tbody>
                  {iocs.map((ioc) => {
                    const open = expanded === ioc.id;
                    const conf = Math.max(0, Math.min(100, Number(ioc.confidence_score) || 0));
                    return (
                      <Fragment key={ioc.id}>
                        <tr
                          className="clickable-row"
                          onClick={() => setExpanded(open ? null : ioc.id)}
                        >
                          <td>
                            <span
                              className={`severity-pill severity-${
                                ioc.reputation_status === "MALICIOUS"
                                  ? "critical"
                                  : ioc.reputation_status === "SUSPICIOUS"
                                    ? "medium"
                                    : "low"
                              }`}
                            >
                              {ioc.reputation_status}
                            </span>
                          </td>
                          <td>
                            <div>{ioc.ioc_value}</div>
                            <div className="muted">{ioc.ioc_type.replace("_", " ")}</div>
                          </td>
                          <td>
                            <div className="muted">{conf}%</div>
                            <div
                              style={{
                                height: 6,
                                background: "var(--border, #334)",
                                borderRadius: 3,
                                overflow: "hidden",
                                minWidth: 72,
                              }}
                            >
                              <div
                                style={{
                                  width: `${conf}%`,
                                  height: "100%",
                                  background:
                                    conf >= 80
                                      ? "var(--soc-severity-critical, #e11)"
                                      : conf >= 50
                                        ? "var(--soc-severity-medium, #e90)"
                                        : "var(--soc-severity-low, #3a7)",
                                }}
                              />
                            </div>
                          </td>
                          <td>{ioc.threat_actor}</td>
                          <td>
                            {(ioc.mitre_techniques || []).slice(0, 2).join(" · ") ||
                              (ioc.mitre_tactics || []).slice(0, 2).join(" · ") ||
                              "—"}
                          </td>
                        </tr>
                        {open && (
                          <tr className="detail-row">
                            <td colSpan={5}>
                              <div className="compliance-remediation">
                                <strong>Context</strong>
                                <p>{ioc.summary}</p>
                                <strong>Recommended action</strong>
                                <p>{ioc.recommended_action}</p>
                                {ioc.mitre_tactics?.length > 0 && (
                                  <>
                                    <strong>Tactics</strong>
                                    <p>{ioc.mitre_tactics.join(" · ")}</p>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
