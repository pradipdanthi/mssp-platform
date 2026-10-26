import { request } from "./client";

export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  user_type: string;
  role: string;
  tenant_id: string | null;
  status: string;
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

const STAFF = new Set(["platform_admin", "soc_manager", "soc_analyst"]);

export function isStaff(user: UserPublic | null): boolean {
  return !!user && STAFF.has(user.role);
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return request("/auth/login", {
    method: "POST",
    body: { email, password, portal: "admin" },
  });
}

export function mfaAuthenticate(mfaToken: string, code: string): Promise<TokenResponse> {
  return request("/auth/mfa/authenticate", {
    method: "POST",
    body: { mfa_token: mfaToken, code },
  });
}

export function me(): Promise<UserPublic> {
  return request("/auth/me");
}
