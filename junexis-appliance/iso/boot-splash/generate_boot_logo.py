#!/usr/bin/env python3
"""Generate Junexis Appliance boot splash (1920x1080).

Branding (locked):
  - JUNEXIS APPLIANCE — yellow→red mix (website amber #F59E0B + deep red)
  - Your Dedicated SOC Sentinel — white
  - Pure black background, Proxmox-style minimal
  - Includes improvised radar mark inspired by website-junexis/assets/mark.svg

Usage:
  python3 generate_boot_logo.py [/path/to/output.png]
Default output (dev tree):
  ./junexis-boot.png  (next to this script)
On appliance firstboot / chroot:
  /usr/share/plymouth/themes/junexis/junexis-boot.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow required: pip install Pillow") from exc

# Website palette (website-junexis/css/styles.css)
AMBER = (245, 158, 11)       # --amber #F59E0B
AMBER_DEEP = (217, 119, 6)   # --amber-deep
RED = (220, 38, 38)          # enterprise red mix
WHITE = (248, 250, 252)      # --text #F8FAFC
CYAN = (56, 189, 248)        # --cyan mark accents
BLACK = (0, 0, 0)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def draw_brand_gradient_text(
    base: Image.Image,
    text: str,
    center: tuple[int, int],
    font: ImageFont.ImageFont,
) -> None:
    """Draw text with left→right yellow-to-red fill (yellow+red mixed brand)."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Measure
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x0 = center[0] - tw // 2
    y0 = center[1] - th // 2
    # Gradient strip
    grad = Image.new("RGB", (max(tw, 1), max(th, 1)))
    gp = grad.load()
    for x in range(grad.size[0]):
        # amber → amber-deep → red
        t = x / max(grad.size[0] - 1, 1)
        if t < 0.55:
            color = _lerp(AMBER, AMBER_DEEP, t / 0.55)
        else:
            color = _lerp(AMBER_DEEP, RED, (t - 0.55) / 0.45)
        for y in range(grad.size[1]):
            gp[x, y] = color
    mask = Image.new("L", grad.size, 0)
    ImageDraw.Draw(mask).text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    overlay.paste(grad, (x0, y0), mask)
    base.alpha_composite(overlay)


def draw_radar_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float = 3.2) -> None:
    """Improvised mark from website mark.svg (radar ring + crosshair)."""
    r = int(11 * scale)
    # outer ring amber
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=AMBER, width=max(2, int(1.75 * scale / 2)))
    # core
    cr = int(3.5 * scale)
    draw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=AMBER)
    # cyan ticks
    tick = int(5 * scale)
    w = max(2, int(1.4 * scale / 2))
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        draw.line(
            (cx + dx * (r - tick), cy + dy * (r - tick), cx + dx * (r + tick // 2), cy + dy * (r + tick // 2)),
            fill=CYAN,
            width=w,
        )
    for dx, dy in ((-1, -1), (1, 1), (-1, 1), (1, -1)):
        draw.line(
            (
                cx + int(dx * r * 0.55),
                cy + int(dy * r * 0.55),
                cx + int(dx * r * 0.85),
                cy + int(dy * r * 0.85),
            ),
            fill=CYAN,
            width=w,
        )


def generate(out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (1920, 1080), (*BLACK, 255))
    draw = ImageDraw.Draw(img)

    # Mark above brand
    draw_radar_mark(draw, 960, 390, scale=3.4)

    brand_font = _font(64, bold=True)
    tag_font = _font(28, bold=False)

    draw_brand_gradient_text(img, "JUNEXIS APPLIANCE", (960, 520), brand_font)

    # Tagline white (reversed from earlier yellow)
    draw.text((960, 600), "Your Dedicated SOC Sentinel", fill=WHITE, font=tag_font, anchor="mm")

    # Subtle gold rule under tagline
    draw.line((760, 640, 1160, 640), fill=AMBER_DEEP, width=2)

    rgb = img.convert("RGB")
    rgb.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    else:
        # Default: write beside script; also support appliance path when run as root in chroot
        here = Path(__file__).resolve().parent
        appliance_default = Path("/usr/share/plymouth/themes/junexis/junexis-boot.png")
        out = appliance_default if os.geteuid() == 0 and str(here).startswith("/usr") else here / "junexis-boot.png"
    path = generate(out)
    print(f"BOOT_LOGO_OK {path}")


if __name__ == "__main__":
    main()
