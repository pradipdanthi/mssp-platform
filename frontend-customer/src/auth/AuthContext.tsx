import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { login as apiLogin, me as apiMe, isCustomerPortalUser, UserPublic } from "../api/auth";
import { ApiError, setAuthToken } from "../api/client";

const TOKEN_STORAGE_KEY = "mssp_customer_access_token";

interface AuthContextValue {
  token: string | null;
  user: UserPublic | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  refreshUser: () => Promise<void>;
  setUser: (user: UserPublic | null) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);
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
        if (!isCustomerPortalUser(fetchedUser)) {
          sessionStorage.removeItem(TOKEN_STORAGE_KEY);
          setAuthToken(null);
          setToken(null);
          setUser(null);
          setError("MSSP staff must use the admin portal at admin.kevantic.com.");
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
      if (!isCustomerPortalUser(result.user)) {
        sessionStorage.removeItem(TOKEN_STORAGE_KEY);
        setAuthToken(null);
        setError("MSSP staff must sign in at admin.kevantic.com.");
        throw new ApiError(403, "Wrong portal");
      }
      sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
      setAuthToken(result.access_token);
      setToken(result.access_token);
      // Prefer fresh /auth/me so tenant_short_code/tenant_name are present.
      try {
        const fresh = await apiMe();
        setUser(fresh);
      } catch {
        setUser(result.user);
      }
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

  const refreshUser = useCallback(async () => {
    const fresh = await apiMe();
    setUser(fresh);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        loading,
        error,
        login,
        logout,
        clearError,
        refreshUser,
        setUser,
      }}
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
