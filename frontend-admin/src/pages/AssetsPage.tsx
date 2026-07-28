import { FormEvent, useEffect, useState } from "react";
import {
  AdminAsset,
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
import RowActionsMenu from "../components/RowActionsMenu";
import { useAdminQuery } from "../hooks/useAdminQuery";

const TYPES: AssetType[] = [
  "server",
  "workstation",
  "firewall",
  "network_device",
  "application",
  "database",
  "other",
];
const CRITICALITIES: AssetCriticality[] = ["low", "medium", "high", "critical"];
const STATUSES: AssetStatus[] = ["active", "inactive", "unknown"];

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.detail === "string") return err.detail;
  if (err instanceof ApiError && err.status === 403) return "Access denied for this action.";
  return fallback;
}

export default function AssetsPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "platform_admin" || user?.role === "soc_manager";
  const { status, data, errorMessage, refetch } = useAdminQuery(() => getAssets(), []);
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

  useEffect(() => {
    getTenants()
      .then((r) => setTenants(r.tenants))
      .catch(() => undefined);
  }, []);

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

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">Protected Assets</h1>
          <p className="page-subtitle">
            Inventory of customer assets the SOC is protecting. IP addresses are SOC-visible only.
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

      {showCreate && canWrite && (
        <form className="management-panel" onSubmit={handleCreate}>
          <h2 className="section-title" style={{ marginTop: 0 }}>
            Add Asset
          </h2>
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
                    {t}
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
              <input className="form-input" value={osName} onChange={(e) => setOsName(e.target.value)} />
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
                    {t}
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
      {status === "success" && data && (
        data.assets.length === 0 ? (
          <div className="state-message">No protected assets yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Hostname</th>
                <th>IP</th>
                <th>Type</th>
                <th>Criticality</th>
                <th>Status</th>
                <th>Appliance</th>
                <th>Last seen</th>
                {canWrite && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data.assets.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.tenant_name} ({row.short_code})
                  </td>
                  <td>{row.hostname ?? "—"}</td>
                  <td>{row.ip_address ?? "—"}</td>
                  <td>{row.asset_type}</td>
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
        )
      )}
    </div>
  );
}
