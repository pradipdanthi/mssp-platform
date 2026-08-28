import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  login as apiLogin,
  mfaAuthenticate,
  me as apiMe,
  isStaffPortalUser,
  TokenResponse,
  UserPublic,
} from "../api/auth";
import { ApiError, setAuthToken } from "../api/client";

const TOKEN_STORAGE_KEY = "mssp_admin_access_token";

interface AuthContextValue {
  token: string | null;
  user: UserPublic | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean; mfaToken?: string }>;
  completeMfaLogin: (mfaToken: string, code: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function establishSession(result: TokenResponse, setToken: (t: string) => void, setUser: (u: UserPublic) => void) {
  if (!isStaffPortalUser(result.user)) {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    throw new ApiError(403, "Wrong portal");
  }
  sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
  setAuthToken(result.access_token);
  setToken(result.access_token);
  setUser(result.user);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem(TOKEN_STORAGE_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    setAuthToken(stored);
    apiMe()
      .then((fetchedUser) => {
        if (!isStaffPortalUser(fetchedUser)) {
          sessionStorage.removeItem(TOKEN_STORAGE_KEY);
          setAuthToken(null);
          setToken(null);
          setUser(null);
          setError("This account is for the customer portal only. Sign in at portal.kevantic.com.");
          return;
        }
        setToken(stored);
        setUser(fetchedUser);
      })
      .catch(() => {
        sessionStorage.removeItem(TOKEN_STORAGE_KEY);
        setAuthToken(null);
        setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    try {
      const result = await apiLogin(email, password);
      if (result.mfa_required) {
        if (!result.mfa_token) {
          throw new ApiError(500, "MFA session token missing");
        }
        return { mfaRequired: true, mfaToken: result.mfa_token };
      }
      if (!result.access_token || !result.user) {
        throw new ApiError(500, "Login response incomplete");
      }
      establishSession(
        {
          access_token: result.access_token,
          token_type: result.token_type || "bearer",
          expires_in: result.expires_in || 3600,
          user: result.user,
        },
        setToken,
        setUser
      );
      return { mfaRequired: false };
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail === "Wrong portal") {
          setError(
            "This account is for the customer portal only. Sign in at portal.kevantic.com."
          );
        } else {
          setError(typeof err.detail === "string" ? err.detail : "Invalid email or password.");
        }
      } else {
        setError("Unable to reach the server. Please try again.");
      }
      throw err;
    }
  }, []);

  const completeMfaLogin = useCallback(async (mfaToken: string, code: string) => {
    setError(null);
    try {
      const result = await mfaAuthenticate(mfaToken, code);
      establishSession(result, setToken, setUser);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "Invalid MFA code.");
      } else {
        setError("Unable to reach the server. Please try again.");
      }
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return (
    <AuthContext.Provider
      value={{ token, user, loading, error, login, completeMfaLogin, logout, clearError }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
