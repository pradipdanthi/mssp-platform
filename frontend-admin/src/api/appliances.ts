import { request } from "./client";

// Mirrors backend-api/app/schemas/appliances.py ApplianceCredentialMetadata
// and ApplianceCredentialRotateResponse (KB-017) exactly. Neither type has
// an appliance_api_key_hash field, matching the backend - the hash is
// never returned by any endpoint.
export interface ApplianceCredentialMetadata {
  appliance_id: string;
  has_appliance_api_key: boolean;
  appliance_api_key_hint: string | null;
  appliance_key_created_at: string | null;
  appliance_key_last_used_at: string | null;
  status: string;
  last_seen_at: string | null;
}

export interface ApplianceCredentialRotateResponse {
  appliance_id: string;
  appliance_api_key: string;
  api_key_hint: string;
  appliance_key_created_at: string;
  message: string;
}

export function getApplianceCredential(applianceId: string): Promise<ApplianceCredentialMetadata> {
  return request<ApplianceCredentialMetadata>(`/admin/appliances/${applianceId}/credential`);
}

// Caller is responsible for keeping the raw appliance_api_key in this
// response in local component state only - never in sessionStorage,
// localStorage, or a console.log call. See AppliancesPage.tsx.
export function rotateApplianceCredential(applianceId: string): Promise<ApplianceCredentialRotateResponse> {
  return request<ApplianceCredentialRotateResponse>(`/admin/appliances/${applianceId}/credential/rotate`, {
    method: "POST",
  });
}
