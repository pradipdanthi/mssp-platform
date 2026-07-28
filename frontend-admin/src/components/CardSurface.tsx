import React from "react";

export type CardSurfaceTone =
  | "default"
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "accent";

type CardSurfaceProps = React.HTMLAttributes<HTMLDivElement> & {
  /** Optional severity / metric glow (Phase 1 token wiring). */
  tone?: CardSurfaceTone;
};

/**
 * Phase 1 surface primitive — uses SOC-Glow `--soc-surface` tokens.
 * Layout consumers (KPI cards, panels) should prefer this over raw divs.
 */
export function CardSurface({
  tone = "default",
  className = "",
  children,
  ...rest
}: CardSurfaceProps) {
  const toneClass = tone === "default" ? "" : ` card-surface--${tone}`;
  return (
    <div className={`card-surface${toneClass} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
