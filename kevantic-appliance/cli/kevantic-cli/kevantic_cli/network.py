"""Apply bootstrap vs locked nftables profiles + agent-source CIDRs."""

from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from kevantic_cli import state


def profile_path(mode: str) -> Path:
    name = "locked.nft" if mode == "locked" else "bootstrap.nft"
    return state.nft_profiles_dir() / name


def agent_cidrs_path() -> Path:
    return state.state_root() / "agent_source_cidrs.json"


def load_agent_cidrs() -> List[str]:
    p = agent_cidrs_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            raw = data.get("cidrs") or []
        elif isinstance(data, list):
            raw = data
        else:
            raw = []
        return [str(x).strip() for x in raw if str(x).strip()]
    except Exception:
        return []


def validate_cidrs(cidrs: Sequence[str]) -> List[str]:
    out: List[str] = []
    for raw in cidrs:
        s = str(raw).strip()
        if not s:
            continue
        try:
            net = ipaddress.ip_network(s, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid CIDR '{s}': {exc}") from exc
        if net.version != 4:
            raise ValueError(f"only IPv4 CIDRs supported currently: {s}")
        out.append(str(net))
    # de-dupe preserve order
    seen = set()
    uniq: List[str] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def save_agent_cidrs(cidrs: Sequence[str]) -> List[str]:
    cleaned = validate_cidrs(cidrs)
    state.ensure_dirs()
    agent_cidrs_path().write_text(
        json.dumps({"cidrs": cleaned}, indent=2) + "\n", encoding="utf-8"
    )
    return cleaned


def _nft_elements(cidrs: Sequence[str]) -> str:
    if not cidrs:
        return ""
    return ", ".join(cidrs)


def _render_bootstrap_with_agents(cidrs: Sequence[str]) -> str:
    elements = _nft_elements(cidrs)
    elements_block = f"    elements = {{ {elements} }}\n" if elements else ""
    return f"""#!/usr/sbin/nft -f
# Kevantic — bootstrap + agent ingest (multi-subnet CIDRs)
flush ruleset
table inet kevantic_filter {{
  set kevantic_lan_addr4 {{
    type ipv4_addr
    flags interval
{elements_block}  }}
  chain input {{
    type filter hook input priority 0; policy drop;
    iif lo accept
    ct state established,related accept
    ct state invalid drop
    ip protocol icmp limit rate 5/second accept
    ip6 nexthdr icmpv6 limit rate 5/second accept
    ip saddr {{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 }} tcp dport 22 accept
    ip saddr @kevantic_lan_addr4 tcp dport {{ 1514, 1515, 514, 6514 }} accept
    ip saddr @kevantic_lan_addr4 udp dport {{ 514, 1514 }} accept
  }}
  chain forward {{
    type filter hook forward priority 0; policy drop;
  }}
  chain output {{
    type filter hook output priority 0; policy accept;
  }}
}}
"""


def _render_locked_with_agents(cidrs: Sequence[str]) -> str:
    elements = _nft_elements(cidrs)
    elements_block = f"    elements = {{ {elements} }}\n" if elements else ""
    return f"""#!/usr/sbin/nft -f
# Kevantic — locked + agent ingest (multi-subnet CIDRs)
flush ruleset
table inet kevantic_filter {{
  set kevantic_soc_addr4 {{
    type ipv4_addr
    flags interval
  }}
  set kevantic_lan_addr4 {{
    type ipv4_addr
    flags interval
{elements_block}  }}
  chain input {{
    type filter hook input priority 0; policy drop;
    iif lo accept
    ct state established,related accept
    ct state invalid drop
    ip protocol icmp limit rate 5/second accept
    ip6 nexthdr icmpv6 limit rate 5/second accept
    ip saddr @kevantic_lan_addr4 tcp dport {{ 1514, 1515, 514, 6514 }} accept
    ip saddr @kevantic_lan_addr4 udp dport {{ 514, 1514 }} accept
  }}
  chain forward {{
    type filter hook forward priority 0; policy drop;
  }}
  chain output {{
    type filter hook output priority 0; policy drop;
    oif lo accept
    ct state established,related accept
    udp dport 53 accept
    tcp dport 53 accept
    udp dport 123 accept
    tcp dport 443 accept
  }}
}}
"""


def _apply_nft_text(text: str, dest_name: str) -> str:
    nft = shutil.which("nft")
    if nft is None:
        return "nft not installed — CIDRs saved only"

    dest_dir = state.config_root() / "nftables"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / dest_name
    dest.write_text(text, encoding="utf-8")
    try:
        subprocess.run([nft, "-f", str(dest)], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"nft apply failed: {err}") from exc
    except PermissionError as exc:
        raise RuntimeError(f"need root to apply nftables ({dest})") from exc
    return f"applied {dest}"


def apply_network_mode(mode: str, *, dry_run: bool = False) -> str:
    """Set mode file and optionally load nftables. Returns human message."""
    if mode not in ("bootstrap", "locked"):
        raise ValueError(f"invalid network mode: {mode}")
    state.set_network_mode(mode)

    cidrs = load_agent_cidrs()
    if dry_run:
        return f"network_mode={mode} (dry-run; cidrs={cidrs})"

    if mode == "locked":
        text = _render_locked_with_agents(cidrs)
        note = _apply_nft_text(text, "locked-applied.nft")
    else:
        text = _render_bootstrap_with_agents(cidrs)
        note = _apply_nft_text(text, "bootstrap-applied.nft")
    return f"network_mode={mode}; {note}; agent_cidrs={cidrs}"


def apply_agent_cidrs(cidrs: Iterable[str], *, dry_run: bool = False) -> dict:
    """
    Save agent-source CIDRs and open Wazuh ingest ports (1514/1515) for them.
    Used by CLI and by remote Admin job set_agent_cidrs.
    """
    cleaned = validate_cidrs(list(cidrs))
    if dry_run:
        return {"ok": True, "dry_run": True, "cidrs": cleaned, "network_mode": state.get_network_mode()}
    save_agent_cidrs(cleaned)
    mode = state.get_network_mode()
    if mode not in ("bootstrap", "locked"):
        mode = "bootstrap"
    try:
        msg = apply_network_mode(mode, dry_run=False)
        return {"ok": True, "cidrs": cleaned, "network_mode": mode, "message": msg, "nft_applied": True}
    except Exception as exc:  # noqa: BLE001
        # Persist CIDRs even if nft is blocked (lab CAP/AppArmor); operator can re-apply later.
        return {
            "ok": True,
            "cidrs": cleaned,
            "network_mode": mode,
            "nft_applied": False,
            "message": f"CIDRs saved; nft apply deferred: {exc}",
        }


def require_root_hint() -> None:
    if hasattr(os := __import__("os"), "geteuid") and os.geteuid() != 0:
        print("note: nftables apply may require root", file=sys.stderr)
