import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

/**
 * KB-018: small shared hook used by every list/dashboard page so the
 * loading/error/401/403 handling is written once instead of six times.
 * Not part of the "suggested files" list in the KB-018 prompt, added
 * because duplicating this logic across six pages risked one of them
 * forgetting the 401 handling.
 */
export type AdminQueryStatus = "loading" | "success" | "error" | "forbidden";

interface UseAdminQueryResult<T> {
  status: AdminQueryStatus;
  data: T | null;
  errorMessage: string | null;
  refetch: () => void;
}

export function useAdminQuery<T>(fetchFn: () => Promise<T>, deps: unknown[] = []): UseAdminQueryResult<T> {
  const { logout } = useAuth();
  const [status, setStatus] = useState<AdminQueryStatus>("loading");
  const [data, setData] = useState<T | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refetch = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setErrorMessage(null);

    fetchFn()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setStatus("success");
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 401) {
            // Session expired or token invalid - clear it and let
            // ProtectedRoute send the user back to /login.
            logout();
            return;
          }
          if (err.status === 403) {
            setStatus("forbidden");
            return;
          }
          setErrorMessage(typeof err.detail === "string" ? err.detail : "The server rejected this request.");
        } else {
          setErrorMessage("Unable to reach the server. Please try again.");
        }
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
    // deps intentionally drives refetching; fetchFn/logout are stable enough
    // for this foundation module's needs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadToken, ...deps]);

  return { status, data, errorMessage, refetch };
}
