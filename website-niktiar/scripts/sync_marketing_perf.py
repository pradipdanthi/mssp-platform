#!/usr/bin/env python3
"""Non-blocking Google Fonts + stable asset versions across marketing HTML."""
from __future__ import annotations

import re
from pathlib import Path

ROOTS = [
    Path("/opt/mssp-control/website-niktiar"),
    Path("/home/secadmin/kevantic-website"),
]

FONT_BLOCK_OLD = re.compile(
    r'<link rel="preconnect" href="https://fonts\.googleapis\.com" />\s*'
    r'<link rel="preconnect" href="https://fonts\.gstatic\.com" crossorigin />\s*'
    r'<link href="https://fonts\.googleapis\.com/css2\?[^"]+" rel="stylesheet" />',
    re.S,
)

FONT_BLOCK_NEW = """<link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&amp;family=JetBrains+Mono:wght@400;500;600&amp;display=swap" onload="this.onload=null;this.rel='stylesheet'" />
  <noscript><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&amp;family=JetBrains+Mono:wght@400;500;600&amp;display=swap" rel="stylesheet" /></noscript>"""


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    text = FONT_BLOCK_OLD.sub(FONT_BLOCK_NEW, text)
    text = text.replace("js/app.js?v=7", "js/app.js?v=9")
    text = text.replace("../js/app.js?v=7", "../js/app.js?v=9")
    if path.name == "index.html":
        if 'rel="preload" href="css/styles.css' not in text:
            text = text.replace(
                '<link rel="stylesheet" href="css/styles.css?v=9" />',
                '<link rel="preload" href="css/styles.css?v=9" as="style" />\n'
                '  <link rel="stylesheet" href="css/styles.css?v=9" />',
            )
        text = text.replace(
            'src="assets/brand/kevantic-horizontal.svg?v=1.1.0"',
            'src="assets/brand/kevantic-horizontal.svg?v=1.1.0" fetchpriority="high" decoding="async"',
        )
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    n = 0
    for root in ROOTS:
        if not root.is_dir():
            continue
        for html in sorted(root.rglob("*.html")):
            if patch_file(html):
                print(f"patched {html}")
                n += 1
    print(f"Done. {n} files.")


if __name__ == "__main__":
    main()
