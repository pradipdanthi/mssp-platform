import { request } from "./client";

export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  user_type: string;
  role: string;
  tenant_id: string | null;
  status: string;
  last_login_at: string | null;
  is_mfa_enabled?: boolean;
}

export interface LoginResponse {
  mfa_required: boolean;
  mfa_token?: string | null;
  access_token?: string | null;
  token_type?: string | null;
  expires_in?: number | null;
  user?: UserPublic | null;
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

export function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password, portal: "admin" },
  });
}

export function mfaAuthenticate(mfaToken: string, code: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/mfa/authenticate", {
    method: "POST",
    body: { mfa_token: mfaToken, code },
  });
}

const STAFF_ROLES = new Set(["platform_admin", "soc_manager", "soc_analyst"]);

export function isStaffPortalUser(user: UserPublic | null): boolean {
  return !!user && STAFF_ROLES.has(user.role);
}

export function me(): Promise<UserPublic> {
  return request<UserPublic>("/auth/me");
}

export function roles(): Promise<RolesResponse> {
  return request<RolesResponse>("/auth/roles");
}
