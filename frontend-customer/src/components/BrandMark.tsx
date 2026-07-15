import { useEffect, useState } from "react";
import { useBrand } from "../config/BrandContext";

type BrandMarkVariant = "mark" | "logo";

interface BrandMarkProps {
  variant?: BrandMarkVariant;
  className?: string;
}

export default function BrandMark({ variant = "mark", className }: BrandMarkProps) {
  const brand = useBrand();
  const preferredSrc = variant === "logo" ? brand.logo.logoSrc : brand.logo.markSrc;
  const [src, setSrc] = useState(preferredSrc);

  useEffect(() => {
    setSrc(preferredSrc);
  }, [preferredSrc]);

  function handleError() {
    if (src !== brand.logo.markSrc) {
      setSrc(brand.logo.markSrc);
    }
  }

  return (
    <img
      className={className ?? (variant === "logo" ? "brand-logo" : "brand-mark")}
      src={src}
      alt={brand.logo.alt}
      onError={handleError}
    />
  );
}
