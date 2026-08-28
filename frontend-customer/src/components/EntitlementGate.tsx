import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCustomerEntitlements } from "../config/EntitlementsContext";
import { capabilityFlagEnabled } from "../config/capabilityAccess";
import {
  CustomerEntitlementKey,
  entitlementLabel,
  isEntitlementEnabled,
} from "../config/navEntitlements";
import { MODULE_MIN_TIER, isCustomTier, normalizeTier, tierMeetsMinimum } from "../config/tierConfig";
import { TierUpgradeBadge } from "./TierUpgradeBadge";

/**
 * Blocks capability pages when the tenant's subscription tier is too low.
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
    return <div className="state-message">Checking your subscription tier…</div>;
  }

  if (error) {
    return <div className="state-message state-error">{error}</div>;
  }

  const name = entitlementLabel(require);
  const requiredTier = MODULE_MIN_TIER[require];
  const custom = isCustomTier(entitlements?.subscription_tier);

  if (!isEntitlementEnabled(entitlements, require)) {
    return (
      <div className="entitlement-gate">
        <h1 className="page-title">{name}</h1>
        <p className="page-subtitle">
          {custom ? (
            <>
              This capability is not included in your custom subscription agreement. Contact your
              account manager if you need it added.
            </>
          ) : (
            <>
              This capability is included in the <strong>{requiredTier}</strong> tier or higher when
              provisioned in your contract.
              {!capabilityFlagEnabled(entitlements, require) &&
              tierMeetsMinimum(normalizeTier(entitlements?.subscription_tier), requiredTier)
                ? " Your MSSP team may still be enabling this module — contact your account manager if you need access."
                : " Request a tier upgrade from your Service Portfolio."}
            </>
          )}
        </p>
        <div className="entitlement-gate-actions">
          {!custom && (
            <TierUpgradeBadge requiredTier={requiredTier} className="btn btn-primary" />
          )}
          <Link className="btn btn-ghost" to="/dashboard">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
