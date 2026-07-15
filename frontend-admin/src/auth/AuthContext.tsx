import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { login as apiLogin, me as apiMe, UserPublic } from "../api/auth";
import { ApiError, setAuthToken } from "../api/client";

// KB-018 Decision E: sessionStorage only (never localStorage), and the
// token is never put in a URL or logged to the console anywhere in this
// file or in api/client.ts.
const TOKEN_STORAGE_KEY = "mssp_admin_access_token";

interface AuthContextValue {
  token: string | null;
  user: UserPublic | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // On first load, re-validate any token already in sessionStorage against
  // GET /auth/me instead of trusting it blindly - a token can outlive an
  // account being disabled or the JWT secret rotating server-side.
  useEffect(() => {
    const stored = sessionStorage.getItem(TOKEN_STORAGE_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    setAuthToken(stored);
    apiMe()
      .then((fetchedUser) => {
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
      sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
      setAuthToken(result.access_token);
      setToken(result.access_token);
      setUser(result.user);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : "Invalid email or password.");
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
    <AuthContext.Provider value={{ token, user, loading, error, login, logout, clearError }}>
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
