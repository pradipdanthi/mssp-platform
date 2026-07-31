/** Emerald radial readiness / health gauge. */
export default function RadialGauge({
  percent,
  label = "SLA",
  size = 72,
}: {
  percent: number;
  label?: string;
  size?: number;
}) {
  const p = Math.max(0, Math.min(100, percent));
  const r = 34;
  const c = 2 * Math.PI * r;
  const offset = c - (p / 100) * c;
  const textPx = Math.max(14, Math.round(size * 0.28));
  return (
    <div className="radial-gauge" aria-label={`${label} ${p}%`}>
      <svg viewBox="0 0 88 88" width={size} height={size}>
        <circle cx="44" cy="44" r={r} fill="none" stroke="#23344D" strokeWidth="8" />
        <circle
          cx="44"
          cy="44"
          r={r}
          fill="none"
          stroke="#22C55E"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform="rotate(-90 44 44)"
        />
        <text
          x="44"
          y="48"
          textAnchor="middle"
          className="radial-gauge-text"
          style={{ fontSize: textPx }}
        >
          {p}%
        </text>
      </svg>
    </div>
  );
}
