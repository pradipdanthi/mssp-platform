import FalconMark from "../../assets/images/kestrel_falcon_shield_mark.png";

interface Props {
  className?: string;
  /** Width in px; height follows the full emblem aspect (tail included). */
  size?: number;
  title?: string;
}

/**
 * Full falcon + shield mark (tight crop, high-res — no empty canvas padding).
 */
export default function KestrelFalconShieldLogo({
  className = "",
  size = 132,
  title = "Kestrel Cyber",
}: Props) {
  return (
    <img
      src={FalconMark}
      alt={title}
      width={size}
      className={`kestrel-falcon-shield-logo ${className}`.trim()}
      draggable={false}
      decoding="async"
    />
  );
}
