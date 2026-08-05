/** Appliance Management / channel gateway (KB-093L). Lab default = VM 114. */
export const APPLIANCE_GATEWAY_URL =
  (typeof import.meta !== "undefined" &&
    (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_APPLIANCE_GATEWAY_URL) ||
  "http://192.168.0.224:8000";

export function applianceRegisterCommand(token: string): string {
  return `junexis-cli register --token '${token}' --control-plane ${APPLIANCE_GATEWAY_URL}`;
}
