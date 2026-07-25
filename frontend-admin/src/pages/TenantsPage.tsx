import { FormEvent, useState } from "react";
import {
  Tenant,
  TenantCreateRequest,
  TenantCriticality,
  TenantSlaLevel,
  TenantStatus,
  createTenant,
  getTenantDetail,
  getTenants,
  updateTenant,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

const STATUS_OPTIONS: TenantStatus[] = ["onboarding", "active", "inactive", "suspended"];
const SLA_OPTIONS: TenantSlaLevel[] = ["standard", "business", "premium", "24x7"];
const CRITICALITY_OPTIONS: TenantCriticality[] = ["low", "medium", "high", "critical"];

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) return "Access denied. Only platform_admin can create or edit customers.";
    if (err.status === 409) return "A customer with this short code already exists.";
  }
  return fallback;
}

type CreateFormState = {
  name: string;
  short_code: string;
  status: TenantStatus;
  sla_level: TenantSlaLevel;
  business_criticality: TenantCriticality;
  timezone: string;
  notes: string;
};

type EditFormState = {
  name: string;
  status: TenantStatus;
  sla_level: TenantSlaLevel;
  business_criticality: TenantCriticality;
  timezone: string;
  notes: string;
};

const EMPTY_CREATE: CreateFormState = {
  name: "",
  short_code: "",
  status: "active",
  sla_level: "standard",
  business_criticality: "medium",
  timezone: "Asia/Kolkata",
  notes: "",
};

export default function TenantsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin";
  const { status, data, errorMessage, refetch } = useAdminQuery(() => getTenants(), []);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFormState>(EMPTY_CREATE);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  const [editing, setEditing] = useState<Tenant | null>(null);
  const [editForm, setEditForm] = useState<EditFormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);

  function openCreate() {
    setCreateForm(EMPTY_CREATE);
    setCreateError(null);
    setCreateSuccess(null);
    setShowCreate(true);
  }

  function openEdit(tenant: Tenant) {
    setEditing(tenant);
    setEditForm({
      name: tenant.name,
      status: tenant.status as TenantStatus,
      sla_level: tenant.sla_level as TenantSlaLevel,
      business_criticality: tenant.business_criticality as TenantCriticality,
      timezone: tenant.timezone || "Asia/Kolkata",
      notes: "",
    });
    setEditError(null);
    setEditSuccess(null);
    getTenantDetail(tenant.id)
      .then((detail) => {
        setEditForm({
          name: detail.name,
          status: detail.status as TenantStatus,
          sla_level: detail.sla_level as TenantSlaLevel,
          business_criticality: detail.business_criticality as TenantCriticality,
          timezone: detail.timezone || "Asia/Kolkata",
          notes: detail.notes ?? "",
        });
      })
      .catch((err) => {
        setEditError(apiErrorMessage(err, "Could not load customer details for editing."));
      });
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!canWrite) return;
    setCreating(true);
    setCreateError(null);
    setCreateSuccess(null);
    const payload: TenantCreateRequest = {
      name: createForm.name.trim(),
      short_code: createForm.short_code.trim().toUpperCase(),
      status: createForm.status,
      sla_level: createForm.sla_level,
      business_criticality: createForm.business_criticality,
      timezone: createForm.timezone.trim() || "Asia/Kolkata",
      notes: createForm.notes.trim() || null,
    };
    try {
      const created = await createTenant(payload);
      setCreateSuccess(
        `Customer "${created.name}" (${created.short_code}) created. Next: Users → Add User (customer_admin), then Appliances → activation token.`
      );
      setCreateForm(EMPTY_CREATE);
      setShowCreate(false);
      refetch();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create customer."));
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(event: FormEvent) {
    event.preventDefault();
    if (!canWrite || !editing || !editForm) return;
    setSaving(true);
    setEditError(null);
    setEditSuccess(null);
    try {
      const updated = await updateTenant(editing.id, {
        name: editForm.name.trim(),
        status: editForm.status,
        sla_level: editForm.sla_level,
        business_criticality: editForm.business_criticality,
        timezone: editForm.timezone.trim() || "Asia/Kolkata",
        notes: editForm.notes.trim() || null,
      });
      setEditSuccess(`Saved changes for ${updated.name} (${updated.short_code}).`);
      setEditing(null);
      setEditForm(null);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update customer."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Customers / Tenants</h1>
          <p className="page-subtitle">
            Onboard and manage MSSP customers from this dashboard. Short codes are permanent
            identifiers used in customer portal URLs.
          </p>
        </div>
        {canWrite && (
          <button className="btn btn-primary" type="button" onClick={openCreate}>
            Add Customer
          </button>
        )}
      </div>

      {!canWrite && (
        <div className="state-message" style={{ marginBottom: "1rem" }}>
          You can view customers. Creating or editing requires a platform_admin account.
        </div>
      )}

      {createSuccess && <div className="state-message state-success">{createSuccess}</div>}
      {editSuccess && <div className="state-message state-success">{editSuccess}</div>}

      {showCreate && canWrite && (
        <form className="management-panel" onSubmit={handleCreate}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Add Customer
          </h2>
          <div className="form-grid">
            <label className="form-label">
              Customer name
              <input
                className="form-input"
                required
                maxLength={200}
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Short code (2–20 chars, letters/numbers/_/-)
              <input
                className="form-input"
                required
                minLength={2}
                maxLength={20}
                pattern="[A-Za-z0-9_-]+"
                value={createForm.short_code}
                onChange={(e) => setCreateForm({ ...createForm, short_code: e.target.value })}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={createForm.status}
                onChange={(e) =>
                  setCreateForm({ ...createForm, status: e.target.value as TenantStatus })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              SLA level
              <select
                className="form-input"
                value={createForm.sla_level}
                onChange={(e) =>
                  setCreateForm({ ...createForm, sla_level: e.target.value as TenantSlaLevel })
                }
              >
                {SLA_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Business criticality
              <select
                className="form-input"
                value={createForm.business_criticality}
                onChange={(e) =>
                  setCreateForm({
                    ...createForm,
                    business_criticality: e.target.value as TenantCriticality,
                  })
                }
              >
                {CRITICALITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Timezone
              <input
                className="form-input"
                maxLength={64}
                value={createForm.timezone}
                onChange={(e) => setCreateForm({ ...createForm, timezone: e.target.value })}
              />
            </label>
            <label className="form-label form-grid-full">
              Notes (internal)
              <textarea
                className="form-input"
                rows={3}
                value={createForm.notes}
                onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
              />
            </label>
          </div>
          {createError && <div className="form-error">{createError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create customer"}
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

      {editing && editForm && canWrite && (
        <form className="management-panel" onSubmit={handleEdit}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Edit {editing.name} ({editing.short_code})
          </h2>
          <p className="page-subtitle" style={{ marginBottom: "12px" }}>
            Short code cannot be changed after creation.
          </p>
          <div className="form-grid">
            <label className="form-label">
              Customer name
              <input
                className="form-input"
                required
                maxLength={200}
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={editForm.status}
                onChange={(e) =>
                  setEditForm({ ...editForm, status: e.target.value as TenantStatus })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              SLA level
              <select
                className="form-input"
                value={editForm.sla_level}
                onChange={(e) =>
                  setEditForm({ ...editForm, sla_level: e.target.value as TenantSlaLevel })
                }
              >
                {SLA_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Business criticality
              <select
                className="form-input"
                value={editForm.business_criticality}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    business_criticality: e.target.value as TenantCriticality,
                  })
                }
              >
                {CRITICALITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Timezone
              <input
                className="form-input"
                maxLength={64}
                value={editForm.timezone}
                onChange={(e) => setEditForm({ ...editForm, timezone: e.target.value })}
              />
            </label>
            <label className="form-label form-grid-full">
              Notes (optional — leave blank to clear, or type new notes)
              <textarea
                className="form-input"
                rows={3}
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
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
                setEditing(null);
                setEditForm(null);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {status === "loading" && <div className="state-message">Loading customers...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view customers.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.tenants.length === 0 ? (
          <div className="state-message">No customers yet. Use Add Customer to onboard the first one.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Short Code</th>
                <th>Status</th>
                <th>SLA Level</th>
                <th>Criticality</th>
                <th>Appliances</th>
                <th>Protected Assets</th>
                <th>Incidents</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data.tenants.map((tenant) => (
                <tr key={tenant.id}>
                  <td>{tenant.name}</td>
                  <td>{tenant.short_code}</td>
                  <td>
                    <span className={`badge badge-${tenant.status}`}>{tenant.status}</span>
                  </td>
                  <td>{tenant.sla_level}</td>
                  <td>{tenant.business_criticality}</td>
                  <td>{tenant.appliances}</td>
                  <td>{tenant.protected_assets}</td>
                  <td>{tenant.incidents}</td>
                  {canWrite && (
                    <td>
                      <button
                        className="btn btn-small"
                        type="button"
                        onClick={() => openEdit(tenant)}
                      >
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
