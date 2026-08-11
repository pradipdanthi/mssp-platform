import { useBrand } from "../../config/BrandContext";

interface Props {
  className?: string;
  size?: number;
  title?: string;
}

export default function KestrelFalconShieldLogo({
  className = "",
  size = 132,
  title,
}: Props) {
  const brand = useBrand();
  const alt = title ?? brand.logo.alt;

  return (
    <img
      src={brand.logo.markSrc}
      alt={alt}
      width={size}
      className={`kevantic-shield-logo ${className}`.trim()}
      draggable={false}
      decoding="async"
    />
  );
}
