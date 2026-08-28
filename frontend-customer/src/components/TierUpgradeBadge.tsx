import { Link } from "react-router-dom";
import type { SubscriptionTier } from "../config/tierConfig";
import { upgradeLabel } from "../config/tierConfig";

type Props = {
  requiredTier: SubscriptionTier;
  className?: string;
};

export function TierUpgradeBadge({ requiredTier, className }: Props) {
  return (
    <Link to="/services" className={className ?? "tier-upgrade-badge"} title={upgradeLabel(requiredTier)}>
      {upgradeLabel(requiredTier)}
    </Link>
  );
}
