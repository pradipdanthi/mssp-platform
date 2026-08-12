import type { ReactNode } from "react";

/** Crisp 24px stroke icons for sidebar nav (inline SVG — no icon package). */
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
      className="sidebar-nav-icon"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

const ICONS: Record<string, ReactNode> = {
  home: (
    <Svg>
      <path {...STROKE} d="M3 10.5 12 3l9 7.5" />
      <path {...STROKE} d="M5.5 9.5V21h13V9.5" />
      <path {...STROKE} d="M9.5 21v-7h5v7" />
    </Svg>
  ),
  users: (
    <Svg>
      <path {...STROKE} d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle {...STROKE} cx="9" cy="7" r="3.5" />
      <path {...STROKE} d="M22 21v-2a3.5 3.5 0 0 0-2.5-3.35" />
      <path {...STROKE} d="M16.5 3.6a3.5 3.5 0 0 1 0 6.8" />
    </Svg>
  ),
  user: (
    <Svg>
      <path {...STROKE} d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle {...STROKE} cx="12" cy="7" r="3.5" />
    </Svg>
  ),
  monitor: (
    <Svg>
      <rect {...STROKE} x="2.5" y="3.5" width="19" height="13" rx="2" />
      <path {...STROKE} d="M8 21h8M12 16.5V21" />
    </Svg>
  ),
  search: (
    <Svg>
      <circle {...STROKE} cx="11" cy="11" r="6.5" />
      <path {...STROKE} d="m20 20-3.5-3.5" />
    </Svg>
  ),
  shield: (
    <Svg>
      <path
        {...STROKE}
        d="M12 2.5 4.5 5.5v6.2c0 4.6 3.1 8.8 7.5 10.1 4.4-1.3 7.5-5.5 7.5-10.1V5.5L12 2.5Z"
      />
    </Svg>
  ),
  server: (
    <Svg>
      <rect {...STROKE} x="3" y="3.5" width="18" height="6" rx="1.5" />
      <rect {...STROKE} x="3" y="14.5" width="18" height="6" rx="1.5" />
      <path {...STROKE} d="M7 6.5h.01M7 17.5h.01" />
    </Svg>
  ),
  bell: (
    <Svg>
      <path {...STROKE} d="M6.5 9.5a5.5 5.5 0 0 1 11 0c0 6 2.5 7 2.5 7H4s2.5-1 2.5-7" />
      <path {...STROKE} d="M10 20a2 2 0 0 0 4 0" />
    </Svg>
  ),
  alert: (
    <Svg>
      <path {...STROKE} d="M12 3.5 21 19H3L12 3.5Z" />
      <path {...STROKE} d="M12 10v4M12 16.5h.01" />
    </Svg>
  ),
  bug: (
    <Svg>
      <path {...STROKE} d="M8 13h8M9 9.5a3 3 0 0 1 6 0v8a3 3 0 0 1-6 0v-8Z" />
      <path {...STROKE} d="M5 10l2.5 1.5M19 10l-2.5 1.5M5 17l2.5-1.5M19 17l-2.5-1.5" />
    </Svg>
  ),
  check: (
    <Svg>
      <path {...STROKE} d="M9 12.5 11 14.5 15.5 9.5" />
      <circle {...STROKE} cx="12" cy="12" r="8.5" />
    </Svg>
  ),
  chart: (
    <Svg>
      <path {...STROKE} d="M4 19.5h16" />
      <path {...STROKE} d="M7 16.5v-5M12 16.5V7.5M17 16.5v-8" />
    </Svg>
  ),
  mail: (
    <Svg>
      <rect {...STROKE} x="3" y="5" width="18" height="14" rx="2" />
      <path {...STROKE} d="m3.5 7 8.5 6 8.5-6" />
    </Svg>
  ),
  clipboard: (
    <Svg>
      <rect {...STROKE} x="6" y="5" width="12" height="16" rx="2" />
      <path {...STROKE} d="M9 5.5V4.5a2 2 0 0 1 2-1h2a2 2 0 0 1 2 1v1" />
    </Svg>
  ),
  book: (
    <Svg>
      <path {...STROKE} d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5V5.5Z" />
      <path {...STROKE} d="M4 19.5h14" />
    </Svg>
  ),
  globe: (
    <Svg>
      <circle {...STROKE} cx="12" cy="12" r="8.5" />
      <path {...STROKE} d="M3.5 12h17M12 3.5c2.5 2.8 2.5 14.2 0 17M12 3.5c-2.5 2.8-2.5 14.2 0 17" />
    </Svg>
  ),
  cloud: (
    <Svg>
      <path
        {...STROKE}
        d="M7.5 18.5h10a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.6 1.5A3.5 3.5 0 0 0 7.5 18.5Z"
      />
    </Svg>
  ),
  network: (
    <Svg>
      <circle {...STROKE} cx="6" cy="6" r="2.2" />
      <circle {...STROKE} cx="18" cy="6" r="2.2" />
      <circle {...STROKE} cx="12" cy="18" r="2.2" />
      <path {...STROKE} d="M8 7.2 10.5 16M16 7.2 13.5 16M8.2 6h7.6" />
    </Svg>
  ),
  eye: (
    <Svg>
      <path {...STROKE} d="M2.5 12S6.5 5.5 12 5.5 21.5 12 21.5 12 17.5 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle {...STROKE} cx="12" cy="12" r="3" />
    </Svg>
  ),
  lens: (
    <Svg>
      <circle {...STROKE} cx="11" cy="11" r="6.5" />
      <path {...STROKE} d="m20 20-3.2-3.2M8.5 11h5M11 8.5v5" />
    </Svg>
  ),
  settings: (
    <Svg>
      <circle {...STROKE} cx="12" cy="12" r="3" />
      <path
        {...STROKE}
        d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V20a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H4a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H10a1.7 1.7 0 0 0 1-1.5V4a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V10c.3.6.9 1 1.5 1H20a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"
      />
    </Svg>
  ),
  layers: (
    <Svg>
      <path {...STROKE} d="m12 3.5 8 4.5-8 4.5-8-4.5 8-4.5Z" />
      <path {...STROKE} d="m4 12.5 8 4.5 8-4.5M4 16.5l8 4.5 8-4.5" />
    </Svg>
  ),
  file: (
    <Svg>
      <path {...STROKE} d="M14 3.5H7.5A2 2 0 0 0 5.5 5.5v13A2 2 0 0 0 7.5 20.5h9a2 2 0 0 0 2-2V9L14 3.5Z" />
      <path {...STROKE} d="M14 3.5V9h5.5" />
    </Svg>
  ),
};

const ROUTE_ICON: Record<string, keyof typeof ICONS> = {
  "/dashboard": "home",
  "/tenants": "users",
  "/users": "user",
  "/appliances": "monitor",
  "/retrospective-hunts": "search",
  "/threat-intel": "shield",
  "/ai-assistant": "lens",
  "/assets": "server",
  "/alerts": "bell",
  "/incidents": "alert",
  "/vulnerabilities": "bug",
  "/recommendations": "check",
  "/reports": "chart",
  "/notifications": "mail",
  "/audit": "clipboard",
  "/service-requests": "file",
  "/services": "book",
  "/compliance": "clipboard",
  "/easm": "globe",
  "/itdr": "cloud",
  "/ndr": "network",
  "/threatlens": "lens",
  "/forensics": "eye",
  "/account": "settings",
};

export default function NavIcon({ to }: { to: string }) {
  const key = ROUTE_ICON[to] ?? "layers";
  return <>{ICONS[key]}</>;
}
