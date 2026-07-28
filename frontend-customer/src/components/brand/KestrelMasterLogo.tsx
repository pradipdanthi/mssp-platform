import MasterEmblemPNG from "../../assets/images/kestrel_master_emblem.jpg";
import MasterLogoPNG from "../../assets/images/kestrel_cyber_master_logo.png";

interface KestrelMasterLogoProps {
  className?: string;
  /** Outer frame size for mark variant (default 56px / w-14). */
  size?: string;
  /**
   * mark — standalone falcon/shield emblem (sidebar / login).
   * full — PNG lockup including wordmark.
   */
  variant?: "mark" | "full";
  alt?: string;
  /** Live-feed pulse LED (green) in the mark frame corner. */
  live?: boolean;
}

/**
 * Kestrel brand mark — renders the standalone master emblem asset directly
 * (no CSS crop / object-position math). Full variant keeps the wordmark lockup.
 */
export default function KestrelMasterLogo({
  className = "",
  size = "56px",
  variant = "mark",
  alt = "Kestrel Cyber Master Emblem",
  live = false,
}: KestrelMasterLogoProps) {
  if (variant === "full") {
    return (
      <img
        src={MasterLogoPNG}
        alt={alt}
        className={`kestrel-master-logo kestrel-master-logo--full ${className}`.trim()}
        style={{ width: size, height: "auto", objectFit: "contain", display: "block" }}
      />
    );
  }

  return (
    <div
      className={
        "kestrel-master-logo-frame kestrel-master-logo-frame--emblem brand-mark sidebar-brand-logo group" +
        (live ? " is-live" : "") +
        (className ? ` ${className}` : "")
      }
      style={{ width: size, height: size }}
    >
      {/* Ambient glow */}
      <div className="kestrel-emblem-core-glow" aria-hidden="true" />
      {/* Standalone master emblem — full asset, no cropping */}
      <img
        src={MasterEmblemPNG}
        alt={alt}
        className="kestrel-master-emblem-img"
      />
      {live ? <span className="kestrel-emblem-live-led" aria-hidden="true" /> : null}
    </div>
  );
}
