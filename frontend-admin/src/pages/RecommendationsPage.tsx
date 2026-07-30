import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AdminRecommendation,
  RecommendationCreateRequest,
  RecommendationPriority,
  RecommendationStatus,
  Tenant,
  createRecommendation,
  getRecommendationDetail,
  getRecommendations,
  getTenants,
  updateRecommendation,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import SeverityPill from "../components/SeverityPill";
import { useAdminQuery } from "../hooks/useAdminQuery";

const PRIORITIES: RecommendationPriority[] = ["low", "medium", "high", "critical"];
const STATUSES: RecommendationStatus[] = [
  "open",
  "in_progress",
  "accepted_risk",
  "completed",
  "dismissed",
];
const STATUS_OPTIONS = STATUSES.map((s) => ({ value: s, label: s.replace(/_/g, " ") }));

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) {
      return "Access denied. platform_admin or soc_manager can create/edit recommendations.";
    }
  }
  return fallback;
}

type CreateForm = {
  tenant_id: string;
  title: string;
  description: string;
  priority: RecommendationPriority;
  category: string;
  status: RecommendationStatus;
  customer_visible: boolean;
  due_at: string;
};

type EditForm = {
  title: string;
  description: string;
  priority: RecommendationPriority;
  category: string;
  status: RecommendationStatus;
  customer_visible: boolean;
  due_at: string;
};

const EMPTY_CREATE: CreateForm = {
  tenant_id: "",
  title: "",
  description: "",
  priority: "medium",
  category: "general",
  status: "open",
  customer_visible: false,
  due_at: "",
};

export default function RecommendationsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin" || user?.role === "soc_manager";
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status") ?? "";
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
      getRecommendations({
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    [statusFilter, qFilter, page, pageSize]
  );

  const recommendations = status === "success" && data ? data.recommendations : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? recommendations.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateForm>(EMPTY_CREATE);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTenants({ page_size: 200 })
      .then((result) => {
        if (!cancelled) setTenants(result.tenants);
      })
      .catch(() => {
        /* list still works without tenant dropdown fill */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!canWrite) return;
    setCreating(true);
    setCreateError(null);
    setSuccessMessage(null);
    const payload: RecommendationCreateRequest = {
      tenant_id: createForm.tenant_id,
      title: createForm.title.trim(),
      description: createForm.description.trim(),
      priority: createForm.priority,
      category: createForm.category.trim() || "general",
      status: createForm.status,
      customer_visible: createForm.customer_visible,
      due_at: createForm.due_at ? new Date(createForm.due_at).toISOString() : null,
    };
    try {
      const created = await createRecommendation(payload);
      setSuccessMessage(
        `Recommendation created for ${created.short_code}. Customer visible: ${
          created.customer_visible ? "yes" : "no"
        }.`
      );
      setCreateForm(EMPTY_CREATE);
      setShowCreate(false);
      refetch();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create recommendation."));
    } finally {
      setCreating(false);
    }
  }

  async function openEdit(row: AdminRecommendation) {
    setEditingId(row.id);
    setEditError(null);
    setSuccessMessage(null);
    setEditForm({
      title: row.title,
      description: "",
      priority: row.priority as RecommendationPriority,
      category: row.category,
      status: row.status as RecommendationStatus,
      customer_visible: row.customer_visible,
      due_at: row.due_at ? row.due_at.slice(0, 16) : "",
    });
    try {
      const detail = await getRecommendationDetail(row.id);
      setEditForm({
        title: detail.title,
        description: detail.description,
        priority: detail.priority as RecommendationPriority,
        category: detail.category,
        status: detail.status as RecommendationStatus,
        customer_visible: detail.customer_visible,
        due_at: detail.due_at ? detail.due_at.slice(0, 16) : "",
      });
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not load recommendation detail."));
    }
  }

  async function handleEdit(event: FormEvent) {
    event.preventDefault();
    if (!canWrite || !editingId || !editForm) return;
    setSaving(true);
    setEditError(null);
    setSuccessMessage(null);
    try {
      const updated = await updateRecommendation(editingId, {
        title: editForm.title.trim(),
        description: editForm.description.trim(),
        priority: editForm.priority,
        category: editForm.category.trim() || "general",
        status: editForm.status,
        customer_visible: editForm.customer_visible,
        due_at: editForm.due_at ? new Date(editForm.due_at).toISOString() : null,
      });
      setSuccessMessage(`Saved recommendation for ${updated.short_code}.`);
      setEditingId(null);
      setEditForm(null);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update recommendation."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Recommendations</h1>
          <p className="page-subtitle">
            Create customer action items and control whether the customer portal can see them.
          </p>
        </div>
        {canWrite && (
          <button className="btn btn-primary" type="button" onClick={() => setShowCreate(true)}>
            Add Recommendation
          </button>
        )}
      </div>

      {!canWrite && (
        <div className="state-message" style={{ marginBottom: "1rem" }}>
          You can view recommendations. Creating or editing requires platform_admin or soc_manager.
        </div>
      )}

      {successMessage && <div className="state-message state-success">{successMessage}</div>}

      <ListToolbar
        searchPlaceholder="Search title, category, tenant…"
        searchValue={qFilter}
        onSearchChange={(q) => patchParams({ q, page: "1" })}
        statusOptions={STATUS_OPTIONS}
        statusValue={statusFilter}
        onStatusChange={(status) => patchParams({ status, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      {showCreate && canWrite && (
        <form className="management-panel" onSubmit={handleCreate}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Add Recommendation
          </h2>
          <div className="form-grid">
            <label className="form-label">
              Customer
              <select
                className="form-input"
                required
                value={createForm.tenant_id}
                onChange={(e) => setCreateForm({ ...createForm, tenant_id: e.target.value })}
              >
                <option value="">Select customer…</option>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.short_code})
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Priority
              <select
                className="form-input"
                value={createForm.priority}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    priority: e.target.value as RecommendationPriority,
                  })
                }
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Category
              <input
                className="form-input"
                value={createForm.category}
                onChange={(e) => setCreateForm({ ...createForm, category: e.target.value })}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={createForm.status}
                onChange={(e) =>
                  setCreateForm({ ...createForm, status: e.target.value as RecommendationStatus })
                }
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Due date (optional)
              <input
                className="form-input"
                type="datetime-local"
                value={createForm.due_at}
                onChange={(e) => setCreateForm({ ...createForm, due_at: e.target.value })}
              />
            </label>
            <label className="form-label">
              Visible to customer
              <select
                className="form-input"
                value={createForm.customer_visible ? "yes" : "no"}
                onChange={(e) =>
                  setCreateForm({ ...createForm, customer_visible: e.target.value === "yes" })
                }
              >
                <option value="no">no (SOC only)</option>
                <option value="yes">yes (customer portal)</option>
              </select>
            </label>
            <label className="form-label form-grid-full">
              Title
              <input
                className="form-input"
                required
                maxLength={500}
                value={createForm.title}
                onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
              />
            </label>
            <label className="form-label form-grid-full">
              Description (plain English for the customer when visible)
              <textarea
                className="form-input"
                required
                rows={4}
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
              />
            </label>
          </div>
          {createError && <div className="form-error">{createError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create recommendation"}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={creating}
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {editingId && editForm && canWrite && (
        <form className="management-panel" onSubmit={handleEdit}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Edit Recommendation
          </h2>
          <div className="form-grid">
            <label className="form-label">
              Priority
              <select
                className="form-input"
                value={editForm.priority}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    priority: e.target.value as RecommendationPriority,
                  })
                }
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Category
              <input
                className="form-input"
                value={editForm.category}
                onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={editForm.status}
                onChange={(e) =>
                  setEditForm({ ...editForm, status: e.target.value as RecommendationStatus })
                }
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Due date
              <input
                className="form-input"
                type="datetime-local"
                value={editForm.due_at}
                onChange={(e) => setEditForm({ ...editForm, due_at: e.target.value })}
              />
            </label>
            <label className="form-label">
              Visible to customer
              <select
                className="form-input"
                value={editForm.customer_visible ? "yes" : "no"}
                onChange={(e) =>
                  setEditForm({ ...editForm, customer_visible: e.target.value === "yes" })
                }
              >
                <option value="no">no (SOC only)</option>
                <option value="yes">yes (customer portal)</option>
              </select>
            </label>
            <label className="form-label form-grid-full">
              Title
              <input
                className="form-input"
                required
                maxLength={500}
                value={editForm.title}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
              />
            </label>
            <label className="form-label form-grid-full">
              Description
              <textarea
                className="form-input"
                required
                rows={4}
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              />
            </label>
          </div>
          {editError && <div className="form-error">{editError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save changes"}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={saving}
              onClick={() => {
                setEditingId(null);
                setEditForm(null);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {status === "loading" && <div className="state-message">Loading recommendations...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view recommendations.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        recommendations.length === 0 ? (
          <div className="state-message">No recommendations matching this view.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Priority</th>
                <th>Title</th>
                <th>Category</th>
                <th>Status</th>
                <th>Customer visible</th>
                <th>Due</th>
                <th>Created</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {recommendations.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.tenant_name} ({row.short_code})
                  </td>
                  <td>
                    <SeverityPill value={row.priority} kind="priority" />
                  </td>
                  <td>{row.title}</td>
                  <td>{row.category}</td>
                  <td>
                    <SeverityPill value={row.status} kind="status" />
                  </td>
                  <td>{row.customer_visible ? "yes" : "no"}</td>
                  <td>{row.due_at ?? "—"}</td>
                  <td>{row.created_at}</td>
                  {canWrite && (
                    <td>
                      <button className="btn btn-small" type="button" onClick={() => openEdit(row)}>
                        Edit
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
