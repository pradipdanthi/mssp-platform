/** Shared folder taxonomy for Assets navigation (customer → category). */

export type AssetFolderId =
  | "windows"
  | "linux"
  | "macos"
  | "firewall"
  | "switch"
  | "load_balancer"
  | "network_device"
  | "application"
  | "database"
  | "other";

export interface AssetFolderDef {
  id: AssetFolderId;
  label: string;
}

/** Stable folder order for SOC / customer navigation. */
export const ASSET_FOLDERS: AssetFolderDef[] = [
  { id: "windows", label: "Windows" },
  { id: "linux", label: "Linux" },
  { id: "macos", label: "macOS" },
  { id: "firewall", label: "Firewalls" },
  { id: "switch", label: "Switches" },
  { id: "load_balancer", label: "Load balancers" },
  { id: "network_device", label: "Network devices" },
  { id: "application", label: "Applications" },
  { id: "database", label: "Databases" },
  { id: "other", label: "Other" },
];

const NETWORK_TYPES = new Set([
  "firewall",
  "switch",
  "load_balancer",
  "network_device",
  "application",
  "database",
]);

export function assetFolderId(assetType: string | null | undefined, osName: string | null | undefined): AssetFolderId {
  const type = (assetType || "other").toLowerCase();
  if (NETWORK_TYPES.has(type)) {
    return type as AssetFolderId;
  }

  const os = (osName || "").toLowerCase();
  if (os.includes("windows")) return "windows";
  if (os.includes("mac") || os.includes("darwin")) return "macos";
  if (
    os.includes("linux") ||
    os.includes("ubuntu") ||
    os.includes("debian") ||
    os.includes("centos") ||
    os.includes("rhel") ||
    os.includes("red hat") ||
    os.includes("redhat") ||
    os.includes("suse") ||
    os.includes("amazon")
  ) {
    return "linux";
  }

  if (type === "other") return "other";
  // server/workstation without a clear OS still go to Other until OS is set.
  return "other";
}

export function folderLabel(id: AssetFolderId): string {
  return ASSET_FOLDERS.find((f) => f.id === id)?.label ?? id;
}
