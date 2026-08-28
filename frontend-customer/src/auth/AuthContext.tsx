import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  login as apiLogin,
  mfaAuthenticate,
  me as apiMe,
  isCustomerPortalUser,
  MfaCompleteSetupResponse,
  TokenResponse,
  UserPublic,
} from "../api/auth";
import { ApiError, setAuthToken } from "../api/client";

const TOKEN_STORAGE_KEY = "mssp_customer_access_token";

interface AuthContextValue {
  token: string | null;
  user: UserPublic | null;
  loading: boolean;
  error: string | null;
  login: (
    email: string,
    password: string
  ) => Promise<{ mfaRequired: boolean; mfaToken?: string; mfaSetupRequired?: boolean; setupToken?: string }>;
  completeMfaLogin: (mfaToken: string, code: string) => Promise<void>;
  establishSessionFromToken: (result: TokenResponse | MfaCompleteSetupResponse) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  refreshUser: () => Promise<void>;
  setUser: (user: UserPublic | null) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

async function establishSession(
  result: TokenResponse,
  setToken: (t: string) => void,
  setUser: (u: UserPublic) => void
) {
  if (!isCustomerPortalUser(result.user)) {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    setAuthToken(null);
    throw new ApiError(403, "Wrong portal");
  }
  sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
  setAuthToken(result.access_token);
  setToken(result.access_token);
  try {
    const fresh = await apiMe();
    setUser(fresh);
  } catch {
    setUser(result.user);
  }
}

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
      if (result.mfa_required) {
        if (!result.mfa_token) {
          throw new ApiError(500, "MFA session token missing");
        }
        return { mfaRequired: true, mfaToken: result.mfa_token, mfaSetupRequired: false };
      }
      if (result.mfa_setup_required) {
        if (!result.setup_token) {
          throw new ApiError(500, "MFA setup token missing");
        }
        return { mfaRequired: false, mfaSetupRequired: true, setupToken: result.setup_token };
      }
      if (!result.access_token || !result.user) {
        throw new ApiError(500, "Login response incomplete");
      }
      await establishSession(
        {
          access_token: result.access_token,
          token_type: result.token_type || "bearer",
          expires_in: result.expires_in || 3600,
          user: result.user,
        },
        setToken,
        setUser
      );
      return { mfaRequired: false, mfaSetupRequired: false };
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail === "Wrong portal") {
          setError("MSSP staff must sign in at admin.kevantic.com.");
        } else {
          setError(typeof err.detail === "string" ? err.detail : "Invalid email or password.");
        }
      } else {
        setError("Unable to reach the server. Please try again.");
      }
      throw err;
    }
  }, []);

  const establishSessionFromToken = useCallback(async (result: TokenResponse | MfaCompleteSetupResponse) => {
    await establishSession(result, setToken, setUser);
  }, []);

  const completeMfaLogin = useCallback(async (mfaToken: string, code: string) => {
    setError(null);
    try {
      const result = await mfaAuthenticate(mfaToken, code);
      await establishSession(result, setToken, setUser);
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
        completeMfaLogin,
        establishSessionFromToken,
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
