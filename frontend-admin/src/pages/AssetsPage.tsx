import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AdminAsset,
  ASSET_TYPE_LABELS,
  AssetCriticality,
  AssetStatus,
  AssetType,
  Tenant,
  createAsset,
  getAssetDetail,
  getAssets,
  getTenants,
  updateAsset,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ListToolbar from "../components/ListToolbar";
import RowActionsMenu from "../components/RowActionsMenu";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { ASSET_FOLDERS, AssetFolderId, assetFolderId } from "../utils/assetFolders";

const TYPES: AssetType[] = [
  "server",
  "workstation",
  "firewall",
  "switch",
  "load_balancer",
  "network_device",
  "application",
  "database",
  "other",
];
const CRITICALITIES: AssetCriticality[] = ["low", "medium", "high", "critical"];
const STATUSES: AssetStatus[] = ["active", "inactive", "unknown"];
const STATUS_OPTIONS = STATUSES.map((s) => ({ value: s, label: s }));

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  if (err instanceof ApiError && err.status === 403) return "Access denied for this action.";
  return fallback;
}

type CustomerBucket = {
  key: string;
  name: string;
  shortCode: string;
  folders: Record<AssetFolderId, AdminAsset[]>;
  total: number;
};

function emptyFolders(): Record<AssetFolderId, AdminAsset[]> {
  return ASSET_FOLDERS.reduce(
    (acc, f) => {
      acc[f.id] = [];
      return acc;
    },
    {} as Record<AssetFolderId, AdminAsset[]>
  );
}

export default function AssetsPage() {
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
      getAssets({
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(qFilter ? { q: qFilter } : {}),
      }),
    [statusFilter, qFilter, page, pageSize]
  );
  const meta =
    status === "success" && data
      ? {
          total: data.total ?? (data.assets?.length ?? 0),
          page: data.page ?? page,
          page_size: data.page_size ?? pageSize,
          total_pages: data.total_pages ?? 1,
          has_next: Boolean(data.has_next),
          has_prev: Boolean(data.has_prev),
        }
      : null;
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [tenantId, setTenantId] = useState("");
  const [hostname, setHostname] = useState("");
  const [assetType, setAssetType] = useState<AssetType>("server");
  const [criticality, setCriticality] = useState<AssetCriticality>("medium");
  const [assetStatus, setAssetStatus] = useState<AssetStatus>("active");
  const [osName, setOsName] = useState("");
  const [owner, setOwner] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [editing, setEditing] = useState<AdminAsset | null>(null);
  const [editHostname, setEditHostname] = useState("");
  const [editType, setEditType] = useState<AssetType>("server");
  const [editCriticality, setEditCriticality] = useState<AssetCriticality>("medium");
  const [editStatus, setEditStatus] = useState<AssetStatus>("active");
  const [editOs, setEditOs] = useState("");
  const [editOwner, setEditOwner] = useState("");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [openCustomers, setOpenCustomers] = useState<Record<string, boolean>>({});
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({});

  useEffect(() => {
    getTenants({ page_size: 200 })
      .then((r) => setTenants(r.tenants))
      .catch(() => undefined);
  }, []);

  const customerBuckets = useMemo(() => {
    const map = new Map<string, CustomerBucket>();

    for (const row of data?.assets ?? []) {
      const key = row.short_code;
      let bucket = map.get(key);
      if (!bucket) {
        bucket = {
          key,
          name: row.tenant_name,
          shortCode: row.short_code,
          folders: emptyFolders(),
          total: 0,
        };
        map.set(key, bucket);
      }
      const folder = assetFolderId(row.asset_type, row.os_name);
      bucket.folders[folder].push(row);
      bucket.total += 1;
    }

    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [data?.assets]);

  useEffect(() => {
    // Auto-expand customers that already have assets (once per load).
    setOpenCustomers((prev) => {
      const next = { ...prev };
      for (const c of customerBuckets) {
        if (c.total > 0 && next[c.key] === undefined) next[c.key] = true;
      }
      return next;
    });
    setOpenFolders((prev) => {
      const next = { ...prev };
      for (const c of customerBuckets) {
        for (const f of ASSET_FOLDERS) {
          const fk = `${c.key}::${f.id}`;
          if (c.folders[f.id].length > 0 && next[fk] === undefined) next[fk] = true;
        }
      }
      return next;
    });
  }, [customerBuckets]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!canWrite) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createAsset({
        tenant_id: tenantId,
        hostname: hostname.trim() || null,
        asset_type: assetType,
        criticality,
        status: assetStatus,
        os_name: osName.trim() || null,
        owner: owner.trim() || null,
      });
      setSuccess(`Asset created for ${created.short_code}: ${created.hostname ?? created.id}`);
      setShowCreate(false);
      setHostname("");
      setOsName("");
      setOwner("");
      refetch();
    } catch (err) {
      setCreateError(apiErrorMessage(err, "Could not create asset."));
    } finally {
      setCreating(false);
    }
  }

  async function openEdit(row: AdminAsset) {
    setEditing(row);
    setEditError(null);
    try {
      const detail = await getAssetDetail(row.id);
      setEditHostname(detail.hostname ?? "");
      setEditType(detail.asset_type as AssetType);
      setEditCriticality(detail.criticality as AssetCriticality);
      setEditStatus(detail.status as AssetStatus);
      setEditOs(detail.os_name ?? "");
      setEditOwner(detail.owner ?? "");
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not load asset."));
    }
  }

  async function handleEdit(e: FormEvent) {
    e.preventDefault();
    if (!canWrite || !editing) return;
    setSaving(true);
    setEditError(null);
    try {
      await updateAsset(editing.id, {
        hostname: editHostname.trim() || null,
        asset_type: editType,
        criticality: editCriticality,
        status: editStatus,
        os_name: editOs.trim() || null,
        owner: editOwner.trim() || null,
      });
      setSuccess("Asset updated.");
      setEditing(null);
      refetch();
    } catch (err) {
      setEditError(apiErrorMessage(err, "Could not update asset."));
    } finally {
      setSaving(false);
    }
  }

  function toggleCustomer(key: string) {
    setOpenCustomers((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function toggleFolder(customerKey: string, folderId: AssetFolderId) {
    const fk = `${customerKey}::${folderId}`;
    setOpenFolders((prev) => ({ ...prev, [fk]: !prev[fk] }));
  }

  function renderAssetTable(rows: AdminAsset[]) {
    if (rows.length === 0) {
      return <div className="asset-folder-empty">No assets in this folder yet.</div>;
    }
    return (
      <table className="data-table asset-folder-table">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>IP</th>
            <th>Type</th>
            <th>OS</th>
            <th>Criticality</th>
            <th>Status</th>
            <th>Appliance</th>
            <th>Last seen</th>
            {canWrite && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.hostname ?? "—"}</td>
              <td>{row.ip_address ?? "—"}</td>
              <td>{ASSET_TYPE_LABELS[row.asset_type as AssetType] ?? row.asset_type}</td>
              <td>{row.os_name ?? "—"}</td>
              <td>{row.criticality}</td>
              <td>
                <span className={`badge badge-${row.status}`}>{row.status}</span>
              </td>
              <td>{row.appliance_name ?? "—"}</td>
              <td>{row.last_seen_at ?? "—"}</td>
              {canWrite && (
                <td>
                  <RowActionsMenu
                    actions={[
                      {
                        id: "edit",
                        label: "Edit asset",
                        onClick: () => openEdit(row),
                      },
                      {
                        id: "deactivate",
                        label: "Set inactive",
                        danger: true,
                        disabled: row.status === "inactive",
                        onClick: async () => {
                          try {
                            await updateAsset(row.id, { status: "inactive" });
                            setSuccess(`Asset ${row.hostname ?? row.id} set inactive.`);
                            refetch();
                          } catch (err) {
                            setCreateError(apiErrorMessage(err, "Could not update asset."));
                          }
                        },
                      },
                    ]}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Protected Assets</h1>
          <p className="page-subtitle">
            Customer folders with OS and device-type categories. New assets land in the matching
            folder automatically. IP addresses are SOC-visible only.
          </p>
        </div>
        {canWrite && (
          <button className="btn btn-primary" type="button" onClick={() => setShowCreate(true)}>
            Add Asset
          </button>
        )}
      </div>

      {!canWrite && (
        <div className="state-message" style={{ marginBottom: "1rem" }}>
          View-only. Creating/editing requires platform_admin or soc_manager.
        </div>
      )}
      {success && <div className="state-message state-success">{success}</div>}

      <ListToolbar
        searchPlaceholder="Search hostname, OS, tenant, IP…"
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
            Add Asset
          </h2>
          <p className="page-subtitle" style={{ marginTop: 0 }}>
            Choose the device type carefully — firewalls, switches, and load balancers go into their
            own folders. For servers/workstations, set the OS so the asset sits under Windows /
            Linux / macOS.
          </p>
          <div className="form-grid">
            <label className="form-label">
              Customer
              <select
                className="form-input"
                required
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
              >
                <option value="">Select…</option>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.short_code})
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Hostname
              <input
                className="form-input"
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
              />
            </label>
            <label className="form-label">
              Type
              <select
                className="form-input"
                value={assetType}
                onChange={(e) => setAssetType(e.target.value as AssetType)}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {ASSET_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Criticality
              <select
                className="form-input"
                value={criticality}
                onChange={(e) => setCriticality(e.target.value as AssetCriticality)}
              >
                {CRITICALITIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={assetStatus}
                onChange={(e) => setAssetStatus(e.target.value as AssetStatus)}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              OS
              <input className="form-input" value={osName} onChange={(e) => setOsName(e.target.value)} placeholder="e.g. Windows Server 2022" />
            </label>
            <label className="form-label">
              Owner
              <input className="form-input" value={owner} onChange={(e) => setOwner(e.target.value)} />
            </label>
          </div>
          {createError && <div className="form-error">{createError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create asset"}
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {editing && canWrite && (
        <form className="management-panel" onSubmit={handleEdit}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Edit Asset
          </h2>
          <div className="form-grid">
            <label className="form-label">
              Hostname
              <input
                className="form-input"
                value={editHostname}
                onChange={(e) => setEditHostname(e.target.value)}
              />
            </label>
            <label className="form-label">
              Type
              <select
                className="form-input"
                value={editType}
                onChange={(e) => setEditType(e.target.value as AssetType)}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {ASSET_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Criticality
              <select
                className="form-input"
                value={editCriticality}
                onChange={(e) => setEditCriticality(e.target.value as AssetCriticality)}
              >
                {CRITICALITIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              Status
              <select
                className="form-input"
                value={editStatus}
                onChange={(e) => setEditStatus(e.target.value as AssetStatus)}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-label">
              OS
              <input className="form-input" value={editOs} onChange={(e) => setEditOs(e.target.value)} />
            </label>
            <label className="form-label">
              Owner
              <input
                className="form-input"
                value={editOwner}
                onChange={(e) => setEditOwner(e.target.value)}
              />
            </label>
          </div>
          {editError && <div className="form-error">{editError}</div>}
          <div className="confirm-actions">
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {status === "loading" && <div className="state-message">Loading assets...</div>}
      {status === "forbidden" && <div className="state-message state-error">Access denied.</div>}
      {status === "error" && <div className="state-message state-error">{errorMessage}</div>}
      {status === "success" && (
        customerBuckets.length === 0 ? (
          <div className="state-message">No assets matching this view.</div>
        ) : (
          <div className="asset-tree">
            {customerBuckets.map((customer) => {
              const customerOpen = !!openCustomers[customer.key];
              return (
                <div key={customer.key} className="asset-tree-customer">
                  <button
                    type="button"
                    className="asset-tree-row asset-tree-customer-row"
                    onClick={() => toggleCustomer(customer.key)}
                    aria-expanded={customerOpen}
                  >
                    <span className="asset-tree-chevron">{customerOpen ? "▾" : "▸"}</span>
                    <span className="asset-tree-label">
                      {customer.name}{" "}
                      <span className="asset-tree-meta">({customer.shortCode})</span>
                    </span>
                    <span className="asset-tree-count">{customer.total}</span>
                  </button>
                  {customerOpen && (
                    <div className="asset-tree-children">
                      {ASSET_FOLDERS.map((folder) => {
                        const fk = `${customer.key}::${folder.id}`;
                        const folderOpen = !!openFolders[fk];
                        const rows = customer.folders[folder.id];
                        return (
                          <div key={folder.id} className="asset-tree-folder">
                            <button
                              type="button"
                              className="asset-tree-row asset-tree-folder-row"
                              onClick={() => toggleFolder(customer.key, folder.id)}
                              aria-expanded={folderOpen}
                            >
                              <span className="asset-tree-chevron">{folderOpen ? "▾" : "▸"}</span>
                              <span className="asset-tree-label">{folder.label}</span>
                              <span className="asset-tree-count">{rows.length}</span>
                            </button>
                            {folderOpen && (
                              <div className="asset-tree-folder-body">{renderAssetTable(rows)}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}
