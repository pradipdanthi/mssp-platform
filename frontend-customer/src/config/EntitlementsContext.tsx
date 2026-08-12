import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getCustomerEntitlements, type CustomerEntitlements } from "../api/customer";
import { useAuth } from "../auth/AuthContext";

type EntitlementsContextValue = {
  entitlements: CustomerEntitlements | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
};

const EntitlementsContext = createContext<EntitlementsContextValue>({
  entitlements: null,
  loading: true,
  error: null,
  refresh: () => undefined,
});

export function EntitlementsProvider({ children }: { children: ReactNode }) {
  const { user, token } = useAuth();
  const shortCode = user?.tenant_short_code ?? "";
  const [entitlements, setEntitlements] = useState<CustomerEntitlements | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!token || !shortCode) {
      setEntitlements(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getCustomerEntitlements(shortCode)
      .then((ent) => {
        if (cancelled) return;
        setEntitlements(ent);
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setEntitlements(null);
        setError("Could not load service entitlements.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, shortCode, tick]);

  const value = useMemo(
    () => ({
      entitlements,
      loading,
      error,
      refresh: () => setTick((n) => n + 1),
    }),
    [entitlements, loading, error]
  );

  return (
    <EntitlementsContext.Provider value={value}>{children}</EntitlementsContext.Provider>
  );
}

export function useCustomerEntitlements(): EntitlementsContextValue {
  return useContext(EntitlementsContext);
}
