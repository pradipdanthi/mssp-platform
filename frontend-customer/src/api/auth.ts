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
  phone: string | null;
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

export interface ProfileUpdatePayload {
  full_name?: string;
  phone?: string | null;
}

export function updateMyProfile(payload: ProfileUpdatePayload): Promise<UserPublic> {
  return request<UserPublic>("/auth/me", {
    method: "PATCH",
    body: payload,
  });
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export function changePassword(payload: ChangePasswordPayload): Promise<{ status: string; message: string }> {
  return request<{ status: string; message: string }>("/auth/change-password", {
    method: "POST",
    body: payload,
  });
}
