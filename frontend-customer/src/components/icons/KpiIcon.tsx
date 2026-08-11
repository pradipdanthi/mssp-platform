import type { ReactNode } from "react";

type KpiIconName =
  | "shield"
  | "activity"
  | "bell"
  | "monitor"
  | "inbox"
  | "database"
  | "search"
  | "check";

const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      className="kpi-glyph"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

const MAP: Record<KpiIconName, ReactNode> = {
  shield: (
    <Svg>
      <path
        {...STROKE}
        d="M12 2.5 4.5 5.5v6.2c0 4.6 3.1 8.8 7.5 10.1 4.4-1.3 7.5-5.5 7.5-10.1V5.5L12 2.5Z"
      />
    </Svg>
  ),
  activity: (
    <Svg>
      <path {...STROKE} d="M3 12h4l2.5-6 4 12 2.5-6H21" />
    </Svg>
  ),
  bell: (
    <Svg>
      <path {...STROKE} d="M6.5 9.5a5.5 5.5 0 0 1 11 0c0 6 2.5 7 2.5 7H4s2.5-1 2.5-7" />
      <path {...STROKE} d="M10 20a2 2 0 0 0 4 0" />
    </Svg>
  ),
  monitor: (
    <Svg>
      <rect {...STROKE} x="2.5" y="3.5" width="19" height="13" rx="2" />
      <path {...STROKE} d="M8 21h8M12 16.5V21" />
    </Svg>
  ),
  inbox: (
    <Svg>
      <path {...STROKE} d="M4 13h4l1.5 2.5h5L16 13h4" />
      <path {...STROKE} d="M4 13V6.5A2 2 0 0 1 6 4.5h12a2 2 0 0 1 2 2V13l-2.5 7H6.5L4 13Z" />
    </Svg>
  ),
  database: (
    <Svg>
      <ellipse {...STROKE} cx="12" cy="6" rx="7.5" ry="3" />
      <path {...STROKE} d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6" />
      <path {...STROKE} d="M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
    </Svg>
  ),
  search: (
    <Svg>
      <circle {...STROKE} cx="11" cy="11" r="6.5" />
      <path {...STROKE} d="m20 20-3.5-3.5" />
    </Svg>
  ),
  check: (
    <Svg>
      <path {...STROKE} d="M9 12.5 11 14.5 15.5 9.5" />
      <circle {...STROKE} cx="12" cy="12" r="8.5" />
    </Svg>
  ),
};

export default function KpiIcon({ name }: { name: KpiIconName }) {
  return <span className="kpi-icon-wrap">{MAP[name]}</span>;
}
