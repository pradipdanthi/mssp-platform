import { Link } from "react-router-dom";
import type { SubscriptionTier } from "../config/tierConfig";
import { upgradeLabel, upgradeShortLabel } from "../config/tierConfig";

type Props = {
  requiredTier: SubscriptionTier;
  className?: string;
  /** Shorter pill text for sidebar / dense layouts */
  compact?: boolean;
};

export function TierUpgradeBadge({ requiredTier, className, compact = false }: Props) {
  const label = compact ? upgradeShortLabel(requiredTier) : upgradeLabel(requiredTier);
  return (
    <Link
      to="/services"
      className={className ?? "tier-upgrade-badge"}
      title={upgradeLabel(requiredTier)}
    >
      {label}
    </Link>
  );
}
