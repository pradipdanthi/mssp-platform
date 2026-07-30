import { useEffect, useState } from "react";
import { getTenants } from "../api/admin";

const STORAGE_KEY = "mssp.admin.tenantFilter";

export function getStoredTenantFilter(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || "all";
  } catch {
    return "all";
  }
}

/** Header tenant switcher — filters are stored for future list pages. */
export default function TenantSwitcher() {
  const [tenants, setTenants] = useState<{ id: string; name: string; short_code: string }[]>([]);
  const [value, setValue] = useState(getStoredTenantFilter);

  useEffect(() => {
    let cancelled = false;
    getTenants({ page_size: 200 })
      .then((res) => {
        if (cancelled) return;
        setTenants(
          (res.tenants || []).map((t) => ({
            id: t.id,
            name: t.name,
            short_code: t.short_code,
          }))
        );
      })
      .catch(() => {
        /* header must not break the shell */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const count = tenants.length;
  const label =
    value === "all"
      ? `All Tenants (${count || "—"})`
      : tenants.find((t) => t.id === value)?.name || "Tenant";

  return (
    <select
      className="tenant-switcher"
      aria-label="Tenant filter"
      title={label}
      value={value}
      onChange={(e) => {
        const next = e.target.value;
        setValue(next);
        try {
          localStorage.setItem(STORAGE_KEY, next);
        } catch {
          /* ignore */
        }
        window.dispatchEvent(new CustomEvent("mssp-tenant-filter", { detail: next }));
      }}
    >
      <option value="all">Tenant Scope: All Tenants ({count || 0})</option>
      {tenants.map((t) => (
        <option key={t.id} value={t.id}>
          {t.name} ({t.short_code})
        </option>
      ))}
    </select>
  );
}
