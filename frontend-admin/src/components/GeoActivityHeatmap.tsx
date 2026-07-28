import { useId, useMemo } from "react";
import {
  WORLD_LAND_PATHS,
  WORLD_MAP_HEIGHT,
  WORLD_MAP_VIEWBOX,
  WORLD_MAP_WIDTH,
  projectLonLat,
} from "./worldMapPaths";

/**
 * Log Source Anomaly Heatmap — Natural Earth equirectangular land + fused heat-glow.
 * Anomaly heatmap overlay for SOC operations (aggregated hubs — not raw IP geolocation).
 */

export type HeatSpot = {
  id: string;
  label: string;
  intensity: number;
  /** Equirectangular SVG x (0–1000). Prefer lon/lat via hubFromLonLat. */
  x: number;
  y: number;
};

type Props = {
  title?: string;
  spots?: HeatSpot[];
  footnote?: string;
  liveTick?: number;
};

type LonLatHub = {
  id: string;
  label: string;
  intensity: number;
  lon: number;
  lat: number;
};

const LON_LAT_HUBS: LonLatHub[] = [
  { id: "us-west", label: "US West Coast", intensity: 0.72, lon: -122.4, lat: 37.8 },
  { id: "us-east", label: "US East Coast", intensity: 0.85, lon: -74.0, lat: 40.7 },
  { id: "brazil", label: "South America", intensity: 0.4, lon: -46.6, lat: -23.5 },
  { id: "eu-west", label: "Western Europe", intensity: 0.95, lon: 2.3, lat: 48.9 },
  { id: "eu-central", label: "Central Europe", intensity: 0.88, lon: 13.4, lat: 52.5 },
  { id: "mea", label: "Middle East", intensity: 0.48, lon: 55.3, lat: 25.2 },
  { id: "safrica", label: "Southern Africa", intensity: 0.35, lon: 28.0, lat: -26.2 },
  { id: "india", label: "South Asia", intensity: 0.9, lon: 77.2, lat: 28.6 },
  { id: "seasia", label: "SE Asia", intensity: 0.55, lon: 106.8, lat: -6.2 },
  { id: "east-asia", label: "East Asia", intensity: 0.78, lon: 121.5, lat: 31.2 },
  { id: "japan", label: "Japan", intensity: 0.5, lon: 139.7, lat: 35.7 },
];

function hubFromLonLat(h: LonLatHub): HeatSpot {
  const { x, y } = projectLonLat(h.lon, h.lat);
  return { id: h.id, label: h.label, intensity: h.intensity, x, y };
}

export const DEFAULT_HUBS: HeatSpot[] = LON_LAT_HUBS.map(hubFromLonLat);

export function hubsFromActivity(score: number, liveTick = 0): HeatSpot[] {
  const base = Math.min(1, Math.max(0.35, 0.45 + score / 50));
  return LON_LAT_HUBS.map((h, i) => {
    const wobble = liveTick ? 0.03 * Math.sin(liveTick / 2 + i) : 0;
    return hubFromLonLat({
      ...h,
      intensity: Math.min(1, Math.max(0.28, h.intensity * base + wobble)),
    });
  });
}

function hash01(n: number): number {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

type HeatNode = {
  cx: number;
  cy: number;
  r: number;
  layer: "bloom" | "mid" | "core";
};

/**
 * Dense overlapping discs per hub. Soft blur merges them into continuous heat glow.
 * High-intensity hubs (Europe / South Asia) get cream cores.
 */
function buildHeatNodes(spot: HeatSpot, liveTick: number): HeatNode[] {
  const dense = spot.intensity >= 0.82;
  const count = Math.round(10 + spot.intensity * (dense ? 28 : 18));
  const spread = 10 + spot.intensity * (dense ? 42 : 28);
  const nodes: HeatNode[] = [];

  // Outer bloom field (large, soft) — fuses under feGaussianBlur
  for (let i = 0; i < count; i++) {
    const a = hash01(spot.x * 11 + spot.y * 5 + i * 19 + liveTick * 0.015) * Math.PI * 2;
    const d = Math.pow(hash01(i * 17 + spot.x + 3), 0.5) * spread;
    nodes.push({
      cx: spot.x + Math.cos(a) * d,
      cy: spot.y + Math.sin(a) * d * 0.58,
      r: 7 + hash01(i * 3 + 2) * (6 + spot.intensity * 10),
      layer: "bloom",
    });
  }

  // Mid cyan ring
  const midCount = Math.round(6 + spot.intensity * 12);
  for (let i = 0; i < midCount; i++) {
    const a = hash01(i * 23 + spot.y) * Math.PI * 2;
    const d = Math.pow(hash01(i * 9 + 1), 0.6) * spread * 0.55;
    nodes.push({
      cx: spot.x + Math.cos(a) * d,
      cy: spot.y + Math.sin(a) * d * 0.55,
      r: 3.5 + hash01(i + 8) * (3 + spot.intensity * 4),
      layer: "mid",
    });
  }

  // Hot cream nucleus for peak clusters
  if (spot.intensity >= 0.65) {
    const cores = dense ? 7 : 4;
    for (let j = 0; j < cores; j++) {
      nodes.push({
        cx: spot.x + (hash01(j + 40) - 0.5) * (dense ? 14 : 8),
        cy: spot.y + (hash01(j + 55) - 0.5) * (dense ? 10 : 6),
        r: 2.8 + spot.intensity * 2.2 - j * 0.15,
        layer: "core",
      });
    }
  }

  return nodes;
}

function WorldLand() {
  return (
    <g className="geo-world-land" aria-hidden>
      <rect
        width={WORLD_MAP_WIDTH}
        height={WORLD_MAP_HEIGHT}
        fill="#0B0F17"
      />
      {WORLD_LAND_PATHS.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="#121824"
          stroke="#1E293B"
          strokeWidth={0.5}
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  );
}

export default function GeoActivityHeatmap({
  title = "Log Source Anomaly Heatmap",
  spots = DEFAULT_HUBS,
  footnote = "Aggregated log-source anomaly overlay — not raw customer IP geolocation.",
  liveTick = 0,
}: Props) {
  const uid = useId().replace(/:/g, "");
  const glowId = `${uid}-heat-glow`;
  const softGlowId = `${uid}-heat-soft`;
  const cyanGrad = `${uid}-cyan`;
  const hotGrad = `${uid}-hot`;

  const clusters = useMemo(
    () => spots.map((s) => ({ spot: s, nodes: buildHeatNodes(s, liveTick) })),
    [spots, liveTick]
  );
  const peak = Math.round(Math.max(...spots.map((s) => s.intensity), 0) * 100);

  return (
    <div className="geo-heatmap card-surface viz-panel">
      <div className="geo-heatmap-head">
        <div className="geo-heatmap-title">{title}</div>
        <div className="geo-heatmap-overlay-legend" aria-label="Log anomaly volume legend">
          <div className="geo-legend-title">Log Anomaly Volume</div>
          <div className="geo-legend-scale">
            <span className="geo-legend-swatch geo-legend-swatch--low" />
            Low
            <span className="geo-legend-swatch geo-legend-swatch--mid" />
            Med
            <span className="geo-legend-swatch geo-legend-swatch--high" />
            High
          </div>
          <div className="geo-legend-peak cell-mono">
            Peak {peak}%{liveTick > 0 ? " · live" : ""}
          </div>
        </div>
      </div>
      <div className="geo-heatmap-stage">
        <svg
          className="geo-heatmap-svg"
          viewBox={WORLD_MAP_VIEWBOX}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={title}
        >
          <defs>
            <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
              <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id={softGlowId} x="-80%" y="-80%" width="260%" height="260%" colorInterpolationFilters="sRGB">
              <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
              </feMerge>
            </filter>
            <radialGradient id={cyanGrad} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#E0FFFF" stopOpacity="0.95" />
              <stop offset="45%" stopColor="#00F0FF" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#00F0FF" stopOpacity="0" />
            </radialGradient>
            <radialGradient id={hotGrad} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#FFFFF0" stopOpacity="1" />
              <stop offset="30%" stopColor="#E8FFC8" stopOpacity="0.95" />
              <stop offset="65%" stopColor="#7CF5FF" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#00F0FF" stopOpacity="0" />
            </radialGradient>
          </defs>

          <WorldLand />

          {/* Soft ambient bloom (fuses neighboring hubs) */}
          <g className="geo-heat-layer geo-heat-layer--soft" filter={`url(#${softGlowId})`} opacity={0.55}>
            {clusters.map(({ spot, nodes }) =>
              nodes
                .filter((n) => n.layer === "bloom")
                .map((n, idx) => (
                  <circle
                    key={`${spot.id}-b-${idx}`}
                    cx={n.cx}
                    cy={n.cy}
                    r={n.r * 1.15}
                    fill={`url(#${cyanGrad})`}
                    opacity={0.35 + spot.intensity * 0.35}
                  />
                ))
            )}
          </g>

          {/* Primary fused heat layer */}
          <g className="geo-heat-layer" filter={`url(#${glowId})`}>
            {clusters.map(({ spot, nodes }) => (
              <g key={spot.id}>
                {nodes
                  .filter((n) => n.layer === "bloom" || n.layer === "mid")
                  .map((n, idx) => (
                    <circle
                      key={`${spot.id}-m-${idx}`}
                      cx={n.cx}
                      cy={n.cy}
                      r={n.layer === "mid" ? n.r : n.r * 0.85}
                      fill={`url(#${cyanGrad})`}
                      opacity={n.layer === "mid" ? 0.7 : 0.45 + spot.intensity * 0.3}
                    />
                  ))}
                <title>{`${spot.label}: ${Math.round(spot.intensity * 100)}%`}</title>
              </g>
            ))}
          </g>

          {/* Cream peak cores */}
          <g className="geo-heat-layer" filter={`url(#${glowId})`}>
            {clusters.map(({ spot, nodes }) =>
              nodes
                .filter((n) => n.layer === "core")
                .map((n, idx) => (
                  <circle
                    key={`${spot.id}-c-${idx}`}
                    cx={n.cx}
                    cy={n.cy}
                    r={n.r}
                    fill={`url(#${hotGrad})`}
                    opacity={0.95}
                  />
                ))
            )}
          </g>
        </svg>
      </div>
      <p className="geo-heatmap-foot">{footnote}</p>
    </div>
  );
}
