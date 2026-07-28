import { Link } from "react-router-dom";
import type { ReactNode } from "react";

type Tone = "default" | "critical" | "high" | "medium" | "low" | "accent";

type Trend = {
  label: string;
  direction: "up" | "down" | "flat";
};

type Props = {
  label: string;
  value: ReactNode;
  to?: string;
  tone?: Tone;
  trend?: Trend | null;
  hint?: string;
};

export default function GlowStatCard({
  label,
  value,
  to,
  tone = "default",
  trend = null,
  hint,
}: Props) {
  const glow =
    tone === "critical" || tone === "high" ? " stat-card--glow-critical" : "";
  const toneClass = tone === "default" ? "" : ` stat-card--${tone}`;
  const valueTone =
    tone === "default" ? "" : ` stat-card-value--${tone}`;

  const body = (
    <>
      <div className="stat-card-row">
        <div className={`stat-card-value${valueTone}`}>{value}</div>
        {trend ? (
          <span className={`stat-trend stat-trend--${trend.direction}`}>{trend.label}</span>
        ) : null}
      </div>
      <div className="stat-card-label">{label}</div>
      {hint ? <div className="stat-card-hint">{hint}</div> : null}
    </>
  );

  const cls = `stat-card card-surface${toneClass}${glow}${to ? " stat-card-link" : ""}`;
  if (to) {
    return (
      <Link className={cls} to={to} aria-label={`Open ${label}`}>
        {body}
      </Link>
    );
  }
  return <div className={cls}>{body}</div>;
}
