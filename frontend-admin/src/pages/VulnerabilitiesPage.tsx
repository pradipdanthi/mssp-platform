import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AdminVulnerability,
  ServiceUpgradeRequestRow,
  approveServiceUpgradeRequest,
  declineServiceUpgradeRequest,
  getServiceUpgradeRequests,
  getTenantAssetServiceCoverage,
  getVulnerabilities,
  getVulnerabilityDetail,
  patchServiceUpgradeRequest,
  promoteVulnerabilityRecommendation,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import { useAdminQuery } from "../hooks/useAdminQuery";

const STATUS_OPTIONS = [
  { value: "open", label: "Open" },
  { value: "fixed", label: "Fixed" },
  { value: "accepted_risk", label: "Accepted risk" },
  { value: "false_positive", label: "False positive" },
];
const SOURCE_OPTIONS = [
  { value: "nuclei", label: "Nuclei" },
  { value: "vuls", label: "Vuls" },
  { value: "greenbone", label: "Greenbone" },
];

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) {
      return "Access denied. platform_admin or soc_manager can promote findings.";
    }
  }
  return fallback;
}

export default function VulnerabilitiesPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin" || user?.role === "soc_manager";
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status") ?? "";
  const sourceFilter = params.get("source") ?? "";
  const qFilter = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;

  function patchParams(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  const { status, data, errorMessage, refetch } = useAdminQuery(
    () =>
      getVulnerabilities({
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(sourceFilter ? { source_platform: sourceFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    [statusFilter, sourceFilter, qFilter, page, pageSize]
  );
  const rows = data?.vulnerabilities ?? [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? rows.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  const [selected, setSelected] = useState<AdminVulnerability | null>(null);
  const [detailNotes, setDetailNotes] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [makeVisible, setMakeVisible] = useState(false);
  const [upgradeRequests, setUpgradeRequests] = useState<ServiceUpgradeRequestRow[]>([]);
  const [upgradeError, setUpgradeError] = useState<string | null>(null);
  const [selectedUpgrade, setSelectedUpgrade] = useState<ServiceUpgradeRequestRow | null>(null);
  const [upgradeActionBusy, setUpgradeActionBusy] = useState(false);
  const [upgradeNextSteps, setUpgradeNextSteps] = useState<string[] | null>(null);
  const [approveAssetIds, setApproveAssetIds] = useState<string[]>([]);
  const [approveAssets, setApproveAssets] = useState<
    Array<{ id: string; hostname: string | null; asset_type: string; os_name: string | null; covered?: boolean }>
  >([]);
  const [approveLoading, setApproveLoading] = useState(false);

  function loadUpgradeRequests() {
    getServiceUpgradeRequests()
      .then((res) => setUpgradeRequests(res.requests || []))
      .catch((err) => setUpgradeError(apiErrorMessage(err, "Could not load upgrade requests.")));
  }

  useEffect(() => {
    loadUpgradeRequests();
  }, []);

  async function handleMarkReviewing(row: ServiceUpgradeRequestRow) {
    if (!canWrite) return;
    setUpgradeActionBusy(true);
    setUpgradeError(null);
    setUpgradeNextSteps(null);
    try {
      const updated = await patchServiceUpgradeRequest(row.id, { status: "reviewing" });
      setSelectedUpgrade(updated);
      loadUpgradeRequests();
    } catch (err) {
      setUpgradeError(apiErrorMessage(err, "Could not update request."));
    } finally {
      setUpgradeActionBusy(false);
    }
  }

  async function prepareApprove(row: ServiceUpgradeRequestRow) {
    setSelectedUpgrade(row);
    setUpgradeNextSteps(null);
    setUpgradeError(null);
    setApproveLoading(true);
    const requested = (row.requested_asset_ids || []).map(String);
    setApproveAssetIds(requested);
    try {
      const cov = await getTenantAssetServiceCoverage(row.tenant_id, "vulnerability_management");
      setApproveAssets(cov.assets || []);
      if (requested.length === 0 && cov.assets?.length) {
        // No customer pick — leave empty so admin must choose.
        setApproveAssetIds([]);
      }
    } catch (err) {
      setApproveAssets((row.requested_assets || []).map((a) => ({ ...a, covered: false })));
      setUpgradeError(apiErrorMessage(err, "Could not load customer assets for coverage."));
    } finally {
      setApproveLoading(false);
    }
  }

  async function handleApproveEnable(row: ServiceUpgradeRequestRow) {
    if (!canWrite) return;
    if (row.service_key === "vulnerability_management" && approveAssetIds.length === 0) {
      setUpgradeError("Select at least one asset to cover before approving Vulnerability Management.");
      return;
    }
    const ok = window.confirm(
      row.service_key === "vulnerability_management"
        ? `Enable Vulnerability Management for ${row.tenant_name} on ${approveAssetIds.length} selected asset(s) (${row.preferred_cadence} cadence)?`
        : `Enable ${row.service_key.replace(/_/g, " ")} for ${row.tenant_name}?`
    );
    if (!ok) return;
    setUpgradeActionBusy(true);
    setUpgradeError(null);
    setSuccessMessage(null);
    setUpgradeNextSteps(null);
    try {
      const result = await approveServiceUpgradeRequest(
        row.id,
        row.service_key === "vulnerability_management" ? { asset_ids: approveAssetIds } : undefined
      );
      setSuccessMessage(result.message);
      setUpgradeNextSteps(result.next_steps || []);
      setSelectedUpgrade(result.request);
      loadUpgradeRequests();
    } catch (err) {
      setUpgradeError(apiErrorMessage(err, "Could not approve request."));
    } finally {
      setUpgradeActionBusy(false);
    }
  }

  async function handleDecline(row: ServiceUpgradeRequestRow) {
    if (!canWrite) return;
    const ok = window.confirm(`Decline this upgrade request for ${row.tenant_name}?`);
    if (!ok) return;
    setUpgradeActionBusy(true);
    setUpgradeError(null);
    try {
      await declineServiceUpgradeRequest(row.id);
      setSelectedUpgrade(null);
      setUpgradeNextSteps(null);
      loadUpgradeRequests();
    } catch (err) {
      setUpgradeError(apiErrorMessage(err, "Could not decline request."));
    } finally {
      setUpgradeActionBusy(false);
    }
  }

  function formatScopeList(values: string[]): string {
    const labels: Record<string, string> = {
      external_perimeter: "External perimeter",
      internal_network: "Internal network",
      authenticated_hosts: "Authenticated hosts",
      cloud_workloads: "Cloud workloads",
      web_applications: "Web applications",
    };
    return values.map((v) => labels[v] || v.replace(/_/g, " ")).join(", ");
  }

  async function openDetail(row: AdminVulnerability) {
    setActionError(null);
    setSuccessMessage(null);
    setSelected(row);
    setDetailNotes(null);
    try {
      const detail = await getVulnerabilityDetail(row.id);
      setSelected(detail);
      const bits = [
        detail.customer_safe_summary,
        detail.remediation_summary,
        detail.internal_notes ? `Internal notes: ${detail.internal_notes}` : null,
        detail.nvt_oid ? `NVT OID: ${detail.nvt_oid}` : null,
      ].filter(Boolean);
      setDetailNotes(bits.join("\n\n") || "No extra detail.");
    } catch (err) {
      setActionError(apiErrorMessage(err, "Could not load vulnerability detail."));
    }
  }

  async function handlePromote() {
    if (!selected || !canWrite) return;
    setPromoting(true);
    setActionError(null);
    setSuccessMessage(null);
    try {
      const result = await promoteVulnerabilityRecommendation(selected.id, {
        customer_visible: makeVisible,
      });
      setSuccessMessage(
        result.created
          ? `Recommendation created (${result.recommendation_id}). Customer visible: ${
              result.customer_visible ? "yes" : "no"
            }.`
          : `Already linked to recommendation ${result.recommendation_id}.`
      );
      await refetch();
      const refreshed = await getVulnerabilityDetail(selected.id);
      setSelected(refreshed);
    } catch (err) {
      setActionError(apiErrorMessage(err, "Promote failed."));
    } finally {
      setPromoting(false);
    }
  }

  const openUpgrades = upgradeRequests.filter((r) =>
    ["submitted", "reviewing", "quoted"].includes(r.status)
  );

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Vulnerabilities</h1>
          <p className="page-subtitle">
            Findings from Nuclei, Vuls, and optional Greenbone — normalized in the control plane.
            Customers never see raw scan output. Promote items to recommendations when ready.
            Customer upgrade requests appear below.
          </p>
        </div>
        <div className="page-header-actions" style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => {
              refetch();
              loadUpgradeRequests();
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      <ListToolbar
        searchPlaceholder="Search title, CVE, asset, tenant…"
        searchValue={qFilter}
        onSearchChange={(q) => patchParams({ q, page: "1" })}
        statusOptions={STATUS_OPTIONS}
        statusValue={statusFilter}
        onStatusChange={(status) => patchParams({ status, page: "1" })}
        severityOptions={SOURCE_OPTIONS}
        severityValue={sourceFilter}
        onSeverityChange={(source) => patchParams({ source, page: "1" })}
        severityLabel="Source"
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      <div className="management-panel" style={{ marginBottom: "1.25rem" }}>
        <h2 className="section-title" style={{ marginTop: 0 }}>
          Customer upgrade requests
        </h2>
        <p className="page-subtitle" style={{ marginTop: 0 }}>
          Submitted from the customer portal when optional services are not yet entitled. For
          Vulnerability Management, approve with a <strong>selected asset list</strong> — scanning
          covers only those hosts, not the whole estate.
          <br />
          If the customer signed offline and emailed a server list instead of using the portal,
          skip this queue: open <strong>Customers → Change Subscription / enable services</strong>,
          tick Vulnerability Management, paste/select those hosts, and Save.
        </p>
        {!canWrite && (
          <p className="muted">You have read-only access. platform_admin or soc_manager can approve requests.</p>
        )}
        {upgradeError && <p className="form-error">{upgradeError}</p>}
        {openUpgrades.length === 0 ? (
          <p className="muted">No open customer upgrade requests.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Service</th>
                  <th>Urgency</th>
                  <th>Cadence</th>
                  <th>Assets</th>
                  <th>Status</th>
                  <th>Requested</th>
                  <th>Summary</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {openUpgrades.map((r) => (
                  <tr
                    key={r.id}
                    className={selectedUpgrade?.id === r.id ? "row-selected" : undefined}
                  >
                    <td>
                      {r.tenant_name} ({r.short_code})
                      {r.requested_by_name ? (
                        <div className="muted-text">{r.requested_by_name}</div>
                      ) : null}
                    </td>
                    <td>{r.service_key.replace(/_/g, " ")}</td>
                    <td>{r.urgency.replace(/_/g, " ")}</td>
                    <td>{r.preferred_cadence}</td>
                    <td>{r.approximate_assets ?? "—"}</td>
                    <td>
                      <span className="badge">{r.status}</span>
                    </td>
                    <td>{new Date(r.created_at).toLocaleString()}</td>
                    <td style={{ maxWidth: 280 }}>{r.requirements_summary}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {canWrite ? (
                        <>
                          <button
                            className="btn btn-ghost"
                            type="button"
                            disabled={upgradeActionBusy}
                            onClick={() => {
                              void prepareApprove(r);
                            }}
                          >
                            Details
                          </button>
                          {r.status === "submitted" ? (
                            <button
                              className="btn btn-ghost"
                              type="button"
                              disabled={upgradeActionBusy}
                              onClick={() => handleMarkReviewing(r)}
                            >
                              Reviewing
                            </button>
                          ) : null}
                          <button
                            className="btn btn-primary"
                            type="button"
                            disabled={upgradeActionBusy}
                            onClick={() => {
                              void prepareApprove(r).then(() => undefined);
                              setSelectedUpgrade(r);
                            }}
                          >
                            Review coverage
                          </button>
                          <button
                            className="btn btn-ghost"
                            type="button"
                            disabled={upgradeActionBusy}
                            onClick={() => handleDecline(r)}
                          >
                            Decline
                          </button>
                        </>
                      ) : (
                        <span className="muted-text" title="Your account role cannot approve requests">
                          SOC manager or platform admin
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {selectedUpgrade && (
          <div className="panel" style={{ marginTop: "1rem" }}>
            <h3 className="section-title" style={{ marginTop: 0 }}>
              Request detail — {selectedUpgrade.tenant_name} ({selectedUpgrade.short_code})
            </h3>
            <p className="muted">
              {selectedUpgrade.service_key.replace(/_/g, " ")} · {selectedUpgrade.status} · cadence{" "}
              {selectedUpgrade.preferred_cadence} · urgency{" "}
              {selectedUpgrade.urgency.replace(/_/g, " ")}
            </p>
            <p>
              <strong>Scope:</strong> {formatScopeList(selectedUpgrade.scan_scope)}
            </p>
            <p>
              <strong>Environments:</strong>{" "}
              {selectedUpgrade.environments.map((e) => e.replace(/_/g, " ")).join(", ")}
            </p>
            {selectedUpgrade.compliance_drivers.length > 0 ? (
              <p>
                <strong>Compliance:</strong>{" "}
                {selectedUpgrade.compliance_drivers.map((c) => c.replace(/_/g, " ")).join(", ")}
              </p>
            ) : null}
            <p className="upgrade-request-quote">{selectedUpgrade.requirements_summary}</p>

            {selectedUpgrade.service_key === "vulnerability_management" ? (
              <div className="asset-picker" style={{ marginTop: "0.75rem" }}>
                <h4 className="section-title">
                  Assets to cover ({approveAssetIds.length} selected)
                </h4>
                <p className="page-subtitle" style={{ marginTop: 0 }}>
                  Customer requested specific devices. Adjust the selection before approving — only
                  checked hosts will receive Vulnerability Management scans.
                </p>
                {approveLoading ? (
                  <p className="muted">Loading assets…</p>
                ) : approveAssets.length === 0 ? (
                  <p className="muted">
                    No protected assets for this customer yet. Add them under{" "}
                    <Link to="/assets">Assets</Link> first.
                  </p>
                ) : (
                  <div className="asset-picker-list">
                    {approveAssets.map((a) => (
                      <label key={a.id} className="upgrade-check asset-picker-row">
                        <input
                          type="checkbox"
                          checked={approveAssetIds.includes(a.id)}
                          onChange={() =>
                            setApproveAssetIds((prev) =>
                              prev.includes(a.id)
                                ? prev.filter((x) => x !== a.id)
                                : [...prev, a.id]
                            )
                          }
                        />
                        <span>
                          <strong>{a.hostname ?? a.id}</strong>
                          <span className="muted-text">
                            {" "}
                            · {a.asset_type}
                            {a.os_name ? ` · ${a.os_name}` : ""}
                            {(selectedUpgrade.requested_asset_ids || []).includes(a.id)
                              ? " · customer-requested"
                              : ""}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            ) : null}

            {upgradeNextSteps && upgradeNextSteps.length > 0 ? (
              <div className="state-message state-success">
                <p>
                  <strong>Next steps for your team:</strong>
                </p>
                <ul>
                  {upgradeNextSteps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="confirm-actions" style={{ marginTop: "0.75rem" }}>
              {canWrite && selectedUpgrade.status !== "accepted" ? (
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={upgradeActionBusy || approveLoading}
                  onClick={() => void handleApproveEnable(selectedUpgrade)}
                >
                  Approve &amp; enable
                </button>
              ) : null}
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => {
                  setSelectedUpgrade(null);
                  setUpgradeNextSteps(null);
                  setApproveAssets([]);
                  setApproveAssetIds([]);
                }}
              >
                Close detail
              </button>
            </div>
          </div>
        )}
      </div>

      {status === "loading" && <p className="muted">Loading vulnerabilities…</p>}
      {status === "error" && <p className="form-error">{errorMessage}</p>}
      {successMessage && <p className="form-success">{successMessage}</p>}
      {actionError && <p className="form-error">{actionError}</p>}

        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          Scans run <strong>automatically</strong> on VM 109 for customers with Vulnerability
          Management entitled and active <strong>protected assets</strong> (IP or hostname). SOC
          can queue an on-demand scan from the customer record when needed — no shell scripts.
        </p>
      {status === "success" && rows.length === 0 && (
        <p className="muted">
          No vulnerability findings yet. Run Nuclei/Vuls sync from VM 109 or ingest via Greenbone
          when ready.
        </p>
      )}

      {status === "success" && rows.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Severity</th>
                <th>Title</th>
                <th>CVE</th>
                <th>Customer</th>
                <th>Asset</th>
                <th>Status</th>
                <th>Recommendation</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.source_platform}</td>
                  <td>
                    <span className={`badge severity-${row.severity}`}>{row.severity}</span>
                  </td>
                  <td>{row.title}</td>
                  <td>{row.cve_id || "—"}</td>
                  <td>
                    {row.tenant_name} ({row.short_code})
                  </td>
                  <td>{row.asset_hostname || "—"}</td>
                  <td>{row.status}</td>
                  <td>{row.recommendation_id ? "Linked" : "—"}</td>
                  <td>
                    <button className="btn btn-ghost" type="button" onClick={() => openDetail(row)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="panel" style={{ marginTop: "1.5rem" }}>
          <h2>{selected.title}</h2>
          <p className="muted">
            {selected.severity.toUpperCase()}
            {selected.cve_id ? ` · ${selected.cve_id}` : ""} · {selected.short_code} ·{" "}
            {selected.source_platform}
          </p>
          <pre className="code-block" style={{ whiteSpace: "pre-wrap" }}>
            {detailNotes || "Loading…"}
          </pre>
          {canWrite && !selected.recommendation_id && (
            <div className="form-row" style={{ marginTop: "1rem" }}>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={makeVisible}
                  onChange={(e) => setMakeVisible(e.target.checked)}
                />
                Make recommendation customer-visible immediately
              </label>
              <button
                className="btn btn-primary"
                type="button"
                disabled={promoting}
                onClick={handlePromote}
              >
                {promoting ? "Creating…" : "Promote to recommendation"}
              </button>
            </div>
          )}
          {selected.recommendation_id && (
            <p className="muted">
              Linked recommendation ID: <code>{selected.recommendation_id}</code>
            </p>
          )}
          <button className="btn btn-ghost" type="button" onClick={() => setSelected(null)}>
            Close
          </button>
        </div>
      )}
    </div>
  );
}
