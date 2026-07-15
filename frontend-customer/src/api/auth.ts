import { request } from "./client";

export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  user_type: string;
  role: string;
  tenant_id: string | null;
  tenant_short_code: string | null;
  tenant_name: string | null;
  status: string;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserPublic;
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
