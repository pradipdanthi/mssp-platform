"""KB-079: Load tenant-scoped vuln scan targets (minimal YAML, no PyYAML required)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def load_vuln_scan_targets(path: str | Path) -> Dict[str, Dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    tenants: Dict[str, Dict[str, Any]] = {}
    current: str | None = None
    mode: str | None = None
    list_key: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("tenants:"):
            mode = "tenants"
            continue
        if mode != "tenants":
            continue
        m_tenant = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m_tenant:
            current = m_tenant.group(1).strip().upper()
            tenants[current] = {
                "asset_hostname": None,
                "nuclei_targets": [],
                "vuls_servers": [],
            }
            list_key = None
            continue
        if not current:
            continue
        m_scalar = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if m_scalar and not line.strip().startswith("-"):
            key, val = m_scalar.group(1), m_scalar.group(2).strip().strip("'\"")
            if key == "asset_hostname":
                tenants[current]["asset_hostname"] = val or None
            continue
        m_list = re.match(r"^    (nuclei_targets|vuls_servers):\s*$", line)
        if m_list:
            list_key = m_list.group(1)
            continue
        m_item = re.match(r"^      - (.+)$", line)
        if m_item and list_key == "nuclei_targets":
            tenants[current]["nuclei_targets"].append(m_item.group(1).strip().strip("'\""))
            continue
        m_vuls = re.match(r"^      - name:\s*(.+)$", line)
        if m_vuls and list_key == "vuls_servers":
            tenants[current]["vuls_servers"].append({"name": m_vuls.group(1).strip().strip("'\"")})
            continue
        m_vuls_field = re.match(r"^        ([a-z]+):\s*(.+)$", line)
        if m_vuls_field and list_key == "vuls_servers" and tenants[current]["vuls_servers"]:
            tenants[current]["vuls_servers"][-1][m_vuls_field.group(1)] = (
                m_vuls_field.group(2).strip().strip("'\"")
            )

    return tenants


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: kb079_vuln_scan_map.py <config.yml>", file=sys.stderr)
        raise SystemExit(2)
    import json

    print(json.dumps(load_vuln_scan_targets(sys.argv[1]), indent=2))


if __name__ == "__main__":
    main()
