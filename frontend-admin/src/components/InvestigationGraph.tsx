import { useId } from "react";

/** Lightweight entity relationship graph for incident investigation context. */
export default function InvestigationGraph({
  title = "Investigation graph",
  entities = [
    { id: "user", label: "User", kind: "user" },
    { id: "host", label: "Host", kind: "host" },
    { id: "proc", label: "Process", kind: "process" },
    { id: "ip", label: "Network", kind: "network" },
  ],
}: {
  title?: string;
  entities?: { id: string; label: string; kind: string }[];
}) {
  const uid = useId().replace(/:/g, "");
  const pos: Record<string, { x: number; y: number }> = {
    user: { x: 90, y: 36 },
    host: { x: 200, y: 36 },
    proc: { x: 90, y: 110 },
    ip: { x: 200, y: 110 },
  };
  const edges: [string, string][] = [
    ["user", "host"],
    ["host", "proc"],
    ["proc", "ip"],
    ["user", "ip"],
  ];

  return (
    <div className="invest-graph">
      <div className="invest-graph-title">{title}</div>
      <svg viewBox="0 0 290 150" className="invest-graph-svg" role="img" aria-label={title}>
        <defs>
          <filter id={`${uid}-glow`} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {edges.map(([a, b]) => (
          <line
            key={a + b}
            x1={pos[a].x}
            y1={pos[a].y}
            x2={pos[b].x}
            y2={pos[b].y}
            stroke="#00AEEF"
            strokeOpacity="0.45"
            strokeWidth="1.5"
          />
        ))}
        {entities.map((e) => {
          const p = pos[e.id] || { x: 145, y: 75 };
          return (
            <g key={e.id} filter={`url(#${uid}-glow)`}>
              <circle cx={p.x} cy={p.y} r="22" fill="#101B2D" stroke="#00AEEF" strokeWidth="1.6" />
              <text
                x={p.x}
                y={p.y + 4}
                textAnchor="middle"
                fill="#F8FAFC"
                fontSize="10"
                fontFamily="Inter, sans-serif"
                fontWeight="600"
              >
                {e.label}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="invest-graph-foot">
        User → Host → Process / IP relational context for triage.
      </p>
    </div>
  );
}
