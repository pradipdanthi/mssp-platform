import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  AdminUser,
  Tenant,
  createTenantCustomerUser,
  enforceUserMfa,
  getTenantUsers,
  postAuditEvent,
  resetUserMfa,
  updateTenantCustomerUser,
  updateTenantCustomerUserPassword,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ConfirmDangerModal from "./ConfirmDangerModal";
import MfaManageModal from "./MfaManageModal";
import RowActionsMenu, { RowAction } from "./RowActionsMenu";

type CustomerRole = "customer_admin" | "customer_viewer";
type UserStatus = "active" | "inactive" | "locked";

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.status === 409) return "A user with this email already exists.";
  }
  return fallback;
}

function roleLabel(role: string): string {
  return role === "customer_admin" ? "Administrator" : "Viewer";
}

function rowActionsForUser(
  u: AdminUser,
  tenantId: string,
  handlers: {
    openEdit: (user: AdminUser) => void;
    openPassword: (user: AdminUser) => void;
    openMfa?: (user: AdminUser) => void;
    requestDisable: (user: AdminUser) => void;
    reload: () => void;
    setError: (msg: string) => void;
  }
): RowAction[] {
  const actions: RowAction[] = [
    { id: "edit", label: "Edit profile & role", onClick: () => handlers.openEdit(u) },
    {
      id: "password",
      label: "Reset password",
      onClick: () => handlers.openPassword(u),
    },
  ];
  if (handlers.openMfa) {
    actions.push({
      id: "mfa",
      label: "Manage MFA",
      onClick: () => handlers.openMfa!(u),
    });
  }
  if (u.status === "active") {
    actions.push({
      id: "lock",
      label: "Lock account",
      onClick: () => {
        void updateTenantCustomerUser(tenantId, u.id, { status: "locked" })
          .then(() => handlers.reload())
          .catch((err) => handlers.setError(apiErrorMessage(err, "Could not lock user.")));
      },
    });
    actions.push({
      id: "disable",
      label: "Revoke access",
      danger: true,
      onClick: () => handlers.requestDisable(u),
    });
  } else {
    actions.push({
      id: "reactivate",
      label: u.status === "locked" ? "Unlock & activate" : "Reactivate",
      onClick: () => {
        void updateTenantCustomerUser(tenantId, u.id, { status: "active" })
          .then(() => handlers.reload())
          .catch((err) => handlers.setError(apiErrorMessage(err, "Could not reactivate user.")));
      },
    });
  }
  return actions;
}

type Props = {
  tenant: Tenant;
  canWrite: boolean;
  onClose: () => void;
};

export default function TenantCustomerUsersPanel({ tenant, canWrite, onClose }: Props) {
  const { user: currentUser } = useAuth();
  const canManageMfa = currentUser?.role === "platform_admin";
  const panelRef = useRef<HTMLDivElement>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "customer_viewer" as CustomerRole,
    phone: "",
  });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState({
    full_name: "",
    phone: "",
    role: "customer_viewer" as CustomerRole,
    status: "active" as UserStatus,
  });
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [passwordUser, setPasswordUser] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const [disableUser, setDisableUser] = useState<AdminUser | null>(null);

  const [mfaUser, setMfaUser] = useState<AdminUser | null>(null);
  const [mfaEnforceResult, setMfaEnforceResult] = useState<{
    secret: string;
    otpauth_url: string;
  } | null>(null);
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaError, setMfaError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const res = await getTenantUsers(tenant.id);
      setUsers(res.users || []);
    } catch (err) {
      setLoadError(apiErrorMessage(err, "Could not load customer users."));
    }
  }, [tenant.id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  function openEdit(u: AdminUser) {
    setEditing(u);
    setEditForm({
      full_name: u.full_name,
      phone: u.phone ?? "",
      role: (u.role as CustomerRole) || "customer_viewer",
      status: (u.status as UserStatus) || "active",
    });
    setEditError(null);
  }

  function openPassword(u: AdminUser) {
    setPasswordUser(u);
    setNewPassword("");
    setPasswordError(null);
  }

  function openMfa(u: AdminUser) {
    setMfaUser(u);
    setMfaEnforceResult(null);
    setMfaError(null);
  }

  async function handleMfaReset() {
    if (!canManageMfa || !mfaUser) return;
    setMfaBusy(true);
    setMfaError(null);
    try {
      const updated = await resetUserMfa(mfaUser.id);
      void postAuditEvent({
        action: "tenant_user.mfa_reset",
        entity_type: "user",
        entity_id: updated.id,
        tenant_id: tenant.id,
        details: { email: updated.email },
      }).catch(() => undefined);
      setMfaUser(updated);
      setMfaEnforceResult(null);
      setBanner(`MFA reset for ${updated.email}.`);
      await load();
    } catch (err) {
      setMfaError(apiErrorMessage(err, "Could not reset MFA."));
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleMfaEnforce() {
    if (!canManageMfa || !mfaUser) return;
    setMfaBusy(true);
    setMfaError(null);
    try {
      const result = await enforceUserMfa(mfaUser.id);
      void postAuditEvent({
        action: "tenant_user.mfa_enforced",
        entity_type: "user",
        entity_id: mfaUser.id,
        tenant_id: tenant.id,
        details: { email: mfaUser.email },
      }).catch(() => undefined);
      setMfaEnforceResult(result);
      setMfaUser({ ...mfaUser, is_mfa_enabled: true });
      await load();
    } catch (err) {
      setMfaError(apiErrorMessage(err, "Could not enforce MFA."));
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!canWrite) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createTenantCustomerUser(tenant.id, {
        email: createForm.email.trim(),
        full_name: createForm.full_name.trim(),
        password: createForm.password,
        role: createForm.role,
        phone: createForm.phone.trim() || null,
      });
      void postAuditEvent({
        action: "tenant_user.created",
        entity_type: "user",
        entity_id: created.id,
        tenant_id: tenant.id,
        details: { email: created.email, role: created.role },
      }).catch(() => undefined);
      setBanner(`Created ${created.full_name}. Share the temporary password securely.`);
      setCreateForm({
        email: "",
        full_name: "",
        password: "",
        role: "customer_viewer",
        phone: "",
      });
      setShowCreate(false);
      await load();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create user."));
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(e: FormEvent) {
    e.preventDefault();
    if (!canWrite || !editing) return;
    setSaving(true);
    setEditError(null);
    try {
      const updated = await updateTenantCustomerUser(tenant.id, editing.id, {
        full_name: editForm.full_name.trim(),
        phone: editForm.phone.trim() || null,
        role: editForm.role,
        status: editForm.status,
      });
      void postAuditEvent({
        action: "tenant_user.updated",
        entity_type: "user",
        entity_id: updated.id,
        tenant_id: tenant.id,
        details: {
          before: { role: editing.role, status: editing.status },
          after: { role: updated.role, status: updated.status },
        },
      }).catch(() => undefined);
      setBanner(`Saved changes for ${updated.email}.`);
      setEditing(null);
      await load();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update user."));
    } finally {
      setSaving(false);
    }
  }

  async function handlePassword(e: FormEvent) {
    e.preventDefault();
    if (!canWrite || !passwordUser) return;
    setPasswordSaving(true);
    setPasswordError(null);
    try {
      await updateTenantCustomerUserPassword(tenant.id, passwordUser.id, {
        new_password: newPassword,
      });
      void postAuditEvent({
        action: "tenant_user.password_reset",
        entity_type: "user",
        entity_id: passwordUser.id,
        tenant_id: tenant.id,
        details: { email: passwordUser.email },
      }).catch(() => undefined);
      setBanner(`Password reset for ${passwordUser.email}.`);
      setPasswordUser(null);
      setNewPassword("");
    } catch (err) {
      setPasswordError(apiErrorMessage(err, "Could not set password."));
    } finally {
      setPasswordSaving(false);
    }
  }

  async function confirmDisable() {
    if (!canWrite || !disableUser) return;
    await updateTenantCustomerUser(tenant.id, disableUser.id, { status: "inactive" });
    setBanner(`Access revoked for ${disableUser.email}.`);
    setDisableUser(null);
    await load();
  }

  const actionHandlers = {
    openEdit,
    openPassword,
    ...(canManageMfa ? { openMfa } : {}),
    requestDisable: setDisableUser,
    reload: () => void load(),
    setError: (msg: string) => setLoadError(msg),
  };

  return (
    <div
      ref={panelRef}
      className="card-surface tenant-customer-users-panel"
      style={{ marginBottom: "1rem", padding: "1rem", border: "1px solid #00aeef" }}
    >
      <div className="page-header-row" style={{ marginBottom: "0.75rem" }}>
        <div>
          <h2 className="page-title" style={{ fontSize: "1.05rem", margin: 0 }}>
            Customer users — {tenant.name} ({tenant.short_code})
          </h2>
          <p className="page-subtitle" style={{ margin: "0.35rem 0 0" }}>
            Create portal logins, reset passwords, change roles, and revoke access. Accounts are
            deactivated instead of deleted (audit trail).
          </p>
        </div>
        <button className="btn btn-ghost" type="button" onClick={onClose}>
          Close
        </button>
      </div>

      {banner ? (
        <div className="state-message state-success" style={{ marginBottom: "0.75rem" }}>
          {banner}
          <button
            type="button"
            className="btn btn-ghost"
            style={{ marginLeft: "0.5rem" }}
            onClick={() => setBanner(null)}
          >
            Dismiss
          </button>
        </div>
      ) : null}
      {loadError ? <p className="form-error">{loadError}</p> : null}

      {canWrite ? (
        <div style={{ marginBottom: "0.75rem" }}>
          {!showCreate ? (
            <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
              Add user
            </button>
          ) : (
            <form className="management-panel" onSubmit={handleCreate}>
              <h3 className="section-title" style={{ marginTop: 0 }}>
                New customer user
              </h3>
              {createError ? <p className="form-error">{createError}</p> : null}
              <div className="form-grid">
                <label className="form-label">
                  Full name
                  <input
                    className="form-input"
                    required
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
                    value={createForm.email}
                    onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                  />
                </label>
                <label className="form-label">
                  Temporary password
                  <input
                    className="form-input"
                    type="password"
                    required
                    minLength={8}
                    value={createForm.password}
                    onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                  />
                </label>
                <label className="form-label">
                  Role
                  <select
                    className="form-input"
                    value={createForm.role}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, role: e.target.value as CustomerRole })
                    }
                  >
                    <option value="customer_viewer">Viewer (read-only)</option>
                    <option value="customer_admin">Administrator</option>
                  </select>
                </label>
                <label className="form-label">
                  Phone (optional)
                  <input
                    className="form-input"
                    value={createForm.phone}
                    onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
                  />
                </label>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button className="btn btn-primary" type="submit" disabled={creating}>
                  {creating ? "Creating…" : "Create user"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setShowCreate(false);
                    setCreateError(null);
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          View only. Managing customer users requires platform_admin or soc_manager.
        </p>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>MFA</th>
            {canWrite ? <th aria-label="Actions" /> : null}
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.full_name}</td>
              <td className="cell-mono">{u.email}</td>
              <td>{roleLabel(u.role)}</td>
              <td>{u.status}</td>
              <td>
                <span
                  className={`badge ${u.is_mfa_enabled ? "badge-active" : "badge-inactive"}`}
                >
                  {u.is_mfa_enabled ? "ENABLED" : "DISABLED"}
                </span>
              </td>
              {canWrite ? (
                <td>
                  <RowActionsMenu actions={rowActionsForUser(u, tenant.id, actionHandlers)} />
                </td>
              ) : null}
            </tr>
          ))}
          {users.length === 0 ? (
            <tr>
              <td colSpan={canWrite ? 6 : 5} className="muted">
                No customer users for this tenant.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>

      <ConfirmDangerModal
        open={!!disableUser}
        title="Revoke customer access"
        body={
          disableUser
            ? `Disable ${disableUser.full_name} (${disableUser.email})? They cannot sign in until reactivated.`
            : ""
        }
        confirmPhrase={disableUser ? `DISABLE ${disableUser.email}` : ""}
        confirmLabel="Disable account"
        onCancel={() => setDisableUser(null)}
        onConfirm={confirmDisable}
      />

      {mfaUser && canManageMfa ? (
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
      ) : null}

      {editing && canWrite ? (
        <div className="modal-root" role="dialog" aria-modal="true" aria-label="Edit user">
          <button type="button" className="modal-backdrop" aria-label="Cancel" onClick={() => setEditing(null)} />
          <form className="modal-card card-surface" onSubmit={handleEdit}>
            <h2 className="modal-title">Edit user</h2>
            <p className="modal-body cell-mono">{editing.email}</p>
            {editError ? <p className="form-error">{editError}</p> : null}
            <div className="form-grid">
              <label className="form-label">
                Full name
                <input
                  className="form-input"
                  required
                  value={editForm.full_name}
                  onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                />
              </label>
              <label className="form-label">
                Phone
                <input
                  className="form-input"
                  value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                />
              </label>
              <label className="form-label">
                Role
                <select
                  className="form-input"
                  value={editForm.role}
                  onChange={(e) =>
                    setEditForm({ ...editForm, role: e.target.value as CustomerRole })
                  }
                >
                  <option value="customer_viewer">Viewer</option>
                  <option value="customer_admin">Administrator</option>
                </select>
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
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="locked">Locked</option>
                </select>
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(null)} disabled={saving}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {passwordUser && canWrite ? (
        <div className="modal-root" role="dialog" aria-modal="true" aria-label="Reset password">
          <button
            type="button"
            className="modal-backdrop"
            aria-label="Cancel"
            onClick={() => setPasswordUser(null)}
          />
          <form className="modal-card card-surface" onSubmit={handlePassword}>
            <h2 className="modal-title">Reset password</h2>
            <p className="modal-body">
              Set a new password for <span className="cell-mono">{passwordUser.email}</span>.
            </p>
            {passwordError ? <p className="form-error">{passwordError}</p> : null}
            <label className="form-label">
              New password
              <input
                className="form-input"
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoFocus
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setPasswordUser(null)} disabled={passwordSaving}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={passwordSaving}>
                {passwordSaving ? "Saving…" : "Update password"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
