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
  is_mfa_enabled?: boolean;
}

export interface LoginResponse {
  mfa_required: boolean;
  mfa_setup_required?: boolean;
  mfa_token?: string | null;
  setup_token?: string | null;
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

export interface MfaSetupSessionResponse {
  secret: string;
  otpauth_uri: string;
}

export interface MfaCompleteSetupResponse extends TokenResponse {
  recovery_codes: string[];
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password, portal: "customer" },
  });
}

export function mfaAuthenticate(mfaToken: string, code: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/mfa/authenticate", {
    method: "POST",
    body: { mfa_token: mfaToken, code },
  });
}

export function mfaSetupSession(setupToken: string): Promise<MfaSetupSessionResponse> {
  return request<MfaSetupSessionResponse>("/auth/mfa/setup-session", {
    method: "POST",
    body: { setup_token: setupToken },
  });
}

export function mfaCompleteSetup(
  setupToken: string,
  code: string
): Promise<MfaCompleteSetupResponse> {
  return request<MfaCompleteSetupResponse>("/auth/mfa/complete-setup", {
    method: "POST",
    body: { setup_token: setupToken, code },
  });
}

const CUSTOMER_ROLES = new Set(["customer_admin", "customer_viewer"]);
const MFA_SETUP_TOKEN_KEY = "mssp_customer_mfa_setup_token";

export function storeMfaSetupToken(token: string): void {
  sessionStorage.setItem(MFA_SETUP_TOKEN_KEY, token);
}

export function getStoredMfaSetupToken(): string | null {
  return sessionStorage.getItem(MFA_SETUP_TOKEN_KEY);
}

export function clearMfaSetupToken(): void {
  sessionStorage.removeItem(MFA_SETUP_TOKEN_KEY);
}

export function isCustomerPortalUser(user: UserPublic | null): boolean {
  return !!user && CUSTOMER_ROLES.has(user.role);
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
