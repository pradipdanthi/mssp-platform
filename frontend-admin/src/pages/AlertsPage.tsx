import { Link, useSearchParams } from "react-router-dom";
import { getAlertTaxonomySummary, getAlerts } from "../api/admin";
import AlertTaxonomyNav from "../components/AlertTaxonomyNav";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import ListToolbar from "../components/ListToolbar";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { niktiairSourceLabel } from "../config/niktiairBrands";
import { useCustomerScope } from "../hooks/useCustomerScope";
import { useEffect, useState } from "react";

type ColumnMode = "default" | "endpoints" | "network" | "vuln" | "data";

function columnModeForCategory(category: string | null): ColumnMode {
  if (!category || category === "all" || category === "uncategorized") return "default";
  if (category.startsWith("endpoints")) return "endpoints";
  if (
    category === "network_ids_sensors" ||
    category === "network_hardware" ||
    category === "security_edge_appliances"
  ) {
    return "network";
  }
  if (category.startsWith("vuln_")) return "vuln";
  if (category === "databases_storage" || category === "identity_access" || category === "iot_ot") {
    return "data";
  }
  return "default";
}

const SEVERITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "urgent", label: "High + Critical" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "triaged", label: "Triaged" },
  { value: "incident_created", label: "Incident created" },
  { value: "false_positive", label: "False positive" },
  { value: "closed", label: "Closed" },
];

function buildAlertsBase(severityFilter: string, statusFilter: string, category?: string | null): string {
  const params = new URLSearchParams();
  if (category && category !== "all") params.set("category", category);
  if (severityFilter) params.set("severity", severityFilter);
  if (statusFilter) params.set("status", statusFilter);
  const q = params.toString();
  return q ? `/alerts?${q}` : "/alerts";
}

export default function AlertsPage() {
  const { tenantId: scopedTenantId, scopeAll, tenantName } = useCustomerScope();
  const [params, setParams] = useSearchParams();
  const severityFilter = params.get("severity") ?? "";
  const statusFilter = params.get("status") ?? "";
  const categoryFilter = params.get("category");
  const qFilter = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;
  const columnMode = columnModeForCategory(categoryFilter);
  const alertsBase = buildAlertsBase(severityFilter, statusFilter, categoryFilter);

  function patchParams(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  const listFilters = {
    page,
    page_size: pageSize,
    ...(scopedTenantId ? { tenant_id: scopedTenantId } : {}),
    ...(qFilter ? { q: qFilter } : {}),
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(severityFilter ? { severity: severityFilter } : {}),
    ...(categoryFilter ? { asset_category: categoryFilter } : {}),
  };

  const { status, data, errorMessage } = useAdminQuery(
    () => getAlerts(listFilters),
    [scopedTenantId, severityFilter, statusFilter, categoryFilter, qFilter, page, pageSize]
  );

  const [taxonomyCounts, setTaxonomyCounts] = useState<Record<string, number>>({ all: 0 });

  useEffect(() => {
    if (!scopedTenantId) {
      setTaxonomyCounts({ all: 0 });
      return;
    }
    getAlertTaxonomySummary({
      tenant_id: scopedTenantId,
      ...(statusFilter ? { status: statusFilter } : {}),
      ...(severityFilter ? { severity: severityFilter } : {}),
    })
      .then((res) => setTaxonomyCounts(res.counts))
      .catch(() => undefined);
  }, [scopedTenantId, severityFilter, statusFilter, data]);

  const alerts = status === "success" && data ? data.alerts : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? alerts.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  const filterLabel =
    severityFilter === "urgent"
      ? "High + Critical"
      : severityFilter
        ? severityFilter
        : null;

  const categoryLabel = categoryFilter ? categoryFilter.replace(/_/g, " ") : null;

  return (
    <div className="alerts-page-layout">
      {scopedTenantId ? (
        <AlertTaxonomyNav
          counts={taxonomyCounts}
          activeCategory={categoryFilter}
          severityFilter={severityFilter || null}
          statusFilter={statusFilter || null}
          tenantName={tenantName || "Customer"}
        />
      ) : null}

      <div className="alerts-page-main">
        <h1 className="page-title">
          Alerts
          {meta ? (
            <span className="page-title-count"> · {meta.total.toLocaleString()}</span>
          ) : null}
        </h1>
        <CustomerScopeBanner />
        <p className="page-subtitle">
          {scopeAll ? (
            <>
              All customers — set <strong>Customer scope</strong> in the header to focus on one
              customer and open device taxonomy.
              {meta ? (
                <>
                  {" "}
                  Showing {meta.total === 0 ? 0 : (meta.page - 1) * meta.page_size + 1}–
                  {Math.min(meta.page * meta.page_size, meta.total)} of {meta.total}.
                </>
              ) : null}
            </>
          ) : (
            <>
              <strong>{tenantName || "Customer"}</strong>
              {meta ? <> · {meta.total.toLocaleString()} matching this view</> : null}
              {categoryLabel ? (
                <>
                  {" · "}
                  Category: <strong>{categoryLabel}</strong>
                  {" · "}
                  <Link to={buildAlertsBase(severityFilter, statusFilter)}>Clear category</Link>
                </>
              ) : null}
              {filterLabel ? (
                <>
                  {" · "}
                  Severity: <strong style={{ textTransform: "capitalize" }}>{filterLabel}</strong>
                </>
              ) : null}
            </>
          )}
        </p>

        <ListToolbar
          searchPlaceholder="Search title, host, summary…"
          searchValue={qFilter}
          onSearchChange={(q) => patchParams({ q, page: "1" })}
          statusOptions={STATUS_OPTIONS}
          statusValue={statusFilter}
          onStatusChange={(status) => patchParams({ status, page: "1" })}
          severityOptions={SEVERITY_OPTIONS}
          severityValue={severityFilter}
          onSeverityChange={(severity) => patchParams({ severity, page: "1" })}
          pageSize={pageSize}
          onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
          meta={meta}
          onPageChange={(p) => patchParams({ page: String(p) })}
        />

        {status === "loading" && <div className="state-message">Loading alerts...</div>}
        {status === "forbidden" && (
          <div className="state-message state-error">
            Access denied. Your account does not have permission to view alerts.
          </div>
        )}
        {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

        {status === "success" && data && (
          alerts.length === 0 ? (
            <div className="state-message">
              No alerts{filterLabel ? ` matching “${filterLabel}”` : ""} in this view.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  {scopeAll ? <th>Customer</th> : null}
                  {columnMode === "endpoints" ? (
                    <>
                      <th>Hostname</th>
                      <th>User</th>
                      <th>Rule / title</th>
                      <th>Device</th>
                    </>
                  ) : columnMode === "network" ? (
                    <>
                      <th>Title</th>
                      <th>Source</th>
                      <th>Destination</th>
                      <th>Protocol</th>
                      <th>Action</th>
                    </>
                  ) : columnMode === "vuln" ? (
                    <>
                      <th>Title</th>
                      <th>CVE</th>
                      <th>Target</th>
                      <th>Remediation hint</th>
                    </>
                  ) : columnMode === "data" ? (
                    <>
                      <th>Resource</th>
                      <th>Event</th>
                      <th>User / role</th>
                      <th>Severity</th>
                    </>
                  ) : (
                    <>
                      <th>Title</th>
                      <th>Category</th>
                      <th>Source</th>
                    </>
                  )}
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((alert) => {
                  const ctx = alert.contextual || {};
                  return (
                    <tr key={alert.id}>
                      <td>
                        <SeverityPill value={alert.severity} filterBase={alertsBase} />
                      </td>
                      {scopeAll ? (
                        <td>
                          {alert.tenant_name || "—"}
                          {alert.short_code ? (
                            <span className="alert-customer-code"> {alert.short_code}</span>
                          ) : null}
                        </td>
                      ) : null}
                      {columnMode === "endpoints" ? (
                        <>
                          <td className="cell-mono">{String(ctx.hostname ?? "—")}</td>
                          <td>{String(ctx.user ?? "—")}</td>
                          <td>
                            <Link to={`/alerts/${alert.id}`}>{alert.alert_title}</Link>
                          </td>
                          <td>{alert.device_type ?? "—"}</td>
                        </>
                      ) : columnMode === "network" ? (
                        <>
                          <td>
                            <Link to={`/alerts/${alert.id}`}>{alert.alert_title}</Link>
                          </td>
                          <td className="cell-mono">
                            {String(ctx.source_endpoint ?? alert.source_ip ?? "—")}
                          </td>
                          <td className="cell-mono">{String(ctx.dest_endpoint ?? "—")}</td>
                          <td>{String(ctx.protocol ?? "—")}</td>
                          <td>{String(ctx.action ?? "—")}</td>
                        </>
                      ) : columnMode === "vuln" ? (
                        <>
                          <td>
                            <Link to={`/alerts/${alert.id}`}>{alert.alert_title}</Link>
                          </td>
                          <td className="cell-mono">{String(ctx.cve_id ?? "—")}</td>
                          <td>{String(ctx.target ?? "—")}</td>
                          <td>{String(ctx.remediation_hint ?? "—").slice(0, 80)}</td>
                        </>
                      ) : columnMode === "data" ? (
                        <>
                          <td>{String(ctx.resource_name ?? alert.destination_host ?? "—")}</td>
                          <td>
                            <Link to={`/alerts/${alert.id}`}>{alert.alert_title}</Link>
                          </td>
                          <td>{String(ctx.user_or_role ?? alert.source_user ?? "—")}</td>
                          <td>{alert.severity}</td>
                        </>
                      ) : (
                        <>
                          <td>
                            <Link to={`/alerts/${alert.id}`}>{alert.alert_title}</Link>
                          </td>
                          <td>{alert.asset_category_label ?? alert.asset_category ?? "—"}</td>
                          <td>{niktiairSourceLabel(alert.source_tool)}</td>
                        </>
                      )}
                      <td>
                        <SeverityPill
                          value={alert.status}
                          kind="status"
                          filterBase={alertsBase}
                        />
                      </td>
                      <td className="cell-mono">{alert.created_at}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  );
}
