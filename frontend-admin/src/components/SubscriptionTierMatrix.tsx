import {
  TIER_CATALOG,
  TIER_FEATURE_MATRIX,
  normalizeTier,
  tierDisplayName,
  TIER_RANK,
  type SubscriptionTier,
} from "../data/subscriptionTierMatrix";

type Props = {
  activeTier?: string | null;
  onTierChange?: (tier: SubscriptionTier) => void;
  tierEditable?: boolean;
  compact?: boolean;
};

function tierMeetsMinimum(current: SubscriptionTier, required: SubscriptionTier): boolean {
  return TIER_RANK[current] >= TIER_RANK[required];
}

export default function SubscriptionTierMatrix({
  activeTier,
  onTierChange,
  tierEditable = false,
  compact = false,
}: Props) {
  const current = normalizeTier(activeTier);

  return (
    <div className={"subscription-tier-matrix" + (compact ? " subscription-tier-matrix--compact" : "")}>
      {tierEditable && onTierChange && (
        <label className="form-label tier-selector">
          Subscription tier
          <select
            className="form-input"
            value={current}
            onChange={(e) => onTierChange(e.target.value as SubscriptionTier)}
          >
            <option value="SILVER">Silver — Identity ITDR</option>
            <option value="GOLD">Gold — Core MDR</option>
            <option value="PLATINUM">Platinum — Full MXDR</option>
          </select>
        </label>
      )}

      <div className="tier-matrix-cards">
        {TIER_CATALOG.map((entry) => {
          const isActive = entry.tier === current;
          return (
            <article
              key={entry.tier}
              className={"tier-card glass-card" + (isActive ? " tier-card--active" : "")}
              aria-current={isActive ? "true" : undefined}
            >
              <header className="tier-card-header">
                <div>
                  <p className="tier-card-eyebrow">{entry.subtitle}</p>
                  <h2 className="tier-card-title">{entry.name}</h2>
                </div>
                {isActive && <span className="tier-badge tier-badge--active">Active tier</span>}
              </header>
              <p className="tier-card-tagline">{entry.tagline}</p>
              {entry.inheritsFrom && (
                <p className="tier-card-inherits">
                  Everything in {tierDisplayName(entry.inheritsFrom)}, plus:
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
              {TIER_FEATURE_MATRIX.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.label}</th>
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
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
