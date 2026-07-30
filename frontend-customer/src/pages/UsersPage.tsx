import { FormEvent, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError, request } from "../api/client";
import ConfirmDangerModal from "../components/ConfirmDangerModal";
import ListToolbar from "../components/ListToolbar";
import RowActionsMenu, { RowAction } from "../components/RowActionsMenu";

type CustomerRole = "customer_admin" | "customer_viewer";
type UserStatus = "active" | "inactive" | "locked";

interface TenantUser {
  id: string;
  email: string;
  full_name: string;
  role: CustomerRole;
  status: UserStatus;
  phone?: string | null;
  created_at: string;
}

const STATUS_FILTER_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "locked", label: "Locked" },
];

function errMsg(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  return fallback;
}

function roleLabel(role: CustomerRole): string {
  return role === "customer_admin" ? "Administrator" : "Viewer";
}

function statusLabel(status: UserStatus): string {
  if (status === "active") return "Active";
  if (status === "locked") return "Locked";
  return "Inactive";
}

export default function UsersPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code || "";
  const canWrite = user?.role === "customer_admin";
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

  const [users, setUsers] = useState<TenantUser[]>([]);
  const [meta, setMeta] = useState<{
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "customer_viewer" as CustomerRole,
    phone: "",
  });

  const [editing, setEditing] = useState<TenantUser | null>(null);
  const [editForm, setEditForm] = useState({
    full_name: "",
    phone: "",
    role: "customer_viewer" as CustomerRole,
    status: "active" as UserStatus,
  });

  const [passwordUser, setPasswordUser] = useState<TenantUser | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const [disableUser, setDisableUser] = useState<TenantUser | null>(null);

  const load = useCallback(async () => {
    if (!shortCode) return;
    setError(null);
    try {
      const qs = new URLSearchParams();
      qs.set("page", String(page));
      qs.set("page_size", String(pageSize));
      if (statusFilter) qs.set("status", statusFilter);
      if (qFilter) qs.set("q", qFilter);
      const res = await request<{
        users: TenantUser[];
        total?: number;
        page?: number;
        page_size?: number;
        total_pages?: number;
        has_next?: boolean;
        has_prev?: boolean;
      }>(`/v1/customer/users?${qs.toString()}`);
      setUsers(res.users || []);
      setMeta({
        total: res.total ?? (res.users || []).length,
        page: res.page ?? page,
        page_size: res.page_size ?? pageSize,
        total_pages: res.total_pages ?? 1,
        has_next: Boolean(res.has_next),
        has_prev: Boolean(res.has_prev),
      });
    } catch (e) {
      setError(errMsg(e, "Could not load users"));
    }
  }, [shortCode, page, pageSize, statusFilter, qFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const apiBase = "/v1/customer/users";

  async function patchUser(userId: string, body: Record<string, unknown>) {
    await request(`${apiBase}/${userId}`, { method: "PATCH", body });
    await load();
  }

  function actionsFor(target: TenantUser): RowAction[] {
    if (!canWrite) return [];
    const isSelf = target.id === user?.id;
    const items: RowAction[] = [
      {
        id: "edit",
        label: "Edit profile & role",
        onClick: () => {
          setEditing(target);
          setEditForm({
            full_name: target.full_name,
            phone: target.phone ?? "",
            role: target.role,
            status: target.status,
          });
        },
      },
      {
        id: "password",
        label: "Reset password",
        onClick: () => {
          setPasswordUser(target);
          setNewPassword("");
        },
      },
    ];
    if (target.status === "active") {
      items.push({
        id: "lock",
        label: "Lock account",
        onClick: () => {
          void patchUser(target.id, { status: "locked" }).catch((e) =>
            setError(errMsg(e, "Could not lock user"))
          );
        },
      });
      if (!isSelf) {
        items.push({
          id: "disable",
          label: "Revoke access",
          danger: true,
          onClick: () => setDisableUser(target),
        });
      }
    } else {
      items.push({
        id: "reactivate",
        label: target.status === "locked" ? "Unlock & activate" : "Reactivate",
        onClick: () => {
          void patchUser(target.id, { status: "active" }).catch((e) =>
            setError(errMsg(e, "Could not reactivate user"))
          );
        },
      });
    }
    return items;
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!canWrite || !shortCode) return;
    setBusy(true);
    setError(null);
    try {
      await request(apiBase, {
        method: "POST",
        body: {
          email: form.email.trim(),
          full_name: form.full_name.trim(),
          password: form.password,
          role: form.role,
          phone: form.phone.trim() || null,
        },
      });
      setForm({ email: "", full_name: "", password: "", role: "customer_viewer", phone: "" });
      setShowCreate(false);
      setBanner("User created. Share the temporary password through a secure channel.");
      await load();
    } catch (err) {
      setError(errMsg(err, "Could not create user"));
    } finally {
      setBusy(false);
    }
  }

  async function onEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    try {
      await patchUser(editing.id, {
        full_name: editForm.full_name.trim(),
        phone: editForm.phone.trim() || null,
        role: editForm.role,
        status: editForm.status,
      });
      setBanner(`Saved changes for ${editing.email}.`);
      setEditing(null);
    } catch (err) {
      setError(errMsg(err, "Could not update user"));
    } finally {
      setBusy(false);
    }
  }

  async function onPassword(e: FormEvent) {
    e.preventDefault();
    if (!passwordUser) return;
    setBusy(true);
    try {
      await request(`${apiBase}/${passwordUser.id}/password`, {
        method: "PATCH",
        body: { new_password: newPassword },
      });
      setBanner(`Password updated for ${passwordUser.email}.`);
      setPasswordUser(null);
      setNewPassword("");
    } catch (err) {
      setError(errMsg(err, "Could not set password"));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDisable() {
    if (!disableUser) return;
    await patchUser(disableUser.id, { status: "inactive" });
    setBanner(`Access revoked for ${disableUser.email}.`);
    setDisableUser(null);
  }

  return (
    <div>
      <h1 className="page-title">User Management</h1>
      <p className="page-subtitle">
        {canWrite
          ? "Manage who can access your organization portal. Use strong temporary passwords and revoke access when someone leaves."
          : "Directory of users in your organization (read-only)."}
      </p>

      {banner ? (
        <div className="state-message state-success" style={{ marginBottom: "1rem" }}>
          {banner}
          <button type="button" className="btn btn-ghost" style={{ marginLeft: "0.5rem" }} onClick={() => setBanner(null)}>
            Dismiss
          </button>
        </div>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}

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

      {canWrite ? (
        <div style={{ marginBottom: "1.5rem" }}>
          {!showCreate ? (
            <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
              Add user
            </button>
          ) : (
            <form className="card-surface" onSubmit={onCreate}>
              <h2 className="section-title">Add user</h2>
              <div className="form-grid">
                <label className="form-label">
                  Full name
                  <input
                    className="form-input"
                    required
                    value={form.full_name}
                    onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  />
                </label>
                <label className="form-label">
                  Email
                  <input
                    className="form-input"
                    type="email"
                    required
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                  />
                </label>
                <label className="form-label">
                  Temporary password
                  <input
                    className="form-input"
                    type="password"
                    required
                    minLength={8}
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                  />
                </label>
                <label className="form-label">
                  Role
                  <select
                    className="form-input"
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value as CustomerRole })}
                  >
                    <option value="customer_viewer">Viewer (read-only)</option>
                    <option value="customer_admin">Administrator</option>
                  </select>
                </label>
                <label className="form-label">
                  Phone (optional)
                  <input
                    className="form-input"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  />
                </label>
              </div>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button className="btn btn-primary" type="submit" disabled={busy}>
                  Create user
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      ) : null}

      <div className="card-surface">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              {canWrite ? <th aria-label="Actions" /> : null}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  {u.full_name}
                  {u.id === user?.id ? " (you)" : ""}
                </td>
                <td className="cell-mono">{u.email}</td>
                <td>{roleLabel(u.role)}</td>
                <td>{statusLabel(u.status)}</td>
                {canWrite ? (
                  <td>
                    <RowActionsMenu actions={actionsFor(u)} />
                  </td>
                ) : null}
              </tr>
            ))}
            {users.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 5 : 4} className="muted">
                  No users matching this view.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <ConfirmDangerModal
        open={!!disableUser}
        title="Revoke access"
        body={
          disableUser
            ? `Disable ${disableUser.full_name} (${disableUser.email})? They cannot sign in until an administrator reactivates the account.`
            : ""
        }
        confirmPhrase={disableUser ? `DISABLE ${disableUser.email}` : ""}
        confirmLabel="Disable account"
        onCancel={() => setDisableUser(null)}
        onConfirm={confirmDisable}
      />

      {editing ? (
        <div className="modal-root" role="dialog" aria-modal="true" aria-label="Edit user">
          <button type="button" className="modal-backdrop" aria-label="Cancel" onClick={() => setEditing(null)} />
          <form className="modal-card card-surface" onSubmit={onEdit}>
            <h2 className="modal-title">Edit user</h2>
            <p className="modal-body cell-mono">{editing.email}</p>
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
                  onChange={(e) => setEditForm({ ...editForm, role: e.target.value as CustomerRole })}
                  disabled={editing.id === user?.id}
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
                  onChange={(e) => setEditForm({ ...editForm, status: e.target.value as UserStatus })}
                  disabled={editing.id === user?.id}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="locked">Locked</option>
                </select>
              </label>
            </div>
            {editing.id === user?.id ? (
              <p className="modal-hint">You cannot change your own role or status here. Ask another administrator or MSSP support.</p>
            ) : null}
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(null)} disabled={busy}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                Save
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {passwordUser ? (
        <div className="modal-root" role="dialog" aria-modal="true" aria-label="Reset password">
          <button type="button" className="modal-backdrop" aria-label="Cancel" onClick={() => setPasswordUser(null)} />
          <form className="modal-card card-surface" onSubmit={onPassword}>
            <h2 className="modal-title">Reset password</h2>
            <p className="modal-body">
              New password for <span className="cell-mono">{passwordUser.email}</span> (minimum 8 characters).
            </p>
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
              <button type="button" className="btn btn-ghost" onClick={() => setPasswordUser(null)} disabled={busy}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                Update password
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
