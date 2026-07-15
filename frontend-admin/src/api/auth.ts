import { request } from "./client";

// Mirrors backend-api/app/schemas/auth.py exactly (do not add fields here
// that the backend does not return - e.g. no password/password_hash).
export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  user_type: string;
  role: string;
  tenant_id: string | null;
  status: string;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
}

export interface RoleInfo {
  role: string;
  user_type: string;
  cross_tenant: boolean;
  description: string;
}

export interface RolesResponse {
  roles: RoleInfo[];
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function me(): Promise<UserPublic> {
  return request<UserPublic>("/auth/me");
}

export function roles(): Promise<RolesResponse> {
  return request<RolesResponse>("/auth/roles");
}
