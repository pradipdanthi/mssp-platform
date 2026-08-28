import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  ConsultationRequest,
  getCustomerIncidents,
  listConsultationRequests,
} from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import SeverityPill from "../components/SeverityPill";
import SocFilterBar, { SocFilterValues } from "../components/soc/SocFilterBar";
import { formatScopeSummary } from "../data/serviceCatalog";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

const STATUS_OPTIONS = [
  { value: "open", label: "Open (active)" },
  { value: "in_progress", label: "In progress" },
  { value: "waiting_customer", label: "Waiting customer" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const SEVERITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "urgent", label: "High + Critical" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

type TabKey = "security" | "service-requests";

export default function IncidentsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [params, setParams] = useSearchParams();
  const tab: TabKey = params.get("tab") === "service-requests" ? "service-requests" : "security";
  const statusFilter = params.get("status") ?? "";
  const severityFilter = params.get("severity") ?? "";
  const qFilter = params.get("q") ?? "";
  const sinceFilter = params.get("since") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;

  const [serviceRequests, setServiceRequests] = useState<ConsultationRequest[]>([]);
  const [srLoading, setSrLoading] = useState(false);
  const [srError, setSrError] = useState<string | null>(null);

  function patchParams(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  const filterValues: SocFilterValues = {
    q: qFilter,
    status: statusFilter,
    severity: severityFilter,
    category: "",
    rule_id: "",
    hostname: "",
    process: "",
    path: "",
    user: "",
    hash: "",
    cmdline: "",
    since: sinceFilter,
  };

  const { status, data, errorMessage } = useCustomerQuery(
    () =>
      getCustomerIncidents(shortCode as string, {
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
        ...(sinceFilter ? { since: sinceFilter } : {}),
      }),
    Boolean(shortCode) && tab === "security",
    [shortCode, statusFilter, severityFilter, qFilter, sinceFilter, page, pageSize, tab]
  );

  useEffect(() => {
    if (!shortCode || tab !== "service-requests") return;
    setSrLoading(true);
    listConsultationRequests(shortCode)
      .then((res) => {
        setServiceRequests(res.requests || []);
        setSrError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && typeof err.detail === "string") setSrError(err.detail);
        else setSrError("Could not load service requests.");
      })
      .finally(() => setSrLoading(false));
  }, [shortCode, tab]);

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Incidents</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so incident data cannot be loaded.
        </div>
      </div>
    );
  }

  const incidents = status === "success" && data ? data.incidents : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? incidents.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-subtitle">
        Security cases and service / upgrade consultation tickets for your organization.
      </p>

      <div className="subnav-tabs" role="tablist" aria-label="Incidents views">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "security"}
          className={"subnav-tab" + (tab === "security" ? " is-active" : "")}
          onClick={() => patchParams({ tab: null, page: "1" })}
        >
          Security Incidents
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "service-requests"}
          className={"subnav-tab" + (tab === "service-requests" ? " is-active" : "")}
          onClick={() => patchParams({ tab: "service-requests", page: null })}
        >
          Service Requests &amp; Upgrades
        </button>
      </div>

      {tab === "security" && (
        <>
          <SocFilterBar
            searchPlaceholder="Search number, title, host, or summary…"
            values={filterValues}
            onChange={(patch) => {
              const updates: Record<string, string | null> = {};
              for (const [k, v] of Object.entries(patch)) {
                updates[k] = v == null || v === "" ? null : String(v);
              }
              patchParams(updates);
            }}
            statusOptions={STATUS_OPTIONS}
            severityOptions={SEVERITY_OPTIONS}
            showAlertFacets={false}
            presetNamespace="customer.incidents"
            pageSize={pageSize}
            onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
            meta={meta}
            onPageChange={(p) => patchParams({ page: String(p) })}
          />

          {status === "loading" && <div className="state-message">Loading incidents...</div>}
          {status === "forbidden" && (
            <div className="state-message state-error">
              Access denied for this customer portal view.
            </div>
          )}
          {(status === "error" || status === "not_found") && (
            <div className="state-message state-error">{errorMessage}</div>
          )}

          {status === "success" && data && (
            incidents.length === 0 ? (
              <div className="state-message">
                No incidents{statusFilter ? ` matching “${statusFilter}”` : ""} in this view.
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Incident</th>
                    <th>Title</th>
                    <th>Asset</th>
                    <th>Device</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Summary</th>
                    <th>Opened</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((inc) => (
                    <tr key={inc.incident_number}>
                      <td className="cell-mono">
                        <Link to={`/incidents/${encodeURIComponent(inc.incident_number)}`}>
                          {inc.incident_number}
                        </Link>
                      </td>
                      <td>
                        <Link to={`/incidents/${encodeURIComponent(inc.incident_number)}`}>
                          {inc.title}
                        </Link>
                      </td>
                      <td className="cell-mono">{inc.hostname ?? "—"}</td>
                      <td>{inc.device_type ?? "—"}</td>
                      <td>
                        <SeverityPill value={inc.severity} />
                      </td>
                      <td>
                        <SeverityPill value={inc.status} kind="status" />
                      </td>
                      <td>{inc.customer_visible_summary ?? "—"}</td>
                      <td className="cell-mono">{inc.opened_at ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </>
      )}

      {tab === "service-requests" && (
        <>
          <p className="page-subtitle">
            Consultation and upgrade requests from the{" "}
            <Link to="/services">Service Portfolio</Link>. Status updates come from your MSSP team.
          </p>
          {srLoading && <div className="state-message">Loading service requests…</div>}
          {srError && <div className="state-message state-error">{srError}</div>}
          {!srLoading && !srError && serviceRequests.length === 0 && (
            <div className="state-message">
              No service requests yet. Open the{" "}
              <Link to="/services">Service Portfolio</Link> and use{" "}
              <strong>Request for Consulting</strong> on an available service.
            </div>
          )}
          {!srLoading && !srError && serviceRequests.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Request ID</th>
                  <th>Service Name</th>
                  <th>Target Scope</th>
                  <th>Status</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {serviceRequests.map((r) => (
                  <tr key={r.id}>
                    <td className="cell-mono" title={r.id}>
                      {r.id.slice(0, 8)}…
                    </td>
                    <td>{r.service_name}</td>
                    <td>{formatScopeSummary(r)}</td>
                    <td>
                      <span className={"pill-status pill-status--" + r.status.toLowerCase()}>
                        {r.status}
                      </span>
                    </td>
                    <td className="cell-mono">{r.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
