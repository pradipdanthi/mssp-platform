#!/usr/bin/env python3
"""Phase 3: sync Silver/Gold/Platinum marketing copy across website trees."""
from __future__ import annotations

import re
import sys
from pathlib import Path

SNIPPET_ROOT = Path(__file__).resolve().parent.parent / "snippets"
TIER_SNIPPET = (SNIPPET_ROOT / "tier-section-3tier.html").read_text(encoding="utf-8")
CAPS_SNIPPET = (SNIPPET_ROOT / "capabilities-by-tier.html").read_text(encoding="utf-8")

BRONZE_REPLACEMENTS = [
    ("Bronze to Platinum", "Silver to Platinum"),
    ("Bronze–Platinum", "Silver–Platinum"),
    ("Bronze through Platinum", "Silver through Platinum"),
    ("Bronze Core SIEM through Platinum", "Silver ITDR through Platinum Full MXDR"),
    ("Bronze Core SIEM or Silver Advanced Sec", "Silver Identity ITDR or Gold Core MDR"),
    ("Bronze Core SIEM or Silver", "Silver Identity ITDR or Gold"),
    ("Start with Bronze Core SIEM.", "Start with Silver Identity ITDR."),
    ("dynamic Bronze–Platinum provisioning", "dynamic Silver–Platinum tier provisioning"),
    ("Bronze Core SIEM", "Silver Identity ITDR"),
    ("Four subscription tiers", "Three subscription tiers"),
    ("start on Bronze or Silver", "start on Silver and upgrade to Gold or Platinum"),
]

VENDOR_REPLACEMENTS = [
    ("Wazuh EDR telemetry & alerting", "NikTiar Core EDR telemetry & alerting"),
    ("Wazuh EDR", "NikTiar Core EDR"),
    ("Suricata / Zeek NDR (NikTiar DeepSight)", "NikTiar DeepSight NDR"),
    ("Suricata / Zeek NDR (DeepSight)", "NikTiar DeepSight NDR"),
    ("DeepSight NDR (Suricata & Zeek)", "NikTiar DeepSight NDR"),
    ("ClickHouse OLAP analytics & compressed archival", "NikTiar analytics OLAP & compressed archival"),
    ("ClickHouse OLAP & compressed archival", "NikTiar analytics OLAP & archival"),
    ("Vulnerability management sync", "NikTiar Aegis vulnerability sync"),
    ("External attack surface (EASM) sync", "NikTiar perimeter EASM sync"),
    ("Vulnerability & EASM sync", "NikTiar Aegis & perimeter EASM sync"),
]

def dedupe_niktier(text: str) -> str:
    return text.replace("NikTiar NikTiar", "NikTiar")


def patch_tier_section(html: str, demo_href: str) -> str:
    snippet = TIER_SNIPPET.replace("{{DEMO_HREF}}", demo_href)
    return re.sub(
        r'<section class="tier-section[^"]*" id="tiers">.*?</section>\s*',
        snippet + "\n",
        html,
        count=1,
        flags=re.S,
    )


def patch_capabilities_section(html: str) -> str:
    return re.sub(
        r'<div class="svc-block">\s*<div class="svc-block-head"><h3>Core Platform \(included\)</h3>.*?</div>\s*</div>\s*<div class="svc-block">\s*<div class="svc-block-head"><h3>Optional add-ons</h3>.*?</div>\s*</div>',
        CAPS_SNIPPET,
        html,
        count=1,
        flags=re.S,
    )


def apply_text_replacements(text: str) -> str:
    for old, new in BRONZE_REPLACEMENTS + VENDOR_REPLACEMENTS:
        text = text.replace(old, new)
    return text


def patch_file(path: Path, *, demo_href: str, capabilities: bool) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if 'id="tiers"' in text:
        text = patch_tier_section(text, demo_href)
    if capabilities:
        text = patch_capabilities_section(text)
    text = dedupe_niktier(apply_text_replacements(text))
    path.write_text(text, encoding="utf-8")
    print(f"  patched {path}")


def patch_tree(root: Path) -> None:
    print(f"Syncing {root}")
    for rel in [
        "index.html",
        "services.html",
        "contact.html",
        "platform.html",
        "solutions.html",
    ]:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = apply_text_replacements(text)
        path.write_text(text, encoding="utf-8")
        print(f"  copy-fix {path}")

    patch_file(root / "index.html", demo_href="#demo", capabilities=False)
    patch_file(root / "services.html", demo_href="contact.html", capabilities=True)


def main() -> None:
    targets = [
        Path("/opt/mssp-control/website-niktiar"),
        Path("/home/secadmin/kevantic-website"),
    ]
    for root in targets:
        if root.is_dir():
            patch_tree(root)
    print("Done.")


if __name__ == "__main__":
    main()
