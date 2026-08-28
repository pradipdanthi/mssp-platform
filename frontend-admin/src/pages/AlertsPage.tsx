import { Link, useSearchParams } from "react-router-dom";
import {
  Alert,
  bulkUpdateAlerts,
  getAlertRuleFacets,
  getAlertTaxonomySummary,
  getAlerts,
} from "../api/admin";
import { ApiError } from "../api/client";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import BulkActionBar from "../components/soc/BulkActionBar";
import BulkCloseReasonModal from "../components/soc/BulkCloseReasonModal";
import SocFilterBar, { SocFilterValues } from "../components/soc/SocFilterBar";
import SuppressionRuleModal from "../components/soc/SuppressionRuleModal";
import { useToast } from "../components/soc/ToastProvider";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { niktiairSourceLabel } from "../config/niktiairBrands";
import { useCustomerScope } from "../hooks/useCustomerScope";
import { useCallback, useEffect, useMemo, useState } from "react";

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
  { value: "new", label: "Open" },
  { value: "triaged", label: "In Review" },
  { value: "incident_created", label: "Incident created" },
  { value: "false_positive", label: "False Positive" },
  { value: "closed", label: "Closed" },
];

function buildAlertsBase(
  severityFilter: string,
  statusFilter: string,
  category?: string | null,
  extra?: Record<string, string>
): string {
  const params = new URLSearchParams();
  if (category && category !== "all") params.set("category", category);
  if (severityFilter) params.set("severity", severityFilter);
  if (statusFilter) params.set("status", statusFilter);
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v) params.set(k, v);
    }
  }
  const q = params.toString();
  return q ? `/alerts?${q}` : "/alerts";
}

export default function AlertsPage() {
  const { toast } = useToast();
  const { tenantId: scopedTenantId, scopeAll, tenantName } = useCustomerScope();
  const [params, setParams] = useSearchParams();
  const severityFilter = params.get("severity") ?? "";
  const statusFilter = params.get("status") ?? "";
  const categoryFilter = params.get("category") ?? "";
  const qFilter = params.get("q") ?? "";
  const ruleIdFilter = params.get("rule_id") ?? "";
  const hostnameFilter = params.get("hostname") ?? "";
  const processFilter = params.get("process") ?? "";
  const pathFilter = params.get("path") ?? "";
  const userFilter = params.get("user") ?? "";
  const hashFilter = params.get("hash") ?? "";
  const cmdlineFilter = params.get("cmdline") ?? "";
  const sinceFilter = params.get("since") ?? "";
  const aiQueueFilter = params.get("ai_queue") ?? "actionable";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;
  const columnMode = columnModeForCategory(categoryFilter || null);
  const alertsBase = buildAlertsBase(severityFilter, statusFilter, categoryFilter || null, {
    ...(aiQueueFilter && aiQueueFilter !== "actionable" ? { ai_queue: aiQueueFilter } : {}),
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [statusOverrides, setStatusOverrides] = useState<Record<string, string>>({});
  const [suppressOpen, setSuppressOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);

  const loadRuleFacets = useCallback(
    async (q: string) => {
      const res = await getAlertRuleFacets({
        q: q || undefined,
        ...(scopedTenantId ? { tenant_id: scopedTenantId } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        limit: 40,
      });
      return res.rules;
    },
    [scopedTenantId, statusFilter, severityFilter]
  );

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
    category: categoryFilter,
    rule_id: ruleIdFilter,
    hostname: hostnameFilter,
    process: processFilter,
    path: pathFilter,
    user: userFilter,
    hash: hashFilter,
    cmdline: cmdlineFilter,
    since: sinceFilter,
  };

  const listFilters = {
    page,
    page_size: pageSize,
    ...(scopedTenantId ? { tenant_id: scopedTenantId } : {}),
    ...(qFilter ? { q: qFilter } : {}),
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(severityFilter ? { severity: severityFilter } : {}),
    ...(categoryFilter ? { asset_category: categoryFilter } : {}),
    ...(ruleIdFilter ? { rule_id: ruleIdFilter } : {}),
    ...(hostnameFilter ? { hostname: hostnameFilter } : {}),
    ...(processFilter ? { process: processFilter } : {}),
    ...(pathFilter ? { path: pathFilter } : {}),
    ...(userFilter ? { user: userFilter } : {}),
    ...(hashFilter ? { hash: hashFilter } : {}),
    ...(cmdlineFilter ? { cmdline: cmdlineFilter } : {}),
    ...(sinceFilter ? { since: sinceFilter } : {}),
    ...(aiQueueFilter ? { ai_queue: aiQueueFilter } : {}),
  };

  const { status, data, errorMessage, refetch } = useAdminQuery(
    () => getAlerts(listFilters),
    [
      scopedTenantId,
      severityFilter,
      statusFilter,
      categoryFilter,
      qFilter,
      ruleIdFilter,
      hostnameFilter,
      processFilter,
      pathFilter,
      userFilter,
      hashFilter,
      cmdlineFilter,
      sinceFilter,
      aiQueueFilter,
      page,
      pageSize,
    ]
  );

  const [taxonomyCounts, setTaxonomyCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    getAlertTaxonomySummary({
      ...(scopedTenantId ? { tenant_id: scopedTenantId } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
      ...(severityFilter ? { severity: severityFilter } : {}),
    })
      .then((res) => setTaxonomyCounts(res.counts))
      .catch(() => undefined);
  }, [scopedTenantId, severityFilter, statusFilter, data]);

  useEffect(() => {
    setSelected(new Set());
    setStatusOverrides({});
  }, [
    scopedTenantId,
    severityFilter,
    statusFilter,
    categoryFilter,
    qFilter,
    ruleIdFilter,
    hostnameFilter,
    processFilter,
    pathFilter,
    userFilter,
    hashFilter,
    cmdlineFilter,
    sinceFilter,
    aiQueueFilter,
    page,
    pageSize,
  ]);

  const alerts: Alert[] = useMemo(() => {
    const rows = status === "success" && data ? data.alerts : [];
    return rows.map((a) =>
      statusOverrides[a.id] ? { ...a, status: statusOverrides[a.id] } : a
    );
  }, [status, data, statusOverrides]);

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

  const pageIds = alerts.map((a) => a.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const selectedAlerts = alerts.filter((a) => selected.has(a.id));

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllPage() {
    setSelected((prev) => {
      if (allPageSelected) {
        const next = new Set(prev);
        pageIds.forEach((id) => next.delete(id));
        return next;
      }
      const next = new Set(prev);
      pageIds.forEach((id) => next.add(id));
      return next;
    });
  }

  async function runBulkStatus(
    nextStatus: "false_positive" | "closed",
    reason?: string,
    idsOverride?: string[]
  ) {
    const ids = idsOverride ?? Array.from(selected);
    if (ids.length === 0 || bulkBusy) return;
    setBulkBusy(true);
    const prev = { ...statusOverrides };
    setStatusOverrides((o) => {
      const next = { ...o };
      ids.forEach((id) => {
        next[id] = nextStatus;
      });
      return next;
    });
    try {
      const res = await bulkUpdateAlerts({
        alert_ids: ids,
        status: nextStatus,
        reason: reason || null,
      });
      toast(
        `Updated ${res.updated} alert${res.updated === 1 ? "" : "s"} → ${
          nextStatus === "false_positive" ? "False Positive" : "Closed"
        }`,
        "success"
      );
      setSelected(new Set());
      refetch();
    } catch (err) {
      setStatusOverrides(prev);
      toast(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Bulk alert update failed",
        "error"
      );
    } finally {
      setBulkBusy(false);
    }
  }

  async function runApproveLowPriority(idsOverride?: string[]) {
    const ids = idsOverride ?? (selected.size > 0 ? Array.from(selected) : alerts.map((a) => a.id));
    if (ids.length === 0 || bulkBusy) return;
    setBulkBusy(true);
    try {
      const res = await bulkUpdateAlerts({
        alert_ids: ids,
        action: "approve_ai_low_priority",
        create_suppressions: true,
        reason: "Approved AI low-priority closures (bulk)",
      });
      const supp = res.suppressions_created ?? 0;
      toast(
        `Approved ${res.updated} low-priority alert${res.updated === 1 ? "" : "s"}` +
          (supp ? ` · ${supp} suppression${supp === 1 ? "" : "s"} created` : "") +
          (res.skipped_ids?.length ? ` · ${res.skipped_ids.length} skipped` : ""),
        "success"
      );
      setSelected(new Set());
      setApproveOpen(false);
      refetch();
    } catch (err) {
      toast(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Approve low-priority failed",
        "error"
      );
    } finally {
      setBulkBusy(false);
    }
  }

  const isLowPriorityTab = aiQueueFilter === "low_priority";

  return (
    <div>
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
            customer.
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
            {filterLabel ? (
              <>
                {" · "}
                Severity: <strong style={{ textTransform: "capitalize" }}>{filterLabel}</strong>
              </>
            ) : null}
          </>
        )}
      </p>

      <div className="soc-queue-tabs" role="tablist" aria-label="Alert queue">
        <button
          type="button"
          role="tab"
          aria-selected={!isLowPriorityTab}
          className={`soc-queue-tab${!isLowPriorityTab ? " is-active" : ""}`}
          onClick={() => patchParams({ ai_queue: "actionable", page: "1" })}
          data-testid="alerts-queue-actionable"
        >
          Actionable
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isLowPriorityTab}
          className={`soc-queue-tab${isLowPriorityTab ? " is-active" : ""}`}
          onClick={() => patchParams({ ai_queue: "low_priority", page: "1" })}
          data-testid="alerts-queue-low-priority"
        >
          Low-Priority / AI Reviewed
        </button>
      </div>
      {isLowPriorityTab ? (
        <p className="page-subtitle soc-queue-hint">
          BENIGN_FALSE_POSITIVE with AI confidence ≥ 85%. Default Actionable queue excludes these.{" "}
          <button
            type="button"
            className="btn btn-primary btn-small"
            disabled={bulkBusy || alerts.length === 0}
            onClick={() => setApproveOpen(true)}
            data-testid="approve-all-low-priority"
          >
            Approve All Low-Priority Closures
          </button>
        </p>
      ) : (
        <p className="page-subtitle soc-queue-hint">
          Default actionable queue — excludes Low-Priority / AI Reviewed items.
        </p>
      )}

      <SocFilterBar
        searchPlaceholder="Search title, host, rule, process, path, user…"
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
        showDeviceTypeFilter
        deviceTypeCounts={taxonomyCounts}
        presetNamespace="admin.alerts"
        showAlertFacets
        loadRuleFacets={loadRuleFacets}
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
          <div className="table-wrap alerts-table-wrap">
          <table className="data-table alerts-data-table">
            <thead>
              <tr>
                <th className="soc-check-col">
                  <input
                    type="checkbox"
                    checked={allPageSelected}
                    onChange={toggleAllPage}
                    aria-label="Select all on page"
                    data-testid="alerts-select-all"
                  />
                </th>
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
                    <th>Host</th>
                    <th>Category</th>
                    <th>Source</th>
                  </>
                )}
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => {
                const ctx = alert.contextual || {};
                const hostVal = String(ctx.hostname ?? alert.asset_hostname ?? alert.destination_host ?? "—");
                return (
                  <tr
                    key={alert.id}
                    className={selected.has(alert.id) ? "is-selected-row" : undefined}
                  >
                    <td className="soc-check-col">
                      <input
                        type="checkbox"
                        checked={selected.has(alert.id)}
                        onChange={() => toggleOne(alert.id)}
                        aria-label={`Select alert ${alert.alert_title}`}
                      />
                    </td>
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
                        <td className="cell-mono">
                          {hostVal !== "—" ? (
                            <Link
                              className="soc-click-filter"
                              to={`${alertsBase}${alertsBase.includes("?") ? "&" : "?"}hostname=${encodeURIComponent(hostVal)}`}
                              onClick={(e) => e.stopPropagation()}
                              title={`Filter by hostname ${hostVal}`}
                            >
                              {hostVal}
                            </Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>{String(ctx.user ?? "—")}</td>
                        <td>
                          <Link to={`/alerts/${alert.id}`}>{alert.alert_title}</Link>
                          {alert.wazuh_rule_id ? (
                            <>
                              {" "}
                              <Link
                                className="soc-click-filter cell-mono"
                                to={`${alertsBase}${alertsBase.includes("?") ? "&" : "?"}rule_id=${encodeURIComponent(alert.wazuh_rule_id)}`}
                                onClick={(e) => e.stopPropagation()}
                                title={`Filter by rule ${alert.wazuh_rule_id}`}
                              >
                                [{alert.wazuh_rule_id}]
                              </Link>
                            </>
                          ) : null}
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
                          {alert.wazuh_rule_id ? (
                            <>
                              {" "}
                              <Link
                                className="soc-click-filter cell-mono"
                                to={`${alertsBase}${alertsBase.includes("?") ? "&" : "?"}rule_id=${encodeURIComponent(alert.wazuh_rule_id)}`}
                                onClick={(e) => e.stopPropagation()}
                                title={`Filter by rule ${alert.wazuh_rule_id}`}
                              >
                                [{alert.wazuh_rule_id}]
                              </Link>
                            </>
                          ) : null}
                        </td>
                        <td className="cell-mono">
                          {hostVal !== "—" ? (
                            <Link
                              className="soc-click-filter"
                              to={`${alertsBase}${alertsBase.includes("?") ? "&" : "?"}hostname=${encodeURIComponent(hostVal)}`}
                              onClick={(e) => e.stopPropagation()}
                              title={`Filter by hostname ${hostVal}`}
                            >
                              {hostVal}
                            </Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>{alert.asset_category_label ?? alert.asset_category ?? "—"}</td>
                        <td>{niktiairSourceLabel(alert.source_tool)}</td>
                      </>
                    )}
                    <td>
                      <SeverityPill
                        value={alert.status}
                        kind="status"
                        statusDomain="alert"
                        filterBase={alertsBase}
                      />
                      {alert.ai_queue === "low_priority" || alert.ai_auto_closed ? (
                        <span
                          className="ai-triaged-chip"
                          title={
                            alert.ai_resolution_label ||
                            (alert.ai_verdict
                              ? `${alert.ai_verdict} · ${Math.round(Number(alert.ai_confidence || 0))}%`
                              : "AI Triaged")
                          }
                        >
                          AI Triaged
                        </span>
                      ) : null}
                    </td>
                    <td className="cell-mono">{alert.created_at}</td>
                    <td>
                      <Link className="btn btn-ghost btn-small" to={`/alerts/${alert.id}`}>
                        View
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )
      )}

      <BulkActionBar
        selectedCount={selected.size}
        entityLabel={selected.size === 1 ? "alert selected" : "alerts selected"}
        onClear={() => setSelected(new Set())}
        actions={[
          ...(isLowPriorityTab
            ? [
                {
                  id: "approve-lp",
                  label: "Approve All Low-Priority Closures",
                  tone: "primary" as const,
                  disabled: bulkBusy || alerts.length === 0,
                  onClick: () => setApproveOpen(true),
                },
              ]
            : []),
          {
            id: "fp",
            label: "Bulk Mark False Positive",
            tone: "danger",
            disabled: bulkBusy,
            onClick: () => void runBulkStatus("false_positive"),
          },
          {
            id: "close",
            label: "Bulk Close",
            disabled: bulkBusy,
            onClick: () => setCloseOpen(true),
          },
          {
            id: "suppress",
            label: "Create Suppression Rule",
            tone: "primary",
            disabled: bulkBusy || selected.size === 0,
            onClick: () => setSuppressOpen(true),
          },
        ]}
      />

      <BulkCloseReasonModal
        open={closeOpen}
        onClose={() => setCloseOpen(false)}
        onConfirm={(reason) => runBulkStatus("closed", reason)}
      />

      {approveOpen ? (
        <div
          className="modal-root"
          role="dialog"
          aria-modal="true"
          aria-label="Approve AI low-priority closures"
        >
          <button
            type="button"
            className="modal-backdrop"
            aria-label="Cancel"
            onClick={() => setApproveOpen(false)}
          />
          <div className="modal-card card-surface">
            <h2 className="modal-title">Approve Low-Priority Closures</h2>
            <p className="modal-body">
              Close{" "}
              <strong>
                {selected.size > 0 ? selected.size : alerts.length}
              </strong>{" "}
              {selected.size > 0 ? "selected" : "visible"} alert
              {(selected.size > 0 ? selected.size : alerts.length) === 1 ? "" : "s"} as false
              positive and create suppressions from cached AI suggested scope (rule + host/path)
              where available. This is audited.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-ghost"
                disabled={bulkBusy}
                onClick={() => setApproveOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={bulkBusy}
                onClick={() => void runApproveLowPriority()}
                data-testid="approve-low-priority-confirm"
              >
                {bulkBusy ? "Working…" : "Confirm approve & suppress"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <SuppressionRuleModal
        open={suppressOpen}
        seedAlerts={selectedAlerts}
        onClose={() => setSuppressOpen(false)}
        onCreated={async () => {
          const ids = Array.from(selected);
          toast("Suppression created", "success");
          await runBulkStatus("false_positive", "Closed via suppression rule", ids);
        }}
      />
    </div>
  );
}
