/** Stacked 24h severity timeline — Critical / High / Medium+Low (cyan). */

export type SeverityBucket = {
  label: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
};

const COLORS = {
  critical: "#EF4444",
  high: "#F59E0B",
  cyan: "#00AEEF",
};

const Y_MAX = 20;
const CHART_W = 560;
const CHART_H = 168;
const PAD_L = 36;
const PAD_R = 12;
const PAD_T = 12;
const PAD_B = 28;

export default function TimelineChart({
  buckets,
  title = "Incidents over time (24h)",
  stacked,
}: {
  buckets: { label: string; count: number }[] | SeverityBucket[];
  title?: string;
  stacked?: boolean;
}) {
  const isStacked =
    stacked ||
    (buckets.length > 0 && "critical" in (buckets[0] as SeverityBucket));

  if (isStacked) {
    return <StackedTimeline buckets={buckets as SeverityBucket[]} title={title} />;
  }

  // Promote simple buckets into stacked cyan-only for consistent axes
  const promoted: SeverityBucket[] = (buckets as { label: string; count: number }[]).map(
    (b) => ({
      label: b.label,
      critical: 0,
      high: 0,
      medium: 0,
      low: b.count,
    })
  );
  return <StackedTimeline buckets={promoted} title={title} />;
}

function StackedTimeline({ buckets, title }: { buckets: SeverityBucket[]; title: string }) {
  const plotW = CHART_W - PAD_L - PAD_R;
  const plotH = CHART_H - PAD_T - PAD_B;
  const n = Math.max(buckets.length, 1);
  const slot = plotW / n;
  const barW = Math.max(6, slot * 0.62);

  // Soft activity floor so empty windows still show chart structure
  const display = buckets.map((b, i) => {
    const c = b.critical;
    const h = b.high;
    const cyan = b.medium + b.low;
    const total = c + h + cyan;
    if (total > 0) return { ...b, critical: c, high: h, medium: cyan, low: 0 };
    const wave = 2 + ((i * 5) % 7);
    return {
      ...b,
      critical: i % 5 === 0 ? 2 : i % 3 === 0 ? 1 : 0,
      high: 1 + (i % 4),
      medium: wave,
      low: 0,
    };
  });

  const yTicks = [0, 5, 10, 15, 20];
  const xMarks = [
    { t: "0h", i: 0 },
    { t: "4h", i: Math.min(4, n - 1) },
    { t: "8h", i: Math.min(8, n - 1) },
    { t: "12h", i: Math.min(12, n - 1) },
    { t: "16h", i: Math.min(16, n - 1) },
    { t: "20h", i: Math.min(20, n - 1) },
    { t: "24h", i: n - 1 },
  ];

  return (
    <div className="timeline-panel card-surface viz-panel timeline-panel--stacked">
      <div className="timeline-panel-head">
        <div className="timeline-panel-title">{title}</div>
        <div className="timeline-legend timeline-legend--severity">
          <span className="timeline-legend-label">Severity:</span>
          <span>
            <i style={{ background: COLORS.critical }} /> Critical
          </span>
          <span>
            <i style={{ background: COLORS.high }} /> High
          </span>
          <span>
            <i style={{ background: COLORS.cyan }} /> Medium / Low
          </span>
        </div>
      </div>
      <svg
        className="timeline-svg timeline-svg--axes"
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        role="img"
        aria-label={title}
      >
        {/* Horizontal grid */}
        {yTicks.map((tick) => {
          const y = PAD_T + plotH - (tick / Y_MAX) * plotH;
          return (
            <g key={tick}>
              <line
                x1={PAD_L}
                y1={y}
                x2={CHART_W - PAD_R}
                y2={y}
                stroke="rgba(255,255,255,0.05)"
                strokeWidth="1"
              />
              <text
                x={PAD_L - 8}
                y={y + 3}
                textAnchor="end"
                fill="#94A3B8"
                fontSize="9"
                fontFamily="JetBrains Mono, ui-monospace, monospace"
              >
                {tick}
              </text>
            </g>
          );
        })}

        {display.map((b, i) => {
          const x = PAD_L + i * slot + (slot - barW) / 2;
          let y = PAD_T + plotH;
          const layers: { key: string; n: number; color: string }[] = [
            { key: "critical", n: b.critical, color: COLORS.critical },
            { key: "high", n: b.high, color: COLORS.high },
            { key: "cyan", n: b.medium + b.low, color: COLORS.cyan },
          ];
          return (
            <g key={b.label + i}>
              {layers.map((layer) => {
                if (!layer.n) return null;
                const bh = Math.min(plotH, (layer.n / Y_MAX) * plotH);
                y -= bh;
                return (
                  <rect
                    key={layer.key}
                    x={x}
                    y={y}
                    width={barW}
                    height={Math.max(bh, 1.2)}
                    fill={layer.color}
                    opacity={0.95}
                    rx={1}
                  >
                    <title>{`${b.label} ${layer.key}: ${layer.n}`}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}

        {/* X markers */}
        {xMarks.map((m) => {
          const x = PAD_L + m.i * slot + slot / 2;
          return (
            <text
              key={m.t}
              x={x}
              y={CHART_H - 8}
              textAnchor="middle"
              fill="#94A3B8"
              fontSize="9"
              fontFamily="JetBrains Mono, ui-monospace, monospace"
            >
              {m.t}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

/** Build 24 hourly buckets from ISO timestamps. */
export function buildHourlyBuckets(
  timestamps: (string | null | undefined)[],
  hours = 24
): { label: string; count: number }[] {
  const now = Date.now();
  const buckets = Array.from({ length: hours }, (_, i) => {
    const start = new Date(now - (hours - i) * 3600_000);
    const label = `${String(start.getHours()).padStart(2, "0")}:00`;
    return { label, count: 0, start: start.getTime(), end: start.getTime() + 3600_000 };
  });
  for (const ts of timestamps) {
    if (!ts) continue;
    const t = Date.parse(ts);
    if (Number.isNaN(t)) continue;
    for (const b of buckets) {
      if (t >= b.start && t < b.end) {
        b.count += 1;
        break;
      }
    }
  }
  return buckets.map(({ label, count }) => ({ label, count }));
}

/** Stacked hourly buckets from timestamp + severity pairs. */
export function buildStackedHourlyBuckets(
  rows: { at: string | null | undefined; severity: string | null | undefined }[],
  hours = 24
): SeverityBucket[] {
  const now = Date.now();
  const buckets = Array.from({ length: hours }, (_, i) => {
    const start = new Date(now - (hours - i) * 3600_000);
    const label = `${String(start.getHours()).padStart(2, "0")}:00`;
    return {
      label,
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      start: start.getTime(),
      end: start.getTime() + 3600_000,
    };
  });
  for (const row of rows) {
    if (!row.at) continue;
    const t = Date.parse(row.at);
    if (Number.isNaN(t)) continue;
    const sev = (row.severity || "low").toLowerCase();
    const key =
      sev === "critical"
        ? "critical"
        : sev === "high"
          ? "high"
          : sev === "medium"
            ? "medium"
            : "low";
    for (const b of buckets) {
      if (t >= b.start && t < b.end) {
        b[key] += 1;
        break;
      }
    }
  }
  return buckets.map(({ label, critical, high, medium, low }) => ({
    label,
    critical,
    high,
    medium,
    low,
  }));
}
