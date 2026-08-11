import { useBrand } from "../../config/BrandContext";

interface Props {
  className?: string;
  /** Display width in px; height follows the lockup aspect ratio (800×300). */
  size?: number;
  title?: string;
  /** "logo" = horizontal lockup (default); "mark" = shield-only. */
  variant?: "logo" | "mark";
}

/**
 * Kevantic brand graphic — horizontal lockup by default (app-config logoSrc).
 */
export default function KestrelFalconShieldLogo({
  className = "",
  size = 220,
  title,
  variant = "logo",
}: Props) {
  const brand = useBrand();
  const alt = title ?? brand.logo.alt;
  const src = variant === "mark" ? brand.logo.markSrc : brand.logo.logoSrc;

  return (
    <img
      src={src}
      alt={alt}
      width={size}
      className={`kevantic-shield-logo kevantic-lockup ${className}`.trim()}
      draggable={false}
      decoding="async"
    />
  );
}
