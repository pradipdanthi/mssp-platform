import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, setAuthToken } from "../api/client";
import {
  isStaff,
  login as apiLogin,
  me as apiMe,
  mfaAuthenticate,
  UserPublic,
} from "../api/auth";

/** localStorage so “Open on monitor” windows share the same SOC login. */
const TOKEN_KEY = "mssp_soc_console_token";
const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY),
  set: (v: string) => {
    localStorage.setItem(TOKEN_KEY, v);
    sessionStorage.removeItem(TOKEN_KEY);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
  },
};

type AuthCtx = {
  token: string | null;
  user: UserPublic | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean; mfaToken?: string }>;
  completeMfa: (mfaToken: string, code: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
};

const Ctx = createContext<AuthCtx | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = tokenStore.get();
    if (!stored) {
      setLoading(false);
      return;
    }
    setAuthToken(stored);
    apiMe()
      .then((u) => {
        if (!isStaff(u)) {
          tokenStore.clear();
          setAuthToken(null);
          setError("SOC Console is for Admin / SOC roles only.");
          return;
        }
        tokenStore.set(stored);
        setToken(stored);
        setUser(u);
      })
      .catch(() => {
        tokenStore.clear();
        setAuthToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    const result = await apiLogin(email, password);
    if (result.mfa_required) {
      if (!result.mfa_token) throw new ApiError(500, "MFA token missing");
      return { mfaRequired: true, mfaToken: result.mfa_token };
    }
    if (!result.access_token || !result.user) throw new ApiError(500, "Incomplete login");
    if (!isStaff(result.user)) {
      throw new ApiError(403, "Wrong portal — use Admin/SOC credentials");
    }
    tokenStore.set(result.access_token);
    setAuthToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    return { mfaRequired: false };
  }, []);

  const completeMfa = useCallback(async (mfaToken: string, code: string) => {
    const result = await mfaAuthenticate(mfaToken, code);
    if (!isStaff(result.user)) {
      throw new ApiError(403, "Wrong portal — use Admin/SOC credentials");
    }
    tokenStore.set(result.access_token);
    setAuthToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setAuthToken(null);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <Ctx.Provider
      value={{
        token,
        user,
        loading,
        error,
        login,
        completeMfa,
        logout,
        clearError: () => setError(null),
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
}
