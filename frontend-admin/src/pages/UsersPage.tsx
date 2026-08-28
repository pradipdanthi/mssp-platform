import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AdminUser,
  PlatformRole,
  Tenant,
  UserStatus,
  createUser,
  enforceUserMfa,
  getTenants,
  getUsers,
  postAuditEvent,
  resetUserMfa,
  updateUser,
  updateUserPassword,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ConfirmDangerModal from "../components/ConfirmDangerModal";
import MfaManageModal from "../components/MfaManageModal";
import FormSection from "../components/FormSection";
import ListToolbar from "../components/ListToolbar";
import RowActionsMenu from "../components/RowActionsMenu";
import { useAdminQuery } from "../hooks/useAdminQuery";

const ROLE_OPTIONS: PlatformRole[] = ["platform_admin", "soc_manager", "soc_analyst"];
const CUSTOMER_ROLES: PlatformRole[] = ["customer_admin", "customer_viewer"];
const STATUS_OPTIONS: UserStatus[] = ["active", "inactive", "locked"];
const STATUS_FILTER_OPTIONS = STATUS_OPTIONS.map((s) => ({ value: s, label: s }));

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
  role: "soc_analyst",
  tenant_id: "",
  phone: "",
  status: "active",
};

export default function UsersPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin";
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
      getUsers({
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    [statusFilter, qFilter, page, pageSize]
  );
  const users = status === "success" && data ? data.users : [];
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? users.length,
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;

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

  const [disableUser, setDisableUser] = useState<AdminUser | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  const [mfaUser, setMfaUser] = useState<AdminUser | null>(null);
  const [mfaEnforceResult, setMfaEnforceResult] = useState<{
    secret: string;
    otpauth_url: string;
  } | null>(null);
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaError, setMfaError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTenants({ page_size: 200 })
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

  function openMfa(u: AdminUser) {
    setMfaUser(u);
    setMfaEnforceResult(null);
    setMfaError(null);
  }

  async function handleMfaReset() {
    if (!canWrite || !mfaUser) return;
    setMfaBusy(true);
    setMfaError(null);
    try {
      const updated = await resetUserMfa(mfaUser.id);
      void postAuditEvent({
        action: "user.mfa_reset",
        entity_type: "user",
        entity_id: updated.id,
        tenant_id: updated.tenant_id,
        details: { email: updated.email },
      }).catch(() => undefined);
      setMfaUser(updated);
      setMfaEnforceResult(null);
      setEditSuccess(`MFA reset for ${updated.email}.`);
      refetch();
    } catch (err) {
      setMfaError(apiErrorMessage(err, "Could not reset MFA."));
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleMfaEnforce() {
    if (!canWrite || !mfaUser) return;
    setMfaBusy(true);
    setMfaError(null);
    try {
      const result = await enforceUserMfa(mfaUser.id);
      void postAuditEvent({
        action: "user.mfa_enforced",
        entity_type: "user",
        entity_id: mfaUser.id,
        tenant_id: mfaUser.tenant_id,
        details: { email: mfaUser.email },
      }).catch(() => undefined);
      setMfaEnforceResult(result);
      setMfaUser({ ...mfaUser, is_mfa_enabled: true });
      refetch();
    } catch (err) {
      setMfaError(apiErrorMessage(err, "Could not enforce MFA."));
    } finally {
      setMfaBusy(false);
    }
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
      void postAuditEvent({
        action: "user.created",
        entity_type: "user",
        entity_id: created.id,
        tenant_id: created.tenant_id,
        details: { after: { email: created.email, role: created.role, status: created.status } },
      }).catch(() => undefined);
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
      void postAuditEvent({
        action: "user.updated",
        entity_type: "user",
        entity_id: updated.id,
        tenant_id: updated.tenant_id,
        details: {
          before: { full_name: editing.full_name, status: editing.status },
          after: { full_name: updated.full_name, status: updated.status },
        },
      }).catch(() => undefined);
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
      void postAuditEvent({
        action: "user.password_reset",
        entity_type: "user",
        entity_id: passwordUser.id,
        tenant_id: passwordUser.tenant_id,
        details: { email: passwordUser.email },
      }).catch(() => undefined);
      setPasswordSuccess(`Password updated for ${passwordUser.email}. Share the new password securely.`);
      setPasswordUser(null);
      setNewPassword("");
    } catch (err) {
      setPasswordError(apiErrorMessage(err, "Could not set password."));
    } finally {
      setPasswordSaving(false);
    }
  }

  async function confirmDisableUser() {
    if (!canWrite || !disableUser) return;
    setActionBusy(true);
    try {
      const updated = await updateUser(disableUser.id, { status: "inactive" });
      void postAuditEvent({
        action: "user.disabled",
        entity_type: "user",
        entity_id: disableUser.id,
        tenant_id: disableUser.tenant_id,
        details: {
          before: { status: disableUser.status },
          after: { status: updated.status },
          email: disableUser.email,
        },
      }).catch(() => undefined);
      setDisableUser(null);
      setEditSuccess(`Access revoked for ${updated.email}.`);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not disable user."));
    } finally {
      setActionBusy(false);
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
            MSSP platform personnel only. Customer portal users are managed under Customers → select
            customer → Users.
          </p>
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

      <ListToolbar
        searchPlaceholder="Search name, email, role…"
        searchValue={qFilter}
        onSearchChange={(q) => patchParams({ q, page: "1" })}
        statusOptions={STATUS_FILTER_OPTIONS}
        statusValue={statusFilter}
        onStatusChange={(status) => patchParams({ status, page: "1" })}
        pageSize={pageSize}
        onPageSizeChange={(size) => patchParams({ page_size: String(size), page: "1" })}
        meta={meta}
        onPageChange={(p) => patchParams({ page: String(p) })}
      />

      <ConfirmDangerModal
        open={!!disableUser}
        title="Revoke access"
        body={
          disableUser
            ? `Disable ${disableUser.full_name} (${disableUser.email})? They will not be able to sign in until reactivated.`
            : ""
        }
        confirmPhrase={disableUser ? `DISABLE ${disableUser.email}` : ""}
        confirmLabel="Disable account"
        onCancel={() => setDisableUser(null)}
        onConfirm={confirmDisableUser}
      />

      {showCreate && canWrite && (
        <form className="kv-onboard-form" onSubmit={handleCreate}>
          <FormSection title="Add User">
            <label className="form-label">
              Full name <span className="req">*</span>
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
              Phone
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
          </FormSection>
          {createError && <div className="form-error">{createError}</div>}
          <div className="kv-form-actions">
            <button
              className="btn btn-ghost"
              type="button"
              disabled={creating}
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </button>
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create User"}
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

      {mfaUser && canWrite && (
        <MfaManageModal
          user={mfaUser}
          enforceResult={mfaEnforceResult}
          busy={mfaBusy}
          error={mfaError}
          onClose={() => {
            setMfaUser(null);
            setMfaEnforceResult(null);
            setMfaError(null);
          }}
          onReset={() => void handleMfaReset()}
          onEnforce={() => void handleMfaEnforce()}
        />
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
        users.length === 0 ? (
          <div className="state-message">No users matching this view.</div>
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
                <th>MFA</th>
                <th>Last Login</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td>{u.user_type}</td>
                  <td>{tenantLabel(u.tenant_id)}</td>
                  <td>
                    <span className={`badge badge-${u.status}`}>{u.status}</span>
                  </td>
                  <td>
                    <span
                      className={`badge ${u.is_mfa_enabled ? "badge-active" : "badge-inactive"}`}
                    >
                      {u.is_mfa_enabled ? "ENABLED" : "DISABLED"}
                    </span>
                  </td>
                  <td>{u.last_login_at ?? "Never"}</td>
                  {canWrite && (
                    <td>
                      <RowActionsMenu
                        actions={[
                          {
                            id: "edit",
                            label: "Edit Details",
                            onClick: () => openEdit(u),
                          },
                          {
                            id: "password",
                            label: "Reset Password",
                            onClick: () => openPassword(u),
                          },
                          {
                            id: "mfa",
                            label: "Manage MFA",
                            onClick: () => openMfa(u),
                          },
                          {
                            id: "disable",
                            label: "Revoke Access / Disable",
                            danger: true,
                            disabled: u.status === "inactive" || actionBusy,
                            onClick: () => setDisableUser(u),
                          },
                        ]}
                      />
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
