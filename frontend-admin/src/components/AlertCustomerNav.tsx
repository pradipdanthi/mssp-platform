import { Link } from "react-router-dom";

export type AlertTenantSummary = {
  tenant_id: string;
  tenant_name: string;
  short_code: string;
  alert_count: number;
  high_critical_count: number;
};

type Props = {
  tenants: AlertTenantSummary[];
  activeTenantId: string | null;
  severityFilter: string | null;
  statusFilter: string | null;
};

function customerLink(
  tenantId: string,
  severityFilter: string | null,
  statusFilter: string | null
): string {
  const params = new URLSearchParams();
  params.set("tenant_id", tenantId);
  if (severityFilter) params.set("severity", severityFilter);
  if (statusFilter) params.set("status", statusFilter);
  return `/alerts?${params.toString()}`;
}

function allCustomersLink(severityFilter: string | null, statusFilter: string | null): string {
  const params = new URLSearchParams();
  if (severityFilter) params.set("severity", severityFilter);
  if (statusFilter) params.set("status", statusFilter);
  const q = params.toString();
  return q ? `/alerts?${q}` : "/alerts";
}

/** Customer picker for Admin Alerts — same visual language as device taxonomy nav. */
export default function AlertCustomerNav({
  tenants,
  activeTenantId,
  severityFilter,
  statusFilter,
}: Props) {
  const totalAlerts = tenants.reduce((sum, t) => sum + (t.alert_count || 0), 0);

  return (
    <nav className="alert-taxonomy-nav card-surface" aria-label="Alert customers">
      <h2 className="section-title" style={{ marginTop: 0, fontSize: "1rem" }}>
        Customers
      </h2>
      <ul className="alert-taxonomy-list">
        <li>
          <Link
            className={
              activeTenantId ? "alert-taxonomy-link" : "alert-taxonomy-link active"
            }
            to={allCustomersLink(severityFilter, statusFilter)}
          >
            All customers
            <span className="alert-taxonomy-badge">{totalAlerts}</span>
          </Link>
        </li>
      </ul>
      <p className="muted" style={{ fontSize: "0.85rem", margin: "0.5rem 0" }}>
        Select a customer
      </p>
      <ul className="alert-taxonomy-list">
        {tenants.map((tenant) => (
          <li key={tenant.tenant_id}>
            <Link
              className={
                activeTenantId === tenant.tenant_id
                  ? "alert-taxonomy-link active"
                  : "alert-taxonomy-link"
              }
              to={customerLink(tenant.tenant_id, severityFilter, statusFilter)}
            >
              <span className="alert-customer-label">
                {tenant.tenant_name}
                <span className="alert-customer-code">{tenant.short_code}</span>
              </span>
              <span className="alert-taxonomy-badge">{tenant.alert_count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
