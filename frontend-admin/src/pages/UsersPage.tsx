import { FormEvent, useEffect, useState } from "react";
import {
  AdminUser,
  PlatformRole,
  Tenant,
  UserStatus,
  createUser,
  getTenants,
  getUsers,
  updateUser,
  updateUserPassword,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

const ROLE_OPTIONS: PlatformRole[] = [
  "platform_admin",
  "soc_manager",
  "soc_analyst",
  "customer_admin",
  "customer_viewer",
];
const CUSTOMER_ROLES: PlatformRole[] = ["customer_admin", "customer_viewer"];
const STATUS_OPTIONS: UserStatus[] = ["active", "inactive", "locked"];

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 403) return "Access denied. Only platform_admin can create or edit users.";
    if (err.status === 409) return "A user with this email already exists.";
  }
  return fallback;
}

type CreateFormState = {
  email: string;
  full_name: string;
  password: string;
  role: PlatformRole;
  tenant_id: string;
  phone: string;
  status: UserStatus;
};

type EditFormState = {
  full_name: string;
  phone: string;
  status: UserStatus;
};

const EMPTY_CREATE: CreateFormState = {
  email: "",
  full_name: "",
  password: "",
  role: "customer_admin",
  tenant_id: "",
  phone: "",
  status: "active",
};

export default function UsersPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin";
  const { status, data, errorMessage, refetch } = useAdminQuery(() => getUsers(), []);

  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantsError, setTenantsError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFormState>(EMPTY_CREATE);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState<EditFormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);

  const [passwordUser, setPasswordUser] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTenants()
      .then((result) => {
        if (!cancelled) setTenants(result.tenants);
      })
      .catch((err) => {
        if (!cancelled) setTenantsError(apiErrorMessage(err, "Could not load customer list for user form."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const needsTenant = CUSTOMER_ROLES.includes(createForm.role);

  function openCreate() {
    setCreateForm(EMPTY_CREATE);
    setCreateError(null);
    setCreateSuccess(null);
    setShowCreate(true);
  }

  function openEdit(u: AdminUser) {
    setEditing(u);
    setEditForm({
      full_name: u.full_name,
      phone: u.phone ?? "",
      status: u.status as UserStatus,
    });
    setEditError(null);
    setEditSuccess(null);
  }

  function openPassword(u: AdminUser) {
    setPasswordUser(u);
    setNewPassword("");
    setPasswordError(null);
    setPasswordSuccess(null);
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!canWrite) return;
    if (needsTenant && !createForm.tenant_id) {
      setCreateError("Customer roles require selecting a customer/tenant.");
      return;
    }
    if (!needsTenant && createForm.tenant_id) {
      setCreateError("SOC/platform roles must not be tied to a customer.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const created = await createUser({
        email: createForm.email.trim(),
        full_name: createForm.full_name.trim(),
        password: createForm.password,
        role: createForm.role,
        tenant_id: needsTenant ? createForm.tenant_id : null,
        phone: createForm.phone.trim() || null,
        status: createForm.status,
      });
      setCreateSuccess(
        `User ${created.full_name} (${created.email}) created as ${created.role}. Give them their password securely — it is not stored in plain text.`
      );
      setCreateForm(EMPTY_CREATE);
      setShowCreate(false);
      refetch();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create user."));
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
      const updated = await updateUser(editing.id, {
        full_name: editForm.full_name.trim(),
        phone: editForm.phone.trim() || null,
        status: editForm.status,
      });
      setEditSuccess(`Saved changes for ${updated.email}.`);
      setEditing(null);
      setEditForm(null);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update user."));
    } finally {
      setSaving(false);
    }
  }

  async function handlePassword(event: FormEvent) {
    event.preventDefault();
    if (!canWrite || !passwordUser) return;
    setPasswordSaving(true);
    setPasswordError(null);
    setPasswordSuccess(null);
    try {
      await updateUserPassword(passwordUser.id, { new_password: newPassword });
      setPasswordSuccess(`Password updated for ${passwordUser.email}. Share the new password securely.`);
      setPasswordUser(null);
      setNewPassword("");
    } catch (err) {
      setPasswordError(apiErrorMessage(err, "Could not set password."));
    } finally {
      setPasswordSaving(false);
    }
  }

  function tenantLabel(tenantId: string | null): string {
    if (!tenantId) return "— (platform/SOC)";
    const match = tenants.find((t) => t.id === tenantId);
    return match ? `${match.name} (${match.short_code})` : tenantId;
  }

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Users</h1>
          <p className="page-subtitle">
            Create SOC staff and customer portal logins. Customer roles must be linked to a
            customer; platform/SOC roles are cross-tenant and must not be.
          </p>
        </div>
        {canWrite && (
          <button className="btn btn-primary" type="button" onClick={openCreate}>
            Add User
          </button>
        )}
      </div>

      {!canWrite && (
        <div className="state-message" style={{ marginBottom: "1rem" }}>
          You can view users. Creating or editing requires a platform_admin account.
        </div>
      )}

      {tenantsError && <div className="state-message state-error">{tenantsError}</div>}
      {createSuccess && <div className="state-message state-success">{createSuccess}</div>}
      {editSuccess && <div className="state-message state-success">{editSuccess}</div>}
      {passwordSuccess && <div className="state-message state-success">{passwordSuccess}</div>}

      {showCreate && canWrite && (
        <form className="management-panel" onSubmit={handleCreate}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Add User
          </h2>
          <div className="form-grid">
            <label className="form-label">
              Full name
              <input
                className="form-input"
                required
                maxLength={200}
                value={createForm.full_name}
                onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Email
              <input
                className="form-input"
                type="email"
                required
                maxLength={320}
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
              />
            </label>
            <label className="form-label">
              Temporary password (min 8 characters)
              <input
                className="form-input"
                type="password"
                required
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
              />
            </label>
            <label className="form-label">
              Role
              <select
                className="form-input"
                value={createForm.role}
                onChange={(e) => {
                  const role = e.target.value as PlatformRole;
                  setCreateForm({
                    ...createForm,
                    role,
                    tenant_id: CUSTOMER_ROLES.includes(role) ? createForm.tenant_id : "",
                  });
                }}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            {needsTenant && (
              <label className="form-label">
                Customer / tenant
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
            )}
            <label className="form-label">
              Phone (optional)
              <input
                className="form-input"
                maxLength={40}
                value={createForm.phone}
                onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={createForm.status}
                onChange={(e) =>
                  setCreateForm({ ...createForm, status: e.target.value as UserStatus })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {createError && <div className="form-error">{createError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create user"}
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
            Edit {editing.email}
          </h2>
          <p className="page-subtitle" style={{ marginBottom: "12px" }}>
            Email, role, and tenant cannot be changed here (stable at creation). Use status to
            disable access.
          </p>
          <div className="form-grid">
            <label className="form-label">
              Full name
              <input
                className="form-input"
                required
                maxLength={200}
                value={editForm.full_name}
                onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Phone
              <input
                className="form-input"
                maxLength={40}
                value={editForm.phone}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
              />
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={editForm.status}
                onChange={(e) =>
                  setEditForm({ ...editForm, status: e.target.value as UserStatus })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
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

      {passwordUser && canWrite && (
        <form className="management-panel" onSubmit={handlePassword}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Set password for {passwordUser.email}
          </h2>
          <label className="form-label">
            New password (min 8 characters)
            <input
              className="form-input"
              type="password"
              required
              minLength={8}
              maxLength={128}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>
          {passwordError && <div className="form-error">{passwordError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={passwordSaving}>
              {passwordSaving ? "Saving..." : "Set password"}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={passwordSaving}
              onClick={() => {
                setPasswordUser(null);
                setNewPassword("");
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {status === "loading" && <div className="state-message">Loading users...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">
          Access denied. Your account does not have permission to view users.
        </div>
      )}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}

      {status === "success" && data && (
        data.users.length === 0 ? (
          <div className="state-message">No users yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Type</th>
                <th>Customer</th>
                <th>Status</th>
                <th>Last Login</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td>{u.user_type}</td>
                  <td>{tenantLabel(u.tenant_id)}</td>
                  <td>
                    <span className={`badge badge-${u.status}`}>{u.status}</span>
                  </td>
                  <td>{u.last_login_at ?? "Never"}</td>
                  {canWrite && (
                    <td>
                      <div className="confirm-actions" style={{ marginTop: 0 }}>
                        <button className="btn btn-small" type="button" onClick={() => openEdit(u)}>
                          Edit
                        </button>
                        <button
                          className="btn btn-small"
                          type="button"
                          onClick={() => openPassword(u)}
                        >
                          Set password
                        </button>
                      </div>
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
