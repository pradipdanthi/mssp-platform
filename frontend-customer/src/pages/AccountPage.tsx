import { useAuth } from "../auth/AuthContext";
import { useBrand } from "../config/BrandContext";

export default function AccountPage() {
  const { user } = useAuth();
  const brand = useBrand();

  if (!user) {
    return <div className="state-message">No account information available.</div>;
  }

  return (
    <div>
      <h1 className="page-title">Account</h1>
      <p className="page-subtitle">Read-only account and tenant information.</p>

      <div className="account-panel">
        <div className="credential-grid">
          <Field label="Name" value={user.full_name} />
          <Field label="Email" value={user.email} />
          <Field label="Role" value={user.role} />
          <Field label="Status" value={user.status} />
          <Field label="Tenant" value={user.tenant_name ?? "Not assigned"} />
          <Field label="Tenant code" value={user.tenant_short_code ?? "Not assigned"} />
          <Field label="Last login" value={user.last_login_at ?? "Never"} />
          <Field label="Portal" value={brand.portalName} />
        </div>
        {!user.tenant_short_code && (
          <div className="state-message state-error" style={{ marginTop: 16 }}>
            This account is not linked to a customer tenant. Customer dashboard data requires a
            tenant-linked customer role.
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="credential-field">
      <div className="credential-field-label">{label}</div>
      <div className="credential-field-value">{value}</div>
    </div>
  );
}
