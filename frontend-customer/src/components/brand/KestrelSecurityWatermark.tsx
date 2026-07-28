import FalconWatermark from "../../assets/images/kestrel_falcon_shield_watermark.png";

/**
 * Large subtle falcon/shield watermark for military-grade SOC chrome.
 */
export default function KestrelSecurityWatermark() {
  return (
    <div className="kestrel-security-watermark" aria-hidden="true">
      <img src={FalconWatermark} alt="" className="kestrel-security-watermark-img" />
      <div className="kestrel-security-watermark-vignette" />
    </div>
  );
}
