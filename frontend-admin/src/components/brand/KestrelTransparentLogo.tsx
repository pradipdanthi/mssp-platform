import { useId } from "react";

interface LogoProps {
  className?: string;
  size?: number;
  title?: string;
}

/**
 * Apex Falcon Shield — transparent SVG mark (no raster asset, no background box).
 */
export default function KestrelTransparentLogo({
  className = "",
  size = 48,
  title = "Kevantic Cyber Security",
}: LogoProps) {
  const uid = useId().replace(/:/g, "");
  const glowId = `falcon-cyan-glow-${uid}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`kestrel-transparent-logo shrink-0 ${className}`.trim()}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <defs>
        <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* SHIELD PERIMETER */}
      <path
        d="M64 8 L114 28 L104 92 L64 120 L24 92 L14 28 Z"
        fill="none"
        stroke="#00AEEF"
        strokeWidth="3"
        strokeLinejoin="round"
        filter={`url(#${glowId})`}
      />

      {/* SHIELD INNER MESH ACCENTS */}
      <path
        d="M64 16 L104 32 L96 86 L64 110 L32 86 L24 32 Z"
        fill="none"
        stroke="#00AEEF"
        strokeWidth="1"
        strokeOpacity="0.3"
        strokeLinejoin="round"
      />

      {/* FALCON GEOMETRY & HEAD */}
      <g stroke="#00AEEF" strokeWidth="2" fill="none" filter={`url(#${glowId})`}>
        <path
          d="M64 30 L82 36 L94 50 L82 64 L64 70 L46 64 L34 50 L46 36 Z"
          fill="#00AEEF"
          fillOpacity="0.15"
        />
        <path d="M86 44 L102 50 L90 56 L82 50 Z" fill="#FFFFFF" stroke="#FFFFFF" strokeWidth="1" />
        <path d="M40 52 L12 66 M40 52 L22 88 M40 52 L30 102" strokeWidth="2.5" />
        <path d="M88 52 L116 66 M88 52 L106 88 M88 52 L98 102" strokeWidth="2.5" />
        <path d="M64 70 L50 86 L64 100 L78 86 Z" fill="#00AEEF" fillOpacity="0.2" />
        <path d="M64 100 L64 116" strokeWidth="2" />
      </g>
    </svg>
  );
}
