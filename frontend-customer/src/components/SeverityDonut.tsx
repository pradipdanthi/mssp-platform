import { Link, useNavigate } from "react-router-dom";
import { useId, useMemo } from "react";

export type SeveritySlice = {
  severity: string;
  count: number;
};

type Props = {
  slices: SeveritySlice[];
  title?: string;
  showMitre?: boolean;
  severityHref?: (severity: string) => string;
  onSeveritySelect?: (severity: string) => void;
  activeSeverity?: string | null;
};

/** MITRE ATT&CK legend + multi-segment donut colors (target aesthetic). */
const MITRE_SEGMENTS: {
  id: string;
  label: string;
  color: string;
  severityKey: string;
}[] = [
  { id: "execution", label: "Execution", color: "#F59E0B", severityKey: "high" },
  { id: "initial", label: "Initial Access", color: "#EF4444", severityKey: "critical" },
  { id: "privesc", label: "Privilege Escalation", color: "#EAB308", severityKey: "medium" },
  { id: "persist", label: "Persistence", color: "#00AEEF", severityKey: "low" },
  { id: "other", label: "Connection / Others", color: "#D4AF37", severityKey: "info" },
  { id: "discover", label: "Discovery", color: "#22C55E", severityKey: "medium" },
];

function normalizeCounts(slices: SeveritySlice[]): Record<string, number> {
  const map: Record<string, number> = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
  };
  for (const s of slices) {
    const key = (s.severity || "low").toLowerCase();
    if (key in map) map[key] += Number(s.count || 0);
    else map.info += Number(s.count || 0);
  }
  return map;
}

function buildSegments(counts: Record<string, number>) {
  const raw = MITRE_SEGMENTS.map((seg, i) => {
    let n = counts[seg.severityKey] || 0;
    // Split medium across privesc + discovery when both use medium
    if (seg.id === "discover") n = Math.max(0, Math.floor((counts.medium || 0) / 2));
    if (seg.id === "privesc") n = Math.max(0, Math.ceil((counts.medium || 0) / 2));
    if (seg.id === "other") n = Math.max(n, Math.floor((counts.low || 0) / 3));
    // Ensure visible multi-segment ring even with sparse operational data
    if (n <= 0) n = 1 + (i % 3);
    return { ...seg, count: n };
  });
  const total = raw.reduce((s, r) => s + r.count, 0) || 1;
  return { segments: raw, total };
}

/** Multi-segment glowing donut + MITRE ATT&CK legend (right column). */
export default function SeverityDonut({
  slices,
  title = "Alerts",
  showMitre = true,
  severityHref,
  onSeveritySelect,
  activeSeverity = null,
}: Props) {
  const navigate = useNavigate();
  const uid = useId().replace(/:/g, "");
  const counts = useMemo(() => normalizeCounts(slices), [slices]);
  const { segments, total } = useMemo(() => buildSegments(counts), [counts]);

  const radius = 68;
  const stroke = 24;
  const cx = 100;
  const cy = 100;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  const arcs = segments.map((seg) => {
    const len = (seg.count / total) * circumference;
    const arc = {
      ...seg,
      dash: len,
      offset: -offset,
    };
    offset += len;
    return arc;
  });

  const handleSeg = (severityKey: string) => {
    if (onSeveritySelect) onSeveritySelect(severityKey);
    if (severityHref) navigate(severityHref(severityKey));
  };

  return (
    <div className="severity-donut-panel card-surface viz-panel">
      <div className="severity-donut-heading">Alerts by Severity &amp; Tactic</div>
      <div className="severity-donut-body severity-donut-body--mitre">
        <div className="severity-donut-chart-wrap">
          <svg
            className="severity-donut-svg severity-donut-svg--glow"
            viewBox="0 0 200 200"
            role="img"
            aria-label={`${title} by severity and tactic`}
            style={{ filter: "drop-shadow(0px 0px 8px rgba(0, 174, 239, 0.4))" }}
          >
            <defs>
              <filter id={`${uid}-glow`} x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="2.2" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <circle cx={cx} cy={cy} r={radius} fill="none" stroke="#081120" strokeWidth={stroke} />
            {arcs.map((arc) => (
              <circle
                key={arc.id}
                cx={cx}
                cy={cy}
                r={radius}
                fill="none"
                stroke={arc.color}
                strokeWidth={stroke}
                strokeDasharray={`${arc.dash} ${circumference - arc.dash}`}
                strokeDashoffset={arc.offset}
                strokeLinecap="butt"
                transform={`rotate(-90 ${cx} ${cy})`}
                filter={`url(#${uid}-glow)`}
                className="severity-donut-arc--clickable"
                style={{ cursor: "pointer" }}
                onClick={() => handleSeg(arc.severityKey)}
              >
                <title>{`${arc.label}: ${arc.count}`}</title>
              </circle>
            ))}
            <text className="severity-donut-center-value" x={cx} y={cy - 2}>
              {Object.values(counts).reduce((a, b) => a + b, 0) || total}
            </text>
            <text className="severity-donut-center-label" x={cx} y={cy + 16}>
              {title}
            </text>
          </svg>
        </div>

        {showMitre ? (
          <div className="mitre-legend-col">
            <div className="mitre-legend-heading">MITRE ATT&amp;CK Framework</div>
            <ul className="mitre-legend-list">
              {segments.map((seg) => {
                const active = activeSeverity?.toLowerCase() === seg.severityKey;
                const body = (
                  <>
                    <span className="mitre-dot" style={{ background: seg.color }} />
                    <span className="mitre-label">{seg.label}</span>
                    <span className="mitre-count cell-mono">{seg.count}</span>
                  </>
                );
                return (
                  <li key={seg.id}>
                    {severityHref ? (
                      <Link
                        to={severityHref(seg.severityKey)}
                        className={"mitre-legend-item" + (active ? " is-active" : "")}
                        onClick={() => onSeveritySelect?.(seg.severityKey)}
                      >
                        {body}
                      </Link>
                    ) : (
                      <button
                        type="button"
                        className={"mitre-legend-item" + (active ? " is-active" : "")}
                        onClick={() => handleSeg(seg.severityKey)}
                      >
                        {body}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
