import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  bulkUpdateCustomerAlerts,
  CustomerAlert,
  getCustomerAlertRuleFacets,
  getCustomerAlerts,
} from "../api/customer";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import SeverityPill from "../components/SeverityPill";
import BulkActionBar from "../components/soc/BulkActionBar";
import BulkCloseReasonModal from "../components/soc/BulkCloseReasonModal";
import SocFilterBar, { SocFilterValues } from "../components/soc/SocFilterBar";
import SuppressionRuleModal from "../components/soc/SuppressionRuleModal";
import { useCustomerQuery } from "../hooks/useCustomerQuery";

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
  { value: "false_positive", label: "False positive" },
  { value: "closed", label: "Closed" },
];

function buildAlertsBase(extra?: Record<string, string>): string {
  const params = new URLSearchParams();
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v) params.set(k, v);
    }
  }
  const q = params.toString();
  return q ? `/alerts?${q}` : "/alerts";
}

export default function AlertsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const canBulk = user?.role === "customer_admin";
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
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [statusOverrides, setStatusOverrides] = useState<Record<string, string>>({});
  const [suppressOpen, setSuppressOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);

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

  const alertsBase = buildAlertsBase({
    ...(severityFilter ? { severity: severityFilter } : {}),
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(categoryFilter ? { category: categoryFilter } : {}),
    ...(qFilter ? { q: qFilter } : {}),
    ...(ruleIdFilter ? { rule_id: ruleIdFilter } : {}),
    ...(hostnameFilter ? { hostname: hostnameFilter } : {}),
    ...(processFilter ? { process: processFilter } : {}),
    ...(pathFilter ? { path: pathFilter } : {}),
    ...(userFilter ? { user: userFilter } : {}),
    ...(hashFilter ? { hash: hashFilter } : {}),
    ...(cmdlineFilter ? { cmdline: cmdlineFilter } : {}),
    ...(sinceFilter ? { since: sinceFilter } : {}),
  });

  const loadRuleFacets = useCallback(
    async (q: string) => {
      if (!shortCode) return [];
      const res = await getCustomerAlertRuleFacets(shortCode, {
        q: q || undefined,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        limit: 40,
      });
      return res.rules;
    },
    [shortCode, statusFilter, severityFilter]
  );

  const { status, data, errorMessage, refetch } = useCustomerQuery(
    () =>
      getCustomerAlerts(shortCode as string, {
        page,
        page_size: pageSize,
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
      }),
    Boolean(shortCode),
    [
      shortCode,
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
      page,
      pageSize,
    ]
  );

  useEffect(() => {
    setSelected(new Set());
    setStatusOverrides({});
  }, [
    shortCode,
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
    page,
    pageSize,
  ]);

  const alerts: CustomerAlert[] = useMemo(() => {
    const rows = status === "success" && data ? data.alerts : [];
    return rows.map((a) =>
      statusOverrides[a.alert_id] ? { ...a, status: statusOverrides[a.alert_id] } : a
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

  const pageIds = alerts.map((a) => a.alert_id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const selectedAlerts = alerts.filter((a) => selected.has(a.alert_id));

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
    if (!shortCode || !canBulk) return;
    const ids = idsOverride ?? Array.from(selected);
    if (ids.length === 0 || bulkBusy) return;
    setBulkBusy(true);
    setBulkMessage(null);
    const prev = { ...statusOverrides };
    setStatusOverrides((o) => {
      const next = { ...o };
      ids.forEach((id) => {
        next[id] = nextStatus;
      });
      return next;
    });
    try {
      const res = await bulkUpdateCustomerAlerts(shortCode, {
        alert_ids: ids,
        status: nextStatus,
        reason: reason || null,
      });
      setBulkMessage(
        `Updated ${res.updated} alert${res.updated === 1 ? "" : "s"} → ${
          nextStatus === "false_positive" ? "False Positive" : "Closed"
        }`
      );
      setSelected(new Set());
      refetch();
    } catch (err) {
      setStatusOverrides(prev);
      setBulkMessage(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Bulk alert update failed"
      );
    } finally {
      setBulkBusy(false);
    }
  }

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Alerts</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so alert data cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-subtitle">
        Customer-visible alerts for your organization. Use search, time, and forensic filters to
        hunt; save named views for one-click return. Internal SOC-only alerts are not shown here.
        {canBulk ? " Administrators can bulk-mark false positives, close, or suppress." : null}
      </p>

      <SocFilterBar
        searchPlaceholder="Search title, host, rule, process, path…"
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
        presetNamespace="customer.alerts"
        loadRuleFacets={loadRuleFacets}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {bulkMessage ? (
        <div className={`state-message ${bulkMessage.includes("failed") || bulkMessage.includes("Unable") ? "state-error" : ""}`}>
          {bulkMessage}
        </div>
      ) : null}

      {status === "loading" && <div className="state-message">Loading alerts…</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view alerts.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        alerts.length === 0 ? (
          <div className="state-message">No alerts match the current filters.</div>
        ) : (
          <div className="table-wrap alerts-table-wrap">
            <table className="data-table alerts-data-table">
              <colgroup>
                {canBulk ? <col className="alerts-col-check" /> : null}
                <col className="alerts-col-sev" />
                <col className="alerts-col-title" />
                <col className="alerts-col-host" />
                <col className="alerts-col-cat" />
                <col className="alerts-col-source" />
                <col className="alerts-col-status" />
                <col className="alerts-col-created" />
                <col className="alerts-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  {canBulk ? (
                    <th className="soc-check-col">
                      <input
                        type="checkbox"
                        checked={allPageSelected}
                        onChange={toggleAllPage}
                        aria-label="Select all on page"
                        data-testid="alerts-select-all"
                      />
                    </th>
                  ) : null}
                  <th>Severity</th>
                  <th>Title</th>
                  <th>Host</th>
                  <th>Category</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => {
                  const hostVal = a.hostname || "—";
                  return (
                    <tr
                      key={a.alert_id}
                      className={selected.has(a.alert_id) ? "is-selected-row" : undefined}
                    >
                      {canBulk ? (
                        <td className="soc-check-col">
                          <input
                            type="checkbox"
                            checked={selected.has(a.alert_id)}
                            onChange={() => toggleOne(a.alert_id)}
                            aria-label={`Select alert ${a.title}`}
                          />
                        </td>
                      ) : null}
                      <td>
                        <SeverityPill value={a.severity} kind="severity" filterBase="/alerts" />
                      </td>
                      <td>
                        <Link to={`/alerts/${a.alert_id}`} title="Open alert detail">
                          {a.title}
                        </Link>
                        {a.wazuh_rule_id ? (
                          <>
                            {" "}
                            <Link
                              className="soc-click-filter cell-mono"
                              to={`${alertsBase}${alertsBase.includes("?") ? "&" : "?"}rule_id=${encodeURIComponent(a.wazuh_rule_id)}`}
                              onClick={(e) => e.stopPropagation()}
                              title={`Filter by rule ${a.wazuh_rule_id}`}
                            >
                              [{a.wazuh_rule_id}]
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
                      <td>{a.asset_category_label ?? a.asset_category ?? "—"}</td>
                      <td>{a.source || "—"}</td>
                      <td>
                        <SeverityPill value={a.status} kind="status" filterBase="/alerts" />
                      </td>
                      <td className="cell-mono">
                        {a.detected_at ? new Date(a.detected_at).toLocaleString() : "—"}
                      </td>
                      <td>
                        <Link className="btn btn-ghost btn-small" to={`/alerts/${a.alert_id}`}>
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

      {canBulk ? (
        <>
          <BulkActionBar
            selectedCount={selected.size}
            entityLabel={selected.size === 1 ? "alert selected" : "alerts selected"}
            onClear={() => setSelected(new Set())}
            actions={[
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
          <SuppressionRuleModal
            open={suppressOpen}
            shortCode={shortCode}
            seedAlerts={selectedAlerts}
            onClose={() => setSuppressOpen(false)}
            onCreated={async () => {
              const ids = Array.from(selected);
              setBulkMessage("Suppression created");
              await runBulkStatus("false_positive", "Closed via suppression rule", ids);
            }}
          />
        </>
      ) : null}
    </div>
  );
}
