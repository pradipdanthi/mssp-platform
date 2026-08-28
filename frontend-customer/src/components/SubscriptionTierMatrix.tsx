import { TIER_CATALOG, TIER_FEATURE_MATRIX } from "../data/subscriptionTierMatrix";
import {
  normalizeTier,
  tierMeetsMinimum,
  upgradeLabel,
  type SubscriptionTier,
} from "../config/tierConfig";
import { TierUpgradeBadge } from "./TierUpgradeBadge";

type Props = {
  activeTier?: string | null;
  onRequestUpgrade?: (targetTier: SubscriptionTier) => void;
  compact?: boolean;
};

export default function SubscriptionTierMatrix({
  activeTier,
  onRequestUpgrade,
  compact = false,
}: Props) {
  const current = normalizeTier(activeTier);

  return (
    <div className={"subscription-tier-matrix" + (compact ? " subscription-tier-matrix--compact" : "")}>
      <div className="tier-matrix-cards">
        {TIER_CATALOG.map((entry) => {
          const isActive = entry.tier === current;
          const needsHigherTier = TIER_RANK[entry.tier] > TIER_RANK[current];

          return (
            <article
              key={entry.tier}
              className={
                "tier-card glass-card" +
                (isActive ? " tier-card--active" : "") +
                (needsHigherTier && !isActive ? " tier-card--upgrade" : "")
              }
              aria-current={isActive ? "true" : undefined}
            >
              <header className="tier-card-header">
                <div>
                  <p className="tier-card-eyebrow">{entry.subtitle}</p>
                  <h2 className="tier-card-title">{entry.name}</h2>
                </div>
                <div className="tier-card-badges">
                  {isActive && <span className="tier-badge tier-badge--active">Your plan</span>}
                  {needsHigherTier && onRequestUpgrade && (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm tier-upgrade-cta"
                      onClick={() => onRequestUpgrade(entry.tier)}
                    >
                      {upgradeLabel(entry.tier)}
                    </button>
                  )}
                  {needsHigherTier && !onRequestUpgrade && (
                    <TierUpgradeBadge requiredTier={entry.tier} />
                  )}
                </div>
              </header>
              <p className="tier-card-tagline">{entry.tagline}</p>
              {entry.inheritsFrom && (
                <p className="tier-card-inherits">
                  Everything in {tierName(entry.inheritsFrom)}, plus:
                </p>
              )}
              <ul className="tier-feature-list">
                {entry.features.map((feature) => (
                  <li key={feature}>{feature}</li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>

      {!compact && (
        <div className="tier-matrix-table-wrap">
          <table className="tier-matrix-table data-table">
            <thead>
              <tr>
                <th scope="col">Capability</th>
                <th scope="col" className={current === "SILVER" ? "tier-col--active" : ""}>
                  Silver
                </th>
                <th scope="col" className={current === "GOLD" ? "tier-col--active" : ""}>
                  Gold
                </th>
                <th scope="col" className={current === "PLATINUM" ? "tier-col--active" : ""}>
                  Platinum
                </th>
              </tr>
            </thead>
            <tbody>
              {TIER_FEATURE_MATRIX.map((row) => {
                const locked = !tierMeetsMinimum(current, row.minTier);
                return (
                  <tr key={row.id} className={locked ? "tier-row--locked" : ""}>
                    <th scope="row">
                      {row.label}
                      {locked && (
                        <span className="tier-row-upgrade">
                          <TierUpgradeBadge requiredTier={row.minTier} />
                        </span>
                      )}
                    </th>
                    <td className={tierMeetsMinimum("SILVER", row.minTier) ? "cell-yes" : ""}>
                      {tierMeetsMinimum("SILVER", row.minTier) ? "✓" : "—"}
                    </td>
                    <td className={tierMeetsMinimum("GOLD", row.minTier) ? "cell-yes" : ""}>
                      {tierMeetsMinimum("GOLD", row.minTier) ? "✓" : "—"}
                    </td>
                    <td className={tierMeetsMinimum("PLATINUM", row.minTier) ? "cell-yes" : ""}>
                      {tierMeetsMinimum("PLATINUM", row.minTier) ? "✓" : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const TIER_RANK: Record<SubscriptionTier, number> = {
  SILVER: 1,
  GOLD: 2,
  PLATINUM: 3,
};

function tierName(tier: SubscriptionTier): string {
  return TIER_CATALOG.find((t) => t.tier === tier)?.name ?? tier;
}
