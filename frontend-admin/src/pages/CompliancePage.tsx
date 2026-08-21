import { useEffect, useMemo, useState } from "react";
import {
  AdminComplianceTenantRow,
  getAdminComplianceSummary,
  syncAdminCompliance,
} from "../api/admin";
import { ApiError } from "../api/client";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import { useAuth } from "../auth/AuthContext";
import { useCustomerScope } from "../hooks/useCustomerScope";

const FRAMEWORK_TABS: { id: string | null; label: string }[] = [
  { id: null, label: "All frameworks" },
  { id: "CIS", label: "CIS Benchmarks" },
  { id: "ISO_27001", label: "ISO 27001" },
  { id: "PCI_DSS", label: "PCI-DSS" },
  { id: "NIST", label: "NIST CSF" },
  { id: "HIPAA", label: "HIPAA" },
];

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string" && err.detail.trim()) {
    return err.detail;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

function scoreFor(row: AdminComplianceTenantRow, framework: string | null): number {
  if (!framework) return Math.round(Number(row.overall_score_percentage || 0));
  const block = row.framework_scores?.[framework] || {};
  return Math.round(Number(block.score_percentage || 0));
}

/**
 * Continuous Compliance — SOC view of tenant hardening scorecards.
 * HIPAA tab is an indicator mapped to §164.312 technical safeguards, not a certification.
 */
export default function CompliancePage() {
  const { user } = useAuth();
  const canSync = user?.role === "platform_admin" || user?.role === "soc_manager" || user?.role === "soc_analyst";
  const { scopeAll, tenantShortCode } = useCustomerScope();
  const [rows, setRows] = useState<AdminComplianceTenantRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [framework, setFramework] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const data = await getAdminComplianceSummary();
      setRows(data.tenants || []);
    } catch (err) {
      setError(apiErrorMessage(err, "Unable to load compliance summaries."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const visible = useMemo(() => {
    if (scopeAll || !tenantShortCode) return rows;
    return rows.filter((r) => r.short_code === tenantShortCode);
  }, [rows, scopeAll, tenantShortCode]);

  async function onSync(shortCode: string) {
    setSyncing(shortCode);
    setError(null);
    try {
      await syncAdminCompliance(shortCode);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err, "Compliance sync failed."));
    } finally {
      setSyncing(null);
    }
  }

  return (
    <div className="page compliance-page">
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Continuous Compliance</h1>
          <p className="muted-text">
            Configuration-control readiness by tenant. Scores are indicative hardening indicators,
            not certifications.
          </p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void load()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      <CustomerScopeBanner />
      {error && <p className="form-error">{error}</p>}

      {framework === "HIPAA" && (
        <section className="panel-surface" style={{ padding: 16, marginBottom: 16 }}>
          <h2 className="page-title" style={{ fontSize: "1.1rem" }}>
            HIPAA §164.312 Technical Safeguards Indicator
          </h2>
          <p className="muted-text">
            Maps configuration checks tagged HIPAA or Security Rule sections 164.312 / 164.308 to a
            technical-safeguards readiness indicator. This is not a HIPAA certification or legal
            opinion.
          </p>
        </section>
      )}

      <div className="compliance-fw-grid">
        {FRAMEWORK_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            className={"compliance-fw-card" + (framework === tab.id ? " active" : "")}
            onClick={() => setFramework(tab.id)}
          >
            <span className="compliance-fw-name">{tab.label}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <p className="muted-text">Loading tenant scorecards…</p>
      ) : visible.length === 0 ? (
        <p className="muted-text">No compliance summaries for the current customer scope.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>{framework === "HIPAA" ? "HIPAA indicator" : framework || "Overall"}</th>
                <th>Passed</th>
                <th>Failed</th>
                <th>Endpoints</th>
                <th>Sync</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const pct = scoreFor(row, framework);
                const fw = framework ? row.framework_scores?.[framework] : undefined;
                return (
                  <tr key={row.short_code}>
                    <td>
                      {row.tenant_name} ({row.short_code})
                    </td>
                    <td>{pct}%</td>
                    <td>{framework ? fw?.passed_checks ?? 0 : row.passed_checks}</td>
                    <td>{framework ? fw?.failed_checks ?? 0 : row.failed_checks}</td>
                    <td>{row.agent_count}</td>
                    <td>{row.sync_status || "never"}</td>
                    <td>
                      {canSync && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          disabled={syncing === row.short_code}
                          onClick={() => void onSync(row.short_code)}
                        >
                          {syncing === row.short_code ? "Syncing…" : "Sync"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
