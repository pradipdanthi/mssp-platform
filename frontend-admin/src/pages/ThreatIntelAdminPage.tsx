import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ThreatIntelCampaign,
  ThreatIntelIoc,
  ThreatIntelTenantSummary,
  getThreatIntelAdminSummary,
  getThreatIntelTenantCampaigns,
  getThreatIntelTenantIocs,
  ingestStixBundle,
  pullTaxiiFeed,
  syncThreatIntelTenant,
} from "../api/admin";
import { ApiError } from "../api/client";

/**
 * Admin Threat Intelligence console — IOC/campaign visibility, STIX ingest, TAXII pull.
 * Completes the Anomali-style feed operations gap for SOC staff.
 */
export default function ThreatIntelAdminPage() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("tenant") || "";

  const [tenants, setTenants] = useState<ThreatIntelTenantSummary[]>([]);
  const [iocs, setIocs] = useState<ThreatIntelIoc[]>([]);
  const [campaigns, setCampaigns] = useState<ThreatIntelCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"iocs" | "campaigns" | "ingest">("iocs");

  const [stixJson, setStixJson] = useState("");
  const [taxiiRoot, setTaxiiRoot] = useState("");
  const [taxiiCollection, setTaxiiCollection] = useState("");
  const [taxiiUser, setTaxiiUser] = useState("");
  const [taxiiPass, setTaxiiPass] = useState("");

  function loadSummary() {
    setLoading(true);
    setError(null);
    getThreatIntelAdminSummary()
      .then((res) => setTenants(res.tenants || []))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load threat intel summary.");
      })
      .finally(() => setLoading(false));
  }

  function loadTenantDetail(ref: string) {
    if (!ref) {
      setIocs([]);
      setCampaigns([]);
      return;
    }
    setDetailLoading(true);
    setError(null);
    Promise.all([
      getThreatIntelTenantIocs(ref, { page_size: 100 }),
      getThreatIntelTenantCampaigns(ref),
    ])
      .then(([iocRes, campRes]) => {
        setIocs(iocRes.iocs || []);
        setCampaigns(campRes.campaigns || []);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Unable to load tenant threat intel.");
      })
      .finally(() => setDetailLoading(false));
  }

  useEffect(() => {
    loadSummary();
  }, []);

  useEffect(() => {
    loadTenantDetail(selected);
  }, [selected]);

  function selectTenant(shortCode: string) {
    const next = new URLSearchParams(params);
    if (shortCode) next.set("tenant", shortCode);
    else next.delete("tenant");
    setParams(next, { replace: true });
  }

  async function handleSync() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await syncThreatIntelTenant(selected);
      setSuccess(
        `Synced threat intel for ${selected}. IOCs refreshed (${String(
          (res as { iocs_upserted?: number }).iocs_upserted ?? "ok"
        )}).`
      );
      loadSummary();
      loadTenantDetail(selected);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleStixIngest() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const parsed = JSON.parse(stixJson) as Record<string, unknown>;
      const res = await ingestStixBundle(selected, parsed);
      setSuccess(
        `STIX ingest complete — ${String((res as { iocs_upserted?: number }).iocs_upserted ?? 0)} IOC(s) upserted.`
      );
      setStixJson("");
      loadSummary();
      loadTenantDetail(selected);
      setTab("iocs");
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError("STIX JSON is invalid — paste a valid STIX 2.1 bundle.");
      } else {
        setError(err instanceof ApiError ? err.message : "STIX ingest failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleTaxiiPull(useConfigured: boolean) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await pullTaxiiFeed(selected, {
        use_configured_feed: useConfigured,
        api_root: taxiiRoot || undefined,
        collection_id: taxiiCollection || undefined,
        username: taxiiUser || undefined,
        password: taxiiPass || undefined,
      });
      const taxii = (res as { taxii?: { objects_pulled?: number } }).taxii;
      setSuccess(
        `TAXII pull complete — ${taxii?.objects_pulled ?? 0} object(s) pulled, ${String(
          (res as { iocs_upserted?: number }).iocs_upserted ?? 0
        )} IOC(s) upserted.`
      );
      setTaxiiPass("");
      loadSummary();
      loadTenantDetail(selected);
      setTab("iocs");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "TAXII pull failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <p>
        <Link to="/dashboard">← Dashboard</Link>
        {" · "}
        <Link to="/retrospective-hunts">Retro Hunts</Link>
      </p>
      <h1 className="page-title">Threat Intelligence &amp; Enrichment</h1>
      <p className="page-subtitle">
        SOC console for tenant IOCs and campaigns, STIX 2.1 ingest, and TAXII 2.x pulls — same
        catalog service customers see as Threat Intelligence &amp; Enrichment / ThreatLens.
      </p>

      {error && <div className="state-message state-error">{error}</div>}
      {success && <div className="state-message state-success">{success}</div>}

      <h2 className="section-title">Tenants</h2>
      {loading ? (
        <div className="state-message">Loading summary…</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Tenant</th>
              <th>IOCs</th>
              <th>Malicious</th>
              <th>Campaigns</th>
              <th>Last seen</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tenants.length === 0 ? (
              <tr>
                <td colSpan={6}>No active tenants.</td>
              </tr>
            ) : (
              tenants.map((t) => (
                <tr key={t.short_code} className={selected === t.short_code ? "is-selected" : ""}>
                  <td>
                    <strong>{t.tenant_name}</strong>{" "}
                    <span className="muted cell-mono">{t.short_code}</span>
                  </td>
                  <td>{t.ioc_count}</td>
                  <td>{t.malicious_count}</td>
                  <td>{t.campaign_count}</td>
                  <td className="cell-mono">{t.last_ioc_seen ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => selectTenant(t.short_code)}
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}

      {selected ? (
        <section className="card-surface" style={{ marginTop: "1.5rem", padding: "1.25rem" }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.75rem",
              alignItems: "center",
              marginBottom: "1rem",
            }}
          >
            <h2 className="section-title" style={{ margin: 0 }}>
              Selected: <span className="cell-mono">{selected}</span>
            </h2>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy}
              onClick={handleSync}
            >
              {busy ? "Working…" : "Sync enrichment"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => selectTenant("")}
            >
              Clear
            </button>
          </div>

          <div className="command-chip-row" style={{ marginBottom: "1rem" }}>
            {(
              [
                ["iocs", "IOCs"],
                ["campaigns", "Campaigns"],
                ["ingest", "STIX / TAXII ingest"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={"command-chip" + (tab === id ? " is-active" : "")}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {detailLoading && <div className="state-message">Loading tenant detail…</div>}

          {!detailLoading && tab === "iocs" && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Reputation</th>
                  <th>Actor</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {iocs.length === 0 ? (
                  <tr>
                    <td colSpan={5}>No IOCs yet — sync, ingest STIX, or pull TAXII.</td>
                  </tr>
                ) : (
                  iocs.map((ioc, idx) => (
                    <tr key={`${ioc.ioc_type}-${ioc.ioc_value}-${idx}`}>
                      <td>{ioc.ioc_type}</td>
                      <td className="cell-mono">{ioc.ioc_value}</td>
                      <td>{ioc.reputation_status ?? "—"}</td>
                      <td>{ioc.threat_actor ?? "—"}</td>
                      <td>{ioc.summary ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}

          {!detailLoading && tab === "campaigns" && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Campaign</th>
                  <th>Actor</th>
                  <th>Status</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.length === 0 ? (
                  <tr>
                    <td colSpan={4}>No campaigns yet.</td>
                  </tr>
                ) : (
                  campaigns.map((c, idx) => (
                    <tr key={`${c.name}-${idx}`}>
                      <td>{c.name}</td>
                      <td>{c.threat_actor ?? "—"}</td>
                      <td>{c.status ?? "—"}</td>
                      <td>{c.summary ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}

          {tab === "ingest" && (
            <div className="form-grid" style={{ display: "grid", gap: "1.25rem" }}>
              <div>
                <h3 className="section-title">STIX 2.1 bundle ingest</h3>
                <p className="page-subtitle">
                  Paste a STIX bundle JSON (type: bundle). IOCs are upserted into this tenant and
                  appear in the customer Threat Intel / ThreatLens views.
                </p>
                <textarea
                  className="form-input"
                  rows={10}
                  value={stixJson}
                  onChange={(e) => setStixJson(e.target.value)}
                  placeholder='{"type":"bundle","objects":[...]}'
                />
                <div className="confirm-actions" style={{ marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy || !stixJson.trim()}
                    onClick={handleStixIngest}
                  >
                    Ingest STIX bundle
                  </button>
                </div>
              </div>

              <div>
                <h3 className="section-title">TAXII 2.x collection pull</h3>
                <p className="page-subtitle">
                  Pull objects from a TAXII collection, then ingest as STIX. You can use a one-off
                  URL or the configured feed env vars (
                  <code>JUNEXIS_TAXII_API_ROOT</code> / <code>JUNEXIS_TAXII_COLLECTION_ID</code>).
                </p>
                <label className="form-label">
                  API root
                  <input
                    className="form-input"
                    value={taxiiRoot}
                    onChange={(e) => setTaxiiRoot(e.target.value)}
                    placeholder="https://taxii.example/taxii2/root/"
                  />
                </label>
                <label className="form-label">
                  Collection ID
                  <input
                    className="form-input"
                    value={taxiiCollection}
                    onChange={(e) => setTaxiiCollection(e.target.value)}
                    placeholder="collection-uuid"
                  />
                </label>
                <label className="form-label">
                  Username (optional)
                  <input
                    className="form-input"
                    value={taxiiUser}
                    onChange={(e) => setTaxiiUser(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label className="form-label">
                  Password (optional — never stored)
                  <input
                    className="form-input"
                    type="password"
                    value={taxiiPass}
                    onChange={(e) => setTaxiiPass(e.target.value)}
                    autoComplete="new-password"
                  />
                </label>
                <div className="confirm-actions" style={{ marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy || (!taxiiRoot.trim() && !taxiiCollection.trim())}
                    onClick={() => handleTaxiiPull(false)}
                  >
                    Pull TAXII (form values)
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy}
                    onClick={() => handleTaxiiPull(true)}
                  >
                    Pull configured feed (env)
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      ) : (
        <p className="muted" style={{ marginTop: "1rem" }}>
          Select a tenant to view IOCs/campaigns or run STIX / TAXII ingest.
        </p>
      )}
    </div>
  );
}
