import { useBrand } from "../../config/BrandContext";

interface Props {
  className?: string;
  size?: number;
  title?: string;
  variant?: "logo" | "mark";
}

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
