import { useBrand } from "../../config/BrandContext";

interface Props {
  className?: string;
  /** Display width in px; height follows the locked SVG aspect ratio. */
  size?: number;
  title?: string;
  /** "logo" = horizontal lockup (default); "mark" = shield-only. */
  variant?: "logo" | "mark";
}

/**
 * Locked Kevantic brand graphic from packages/brand (via public/brand + app-config).
 * Never reconstruct the wordmark with HTML/CSS text.
 */
export default function KestrelFalconShieldLogo({
  className = "",
  size = 200,
  title,
  variant = "logo",
}: Props) {
  const brand = useBrand();
  const alt = title ?? brand.logo.alt ?? "Kevantic Cyber Security";
  const src = variant === "mark" ? brand.logo.markSrc : brand.logo.logoSrc;
  const width = variant === "mark" ? Math.min(size, 48) : size;

  return (
    <img
      src={src}
      alt={variant === "mark" && className.includes("decorative") ? "" : alt}
      width={width}
      className={`kevantic-shield-logo kevantic-lockup ${variant === "mark" ? "kevantic-brand-mark" : "kevantic-brand-logo"} ${className}`.trim()}
      draggable={false}
      decoding="async"
      style={{ height: "auto", objectFit: "contain" }}
    />
  );
}
