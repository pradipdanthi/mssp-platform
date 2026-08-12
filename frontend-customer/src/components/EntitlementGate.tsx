import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCustomerEntitlements } from "../config/EntitlementsContext";
import {
  CustomerEntitlementKey,
  entitlementLabel,
  isEntitlementEnabled,
} from "../config/navEntitlements";

/**
 * Blocks add-on pages when the tenant has not subscribed.
 * Shows a clear upgrade path via Service Portfolio.
 */
export default function EntitlementGate({
  require,
  children,
}: {
  require: CustomerEntitlementKey;
  children: ReactNode;
}) {
  const { entitlements, loading, error } = useCustomerEntitlements();

  if (loading) {
    return <div className="state-message">Checking your subscribed services…</div>;
  }

  if (error) {
    return <div className="state-message state-error">{error}</div>;
  }

  if (!isEntitlementEnabled(entitlements, require)) {
    const name = entitlementLabel(require);
    return (
      <div className="entitlement-gate">
        <h1 className="page-title">{name}</h1>
        <p className="page-subtitle">
          This service is not part of your current subscription. Your MSSP team can enable it after
          a consulting request from Service Portfolio.
        </p>
        <div className="entitlement-gate-actions">
          <Link className="btn btn-primary" to="/services">
            Open Service Portfolio
          </Link>
          <Link className="btn btn-ghost" to="/dashboard">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
