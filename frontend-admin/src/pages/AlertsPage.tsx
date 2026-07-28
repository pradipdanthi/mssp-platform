import { Link, useSearchParams } from "react-router-dom";
import { getAlertTaxonomySummary, getAlerts } from "../api/admin";
import AlertTaxonomyNav from "../components/AlertTaxonomyNav";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useEffect, useState } from "react";

function matchesSeverityFilter(severity: string, filter: string | null): boolean {
  if (!filter) return true;
  const s = severity.toLowerCase();
  const f = filter.toLowerCase();
  if (f === "urgent" || f === "high_critical" || f === "high,critical") {
    return s === "high" || s === "critical";
  }
  return s === f;
}

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

export default function AlertsPage() {
  const [params] = useSearchParams();
  const severityFilter = params.get("severity");
  const categoryFilter = params.get("category");
  const columnMode = columnModeForCategory(categoryFilter);

  const listFilters = {
    ...(severityFilter &&
    !["urgent", "high_critical", "high,critical"].includes(severityFilter)
      ? { severity: severityFilter }
      : {}),
    ...(categoryFilter ? { asset_category: categoryFilter } : {}),
  };

  const { status, data, errorMessage } = useAdminQuery(
    () => getAlerts(Object.keys(listFilters).length ? listFilters : undefined),
    [severityFilter, categoryFilter]
  );

  const [taxonomyCounts, setTaxonomyCounts] = useState<Record<string, number>>({ all: 0 });

  useEffect(() => {
    getAlertTaxonomySummary(
      severityFilter &&
        !["urgent", "high_critical", "high,critical"].includes(severityFilter)
        ? { severity: severityFilter }
        : undefined
    )
      .then((res) => setTaxonomyCounts(res.counts))
      .catch(() => undefined);
  }, [severityFilter, data]);

  const alerts =
    status === "success" && data
      ? data.alerts.filter((a) => matchesSeverityFilter(a.severity, severityFilter))
      : [];

  const filterLabel =
    severityFilter === "urgent"
      ? "High + Critical"
      : severityFilter
        ? severityFilter
        : null;

  return (
    <div className="alerts-page-layout">
      <AlertTaxonomyNav
        counts={taxonomyCounts}
        activeCategory={categoryFilter}
        severityFilter={severityFilter}
      />
      <div className="alerts-page-main">
        <h1 className="page-title">Alerts</h1>
        <p className="page-subtitle">
          All-device SOC alert stream with derived taxonomy (latest 100 in view).
          {categoryFilter ? (
            <>
              {" "}
              Category: <strong>{categoryFilter.replace(/_/g, " ")}</strong>
              {" · "}
              <Link to="/alerts">Clear category</Link>
            </>
          ) : null}
          {filterLabel ? (
            <>
              {" "}
              Severity: <strong style={{ textTransform: "capitalize" }}>{filterLabel}</strong>
              {" · "}
              <Link to={categoryFilter ? `/alerts?category=${categoryFilter}` : "/alerts"}>
                Clear severity
              </Link>
            </>
          ) : null}
        </p>

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
              No alerts{filterLabel ? ` matching “${filterLabel}”` : ""} in this category yet.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th>Severity</th>
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
                      <td>{alert.tenant_name}</td>
                      <td>
                        <SeverityPill value={alert.severity} filterBase="/alerts" />
                      </td>
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
                          <td className="cell-mono">{String(ctx.source_endpoint ?? alert.source_ip ?? "—")}</td>
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
                          <td className="cell-mono">{alert.source_tool ?? "—"}</td>
                        </>
                      )}
                      <td>
                        <SeverityPill value={alert.status} kind="status" filterBase="/alerts" />
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
