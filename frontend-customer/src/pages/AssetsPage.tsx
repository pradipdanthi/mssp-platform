import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  CustomerProtectedAsset,
  downloadCustomerAgentPackage,
  getCustomerAssets,
  getCustomerLinuxInstallCommand,
} from "../api/customer";
import { useAuth } from "../auth/AuthContext";
import { useCustomerQuery } from "../hooks/useCustomerQuery";
import { ASSET_FOLDERS, AssetFolderId, assetFolderId } from "../utils/assetFolders";

export default function AssetsPage() {
  const { user } = useAuth();
  const shortCode = user?.tenant_short_code ?? null;
  const [pkgBusy, setPkgBusy] = useState(false);
  const [pkgError, setPkgError] = useState<string | null>(null);
  const [linuxCmd, setLinuxCmd] = useState<string | null>(null);
  const [linuxBusy, setLinuxBusy] = useState(false);
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({});
  const { status, data, errorMessage } = useCustomerQuery(
    () => getCustomerAssets(shortCode as string),
    Boolean(shortCode),
    [shortCode]
  );

  useEffect(() => {
    if (!shortCode) return;
    let cancelled = false;
    void getCustomerLinuxInstallCommand(shortCode)
      .then((res) => {
        if (!cancelled) setLinuxCmd(res.one_liner);
      })
      .catch(() => {
        /* optional until package published */
      });
    return () => {
      cancelled = true;
    };
  }, [shortCode]);

  const folders = useMemo(() => {
    const map = ASSET_FOLDERS.reduce(
      (acc, f) => {
        acc[f.id] = [] as CustomerProtectedAsset[];
        return acc;
      },
      {} as Record<AssetFolderId, CustomerProtectedAsset[]>
    );
    for (const asset of data?.assets ?? []) {
      const key = assetFolderId(asset.asset_type, asset.os_name);
      map[key].push(asset);
    }
    return map;
  }, [data?.assets]);

  useEffect(() => {
    setOpenFolders((prev) => {
      const next = { ...prev };
      for (const f of ASSET_FOLDERS) {
        if (folders[f.id].length > 0 && next[f.id] === undefined) next[f.id] = true;
      }
      return next;
    });
  }, [folders]);

  async function handleAgentDownload(osType: "windows" | "linux" | "all") {
    if (!shortCode || pkgBusy) return;
    setPkgBusy(true);
    setPkgError(null);
    try {
      await downloadCustomerAgentPackage(shortCode, osType);
      if (osType === "linux" || osType === "all") {
        try {
          const res = await getCustomerLinuxInstallCommand(shortCode);
          setLinuxCmd(res.one_liner);
        } catch {
          /* ignore */
        }
      }
    } catch (err) {
      const msg =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not download the endpoint agent package.";
      setPkgError(msg);
    } finally {
      setPkgBusy(false);
    }
  }

  async function refreshLinuxCmd() {
    if (!shortCode || linuxBusy) return;
    setLinuxBusy(true);
    setPkgError(null);
    try {
      const res = await getCustomerLinuxInstallCommand(shortCode);
      setLinuxCmd(res.one_liner);
    } catch (err) {
      const msg =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Could not load the Linux install command.";
      setPkgError(msg);
    } finally {
      setLinuxBusy(false);
    }
  }

  if (!shortCode) {
    return (
      <div>
        <h1 className="page-title">Assets</h1>
        <div className="state-message state-error">
          This account is not linked to a customer tenant, so asset posture cannot be loaded.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Assets</h1>
      <p className="page-subtitle">
        Appliance posture, protected assets by device category, and endpoint agent installers for
        your organization.
      </p>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2 className="page-subtitle" style={{ marginTop: 0 }}>
          Install endpoint agent
        </h2>
        <p className="page-subtitle" style={{ marginTop: 0 }}>
          Windows: download and run the installer. Linux (no GUI): copy the one-line command below —
          it pulls your organization&apos;s package from our repository and installs the agent.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          <button
            className="btn btn-primary"
            type="button"
            disabled={pkgBusy}
            onClick={() => void handleAgentDownload("windows")}
          >
            Download Windows package
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            disabled={pkgBusy}
            onClick={() => void handleAgentDownload("linux")}
          >
            Download Linux ZIP (optional)
          </button>
        </div>
        <div style={{ marginTop: "1rem" }}>
          <h3 className="page-subtitle" style={{ marginTop: 0, fontWeight: 600 }}>
            Linux install command
          </h3>
          {linuxCmd ? (
            <pre
              style={{
                margin: 0,
                padding: "0.75rem",
                background: "var(--soc-surface-hover, #18283f)",
                borderRadius: 6,
                overflowX: "auto",
                fontSize: "0.85rem",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {linuxCmd}
            </pre>
          ) : (
            <p className="page-subtitle" style={{ marginTop: 0 }}>
              Click “Show install command” to publish your one-liner.
            </p>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
            <button
              className="btn btn-primary"
              type="button"
              disabled={linuxBusy}
              onClick={() => void refreshLinuxCmd()}
            >
              {linuxBusy ? "Loading…" : "Show install command"}
            </button>
            {linuxCmd && (
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(linuxCmd).catch(() => undefined);
                }}
              >
                Copy command
              </button>
            )}
          </div>
        </div>
        {pkgError && (
          <div className="state-message state-error" style={{ marginTop: "0.75rem" }}>
            {pkgError}
          </div>
        )}
      </section>

      {status === "loading" && <div className="state-message">Loading assets...</div>}
      {status === "forbidden" && (
        <div className="state-message state-error">Access denied for this customer portal view.</div>
      )}
      {(status === "error" || status === "not_found") && (
        <div className="state-message state-error">{errorMessage}</div>
      )}

      {status === "success" && data && (
        <>
          <h2 className="page-subtitle" style={{ marginTop: "1.5rem" }}>
            Appliances
          </h2>
          {data.appliances.length === 0 ? (
            <div className="state-message">No appliances reported for your organization yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Appliance</th>
                  <th>Site</th>
                  <th>Status</th>
                  <th>Health</th>
                  <th>CPU %</th>
                  <th>Memory %</th>
                  <th>Disk %</th>
                  <th>Agent</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {data.appliances.map((row) => (
                  <tr key={row.appliance_id}>
                    <td>
                      <Link to={`/appliances/${encodeURIComponent(row.appliance_id)}`}>
                        {row.appliance_name}
                      </Link>
                    </td>
                    <td>{row.site_name}</td>
                    <td>
                      <span className={`badge badge-${row.status}`}>{row.status}</span>
                    </td>
                    <td>{row.health_status ?? "Unknown"}</td>
                    <td>{row.cpu_percent ?? "—"}</td>
                    <td>{row.memory_percent ?? "—"}</td>
                    <td>{row.disk_percent ?? "—"}</td>
                    <td>{row.agent_version ?? "—"}</td>
                    <td>{row.last_seen_at ?? "Never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="page-subtitle" style={{ marginTop: "2rem" }}>
            Protected assets
          </h2>
          <p className="page-subtitle" style={{ marginTop: 0 }}>
            Browse by category — Windows, Linux, firewalls, switches, load balancers, and more.
          </p>
          <div className="asset-tree">
            {ASSET_FOLDERS.map((folder) => {
              const rows = folders[folder.id];
              const open = !!openFolders[folder.id];
              return (
                <div key={folder.id} className="asset-tree-folder">
                  <button
                    type="button"
                    className="asset-tree-row asset-tree-folder-row"
                    onClick={() =>
                      setOpenFolders((prev) => ({ ...prev, [folder.id]: !prev[folder.id] }))
                    }
                    aria-expanded={open}
                  >
                    <span className="asset-tree-chevron">{open ? "▾" : "▸"}</span>
                    <span className="asset-tree-label">{folder.label}</span>
                    <span className="asset-tree-count">{rows.length}</span>
                  </button>
                  {open && (
                    <div className="asset-tree-folder-body">
                      {rows.length === 0 ? (
                        <div className="asset-folder-empty">No assets in this folder yet.</div>
                      ) : (
                        <table className="data-table asset-folder-table">
                          <thead>
                            <tr>
                              <th>Hostname</th>
                              <th>Type</th>
                              <th>Criticality</th>
                              <th>Status</th>
                              <th>OS</th>
                              <th>Owner</th>
                              <th>Appliance</th>
                              <th>Site</th>
                              <th>Last Seen</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((asset) => (
                              <tr key={asset.asset_id}>
                                <td>
                                  <Link to={`/assets/${encodeURIComponent(asset.asset_id)}`}>
                                    {asset.hostname ?? "—"}
                                  </Link>
                                </td>
                                <td>{asset.asset_type}</td>
                                <td>
                                  <span className={`badge badge-${asset.criticality}`}>
                                    {asset.criticality}
                                  </span>
                                </td>
                                <td>{asset.status}</td>
                                <td>{asset.os_name ?? "—"}</td>
                                <td>{asset.owner ?? "—"}</td>
                                <td>{asset.appliance_name ?? "—"}</td>
                                <td>{asset.site_name ?? "—"}</td>
                                <td>{asset.last_seen_at ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
