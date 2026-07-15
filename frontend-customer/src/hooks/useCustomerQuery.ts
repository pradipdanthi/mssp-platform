import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export type CustomerQueryStatus = "loading" | "success" | "error" | "forbidden" | "not_found";

interface UseCustomerQueryResult<T> {
  status: CustomerQueryStatus;
  data: T | null;
  errorMessage: string | null;
  refetch: () => void;
}

export function useCustomerQuery<T>(
  fetchFn: () => Promise<T>,
  enabled: boolean,
  deps: unknown[] = []
): UseCustomerQueryResult<T> {
  const { logout } = useAuth();
  const [status, setStatus] = useState<CustomerQueryStatus>("loading");
  const [data, setData] = useState<T | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refetch = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) {
      setStatus("error");
      setErrorMessage("This account is not linked to a customer tenant.");
      setData(null);
      return;
    }

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
            logout();
            return;
          }
          if (err.status === 403) {
            setStatus("forbidden");
            return;
          }
          if (err.status === 404) {
            setStatus("not_found");
            setErrorMessage(
              typeof err.detail === "string" ? err.detail : "Tenant data was not found."
            );
            return;
          }
          setErrorMessage(
            typeof err.detail === "string" ? err.detail : "The server rejected this request."
          );
        } else {
          setErrorMessage("Unable to reach the server. Please try again.");
        }
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, reloadToken, ...deps]);

  return { status, data, errorMessage, refetch };
}
