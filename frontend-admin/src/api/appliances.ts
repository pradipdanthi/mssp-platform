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

// KB-015 / KB-019: safe metadata only - never token_hash, never raw token.
export interface ActivationTokenMetadata {
  id: string;
  tenant_id: string;
  site_name: string;
  token_hint: string | null;
  status: string;
  expires_at: string | null;
  used_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface ActivationTokensListResponse {
  tokens: ActivationTokenMetadata[];
}

export interface ActivationTokenCreatePayload {
  site_name: string;
  expires_in_hours: number;
}

// Create is the only response that may carry the raw one-time token.
// Caller must keep response.token in local component state only.
export interface ActivationTokenCreateResponse {
  token: string;
  metadata: ActivationTokenMetadata;
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

export function listActivationTokens(tenantId: string): Promise<ActivationTokensListResponse> {
  return request<ActivationTokensListResponse>(
    `/admin/tenants/${tenantId}/appliance-activation-tokens`
  );
}

export function createActivationToken(
  tenantId: string,
  payload: ActivationTokenCreatePayload
): Promise<ActivationTokenCreateResponse> {
  return request<ActivationTokenCreateResponse>(
    `/admin/tenants/${tenantId}/appliance-activation-tokens`,
    {
      method: "POST",
      body: payload,
    }
  );
}

export function revokeActivationToken(tokenId: string): Promise<ActivationTokenMetadata> {
  return request<ActivationTokenMetadata>(`/admin/appliance-activation-tokens/${tokenId}/revoke`, {
    method: "PATCH",
  });
}
