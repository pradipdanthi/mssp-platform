#!/usr/bin/env python3
"""Remove Google Fonts (~2MB) from marketing site — use system fonts."""
from __future__ import annotations

import re
from pathlib import Path

ROOTS = [
    Path("/opt/mssp-control/website-niktiar"),
    Path("/home/secadmin/kevantic-website"),
]

FONT_BLOCK = re.compile(
    r'<link rel="preconnect" href="https://fonts\.googleapis\.com" />\s*'
    r'<link rel="preconnect" href="https://fonts\.gstatic\.com" crossorigin />\s*'
    r'(?:<link rel="preload" as="style" href="https://fonts\.googleapis\.com/css2[^"]+" onload="[^"]+" />\s*'
    r'<noscript><link href="https://fonts\.googleapis\.com/css2[^"]+" rel="stylesheet" /></noscript>\s*'
    r'|<link href="https://fonts\.googleapis\.com/css2[^"]+" rel="stylesheet" />\s*)',
    re.S,
)
FONT_LINK = re.compile(
    r'<link href="https://fonts\.googleapis\.com/css2[^"]+" rel="stylesheet" />\s*',
)


def patch_html(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    text = FONT_BLOCK.sub("", text)
    text = FONT_LINK.sub("", text)
    text = text.replace("styles.css?v=9", "styles.css?v=10")
    text = text.replace("../css/styles.css?v=9", "../css/styles.css?v=10")
    text = text.replace('href="css/styles.css?v=9"', 'href="css/styles.css?v=10"')
    text = text.replace("js/app.js?v=9", "js/app.js?v=10")
    text = text.replace("../js/app.js?v=9", "../js/app.js?v=10")
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_css(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace(
        '  --font-display: Inter, system-ui, "Segoe UI", sans-serif;\n'
        '  --font-body: Inter, system-ui, "Segoe UI", sans-serif;\n'
        '  --font-mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;',
        '  --font-display: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;\n'
        '  --font-body: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;\n'
        '  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;',
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
        patch_css(root / "css" / "styles.css")
        for html in sorted(root.rglob("*.html")):
            if patch_html(html):
                print(f"patched {html}")
                n += 1
    print(f"Done. {n} HTML files.")


if __name__ == "__main__":
    main()
