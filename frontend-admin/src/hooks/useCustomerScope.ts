import { useEffect, useMemo, useState } from "react";
import { getTenants } from "../api/admin";
import {
  getStoredTenantFilter,
  TENANT_FILTER_EVENT,
} from "../components/TenantSwitcher";

/** Header Customer scope — shared across Dashboard, AI Assistant, and list pages. */
export function useCustomerScope() {
  const [filter, setFilter] = useState(getStoredTenantFilter);
  const [tenantMeta, setTenantMeta] = useState<{
    id: string;
    name: string;
    short_code: string;
  } | null>(null);

  useEffect(() => {
    const onScope = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (typeof detail === "string") setFilter(detail);
    };
    window.addEventListener(TENANT_FILTER_EVENT, onScope as EventListener);
    return () => window.removeEventListener(TENANT_FILTER_EVENT, onScope as EventListener);
  }, []);

  const scopeAll = filter === "all";
  const tenantId = scopeAll ? undefined : filter;

  useEffect(() => {
    if (!tenantId) {
      setTenantMeta(null);
      return;
    }
    let cancelled = false;
    getTenants({ page_size: 200 })
      .then((res) => {
        if (cancelled) return;
        const match = (res.tenants || []).find((t) => t.id === tenantId);
        setTenantMeta(
          match ? { id: match.id, name: match.name, short_code: match.short_code } : null
        );
      })
      .catch(() => {
        if (!cancelled) setTenantMeta(null);
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  const tenantFilter = useMemo(
    () => (tenantId ? { tenant_id: tenantId } : {}),
    [tenantId]
  );

  const tenantShortCodeFilter = useMemo(
    () => (tenantMeta?.short_code ? { tenant_short_code: tenantMeta.short_code } : {}),
    [tenantMeta?.short_code]
  );

  return {
    filter,
    scopeAll,
    tenantId,
    tenantName: tenantMeta?.name,
    tenantShortCode: tenantMeta?.short_code,
    /** APIs that accept tenant_id (UUID). */
    tenantFilter,
    /** APIs that accept tenant_short_code. */
    tenantShortCodeFilter,
  };
}
