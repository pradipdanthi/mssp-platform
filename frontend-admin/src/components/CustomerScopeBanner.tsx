import { useCustomerScope } from "../hooks/useCustomerScope";

/** Shows which customer the header scope is filtering — omit when all tenants. */
export default function CustomerScopeBanner() {
  const { scopeAll, tenantName, tenantShortCode } = useCustomerScope();

  if (scopeAll || !tenantName) return null;

  const label = tenantShortCode ? `${tenantName} (${tenantShortCode})` : tenantName;

  return (
    <p className="customer-scope-banner" role="status">
      Showing <strong>{label}</strong> only — change via <strong>Customer scope</strong> in the
      header.
    </p>
  );
}
