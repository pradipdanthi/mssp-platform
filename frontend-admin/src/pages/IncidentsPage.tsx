import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { bulkUpdateIncidents, getIncidents, Incident } from "../api/admin";
import { ApiError } from "../api/client";
import CustomerScopeBanner from "../components/CustomerScopeBanner";
import RowActionsMenu from "../components/RowActionsMenu";
import BulkActionBar from "../components/soc/BulkActionBar";
import SocFilterBar, { SocFilterValues } from "../components/soc/SocFilterBar";
import { useToast } from "../components/soc/ToastProvider";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useCustomerScope } from "../hooks/useCustomerScope";
import { useEffect, useMemo, useState } from "react";

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

type CloseReason = "false_positive" | "benign_admin_activity" | "resolved";

export default function IncidentsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { tenantFilter } = useCustomerScope();
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status") ?? "";
  const severityFilter = params.get("severity") ?? "";
  const qFilter = params.get("q") ?? "";
  const aiQueueFilter = params.get("ai_queue") ?? "actionable";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("page_size")))
    ? Number(params.get("page_size"))
    : 25;

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [statusOverrides, setStatusOverrides] = useState<Record<string, string>>({});
  const [bulkBusy, setBulkBusy] = useState(false);
  const [closePrompt, setClosePrompt] = useState<{
    status: "closed" | "resolved";
  } | null>(null);
  const [closeReason, setCloseReason] = useState<CloseReason>("resolved");

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
    since: params.get("since") ?? "",
  };

  const sinceFilter = params.get("since") ?? "";

  const { status, data, errorMessage, refetch } = useAdminQuery(
    () =>
      getIncidents({
        page,
        page_size: pageSize,
        ...tenantFilter,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(severityFilter ? { severity: severityFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
        ...(sinceFilter ? { since: sinceFilter } : {}),
        ...(aiQueueFilter ? { ai_queue: aiQueueFilter } : {}),
      }),
    [tenantFilter, statusFilter, severityFilter, qFilter, sinceFilter, aiQueueFilter, page, pageSize]
  );

  useEffect(() => {
    setSelected(new Set());
    setStatusOverrides({});
  }, [tenantFilter, statusFilter, severityFilter, qFilter, sinceFilter, aiQueueFilter, page, pageSize]);

  const incidents: Incident[] = useMemo(() => {
    const rows = status === "success" && data ? data.incidents : [];
    return rows.map((i) =>
      statusOverrides[i.id] ? { ...i, status: statusOverrides[i.id] } : i
    );
  }, [status, data, statusOverrides]);

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

  const pageIds = incidents.map((i) => i.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

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

  async function runBulkClose(nextStatus: "closed" | "resolved", reason: CloseReason) {
    const ids = Array.from(selected);
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
      const res = await bulkUpdateIncidents({
        incident_ids: ids,
        status: nextStatus,
        close_reason: reason,
      });
      toast(
        `${nextStatus === "resolved" ? "Resolved" : "Closed"} ${res.updated} incident${
          res.updated === 1 ? "" : "s"
        }`,
        "success"
      );
      setSelected(new Set());
      setClosePrompt(null);
      refetch();
    } catch (err) {
      setStatusOverrides(prev);
      toast(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Bulk incident update failed",
        "error"
      );
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <CustomerScopeBanner />
      <p className="page-subtitle">
        Open and historical incidents across all tenants. Search by number, title, or tenant; use
        filters and pagination when queues grow large. Select rows for bulk close/resolve.
      </p>

      <div className="soc-queue-tabs" role="tablist" aria-label="Incident queue">
        <button
          type="button"
          role="tab"
          aria-selected={aiQueueFilter !== "low_priority"}
          className={`soc-queue-tab${aiQueueFilter !== "low_priority" ? " is-active" : ""}`}
          onClick={() => patchParams({ ai_queue: "actionable", page: "1" })}
          data-testid="incidents-queue-actionable"
        >
          Actionable
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={aiQueueFilter === "low_priority"}
          className={`soc-queue-tab${aiQueueFilter === "low_priority" ? " is-active" : ""}`}
          onClick={() => patchParams({ ai_queue: "low_priority", page: "1" })}
          data-testid="incidents-queue-low-priority"
        >
          Low-Priority / AI Reviewed
        </button>
      </div>
      <p className="page-subtitle soc-queue-hint">
        {aiQueueFilter === "low_priority"
          ? "Incidents whose primary alert is AI low-priority (BENIGN_FALSE_POSITIVE ≥ 85%)."
          : "Default actionable queue — excludes incidents with AI low-priority primary alerts."}
      </p>

      <SocFilterBar
        searchPlaceholder="Search number, title, tenant, summary…"
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
        presetNamespace="admin.incidents"
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {status === "loading" && <div className="state-message">Loading incidents...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view incidents.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        incidents.length === 0 ? (
          <div className="state-message">
            No incidents{statusFilter ? ` matching “${statusFilter}”` : ""} in this view.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th className="soc-check-col">
                  <input
                    type="checkbox"
                    checked={allPageSelected}
                    onChange={toggleAllPage}
                    aria-label="Select all on page"
                    data-testid="incidents-select-all"
                  />
                </th>
                <th>Tenant</th>
                <th>Incident #</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Assigned To</th>
                <th>Opened</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((incident) => (
                <tr
                  key={incident.id}
                  className={selected.has(incident.id) ? "is-selected-row" : undefined}
                >
                  <td className="soc-check-col">
                    <input
                      type="checkbox"
                      checked={selected.has(incident.id)}
                      onChange={() => toggleOne(incident.id)}
                      aria-label={`Select incident ${incident.incident_number}`}
                    />
                  </td>
                  <td>{incident.tenant_name}</td>
                  <td className="cell-mono">
                    <Link to={`/incidents/${incident.id}`}>{incident.incident_number}</Link>
                  </td>
                  <td>{incident.title}</td>
                  <td>
                    <SeverityPill value={incident.severity} filterBase="/incidents" />
                  </td>
                  <td>
                    <SeverityPill
                      value={incident.status}
                      kind="status"
                      statusDomain="incident"
                      filterBase="/incidents"
                    />
                    {incident.ai_queue === "low_priority" || incident.ai_auto_closed ? (
                      <span className="ai-triaged-chip" title="Primary alert AI triaged">
                        AI Triaged
                      </span>
                    ) : null}
                  </td>
                  <td>{incident.assigned_to ?? "Unassigned"}</td>
                  <td className="cell-mono">{incident.opened_at ?? "—"}</td>
                  <td>
                    <RowActionsMenu
                      actions={[
                        {
                          id: "open",
                          label: "Open detail",
                          onClick: () => navigate(`/incidents/${incident.id}`),
                        },
                        {
                          id: "alerts",
                          label: "Related alerts",
                          onClick: () =>
                            navigate(`/alerts?severity=${encodeURIComponent(incident.severity)}`),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      <BulkActionBar
        selectedCount={selected.size}
        entityLabel={selected.size === 1 ? "incident selected" : "incidents selected"}
        onClear={() => setSelected(new Set())}
        actions={[
          {
            id: "resolve",
            label: "Resolve",
            tone: "primary",
            disabled: bulkBusy,
            onClick: () => {
              setCloseReason("resolved");
              setClosePrompt({ status: "resolved" });
            },
          },
          {
            id: "close",
            label: "Close",
            tone: "danger",
            disabled: bulkBusy,
            onClick: () => {
              setCloseReason("false_positive");
              setClosePrompt({ status: "closed" });
            },
          },
        ]}
      />

      {closePrompt ? (
        <div className="modal-root" role="dialog" aria-modal="true" aria-label="Bulk close reason">
          <button
            type="button"
            className="modal-backdrop"
            aria-label="Cancel"
            onClick={() => setClosePrompt(null)}
          />
          <div className="modal-card card-surface">
            <h2 className="modal-title">
              {closePrompt.status === "resolved" ? "Resolve" : "Close"} {selected.size} incident
              {selected.size === 1 ? "" : "s"}
            </h2>
            <p className="modal-body">Select a close reason (required by the bulk API).</p>
            <label className="list-toolbar-field">
              <span>Close reason</span>
              <select
                value={closeReason}
                onChange={(e) => setCloseReason(e.target.value as CloseReason)}
                disabled={bulkBusy}
              >
                <option value="false_positive">False positive</option>
                <option value="benign_admin_activity">Benign admin activity</option>
                <option value="resolved">Resolved</option>
              </select>
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setClosePrompt(null)}
                disabled={bulkBusy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={bulkBusy}
                onClick={() => void runBulkClose(closePrompt.status, closeReason)}
              >
                {bulkBusy ? "Working…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
