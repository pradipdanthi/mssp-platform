/** Emerald radial SLA / automation health gauge. */
export default function RadialGauge({
  percent,
  label = "SLA",
}: {
  percent: number;
  label?: string;
}) {
  const p = Math.max(0, Math.min(100, percent));
  const r = 34;
  const c = 2 * Math.PI * r;
  const offset = c - (p / 100) * c;
  return (
    <div className="radial-gauge" aria-label={`${label} ${p}%`}>
      <svg viewBox="0 0 88 88" width={72} height={72}>
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
          style={{ filter: "drop-shadow(0 0 6px rgba(34, 197, 94,0.45))" }}
        />
        <text x="44" y="48" textAnchor="middle" className="radial-gauge-text">
          {p}%
        </text>
      </svg>
    </div>
  );
}
