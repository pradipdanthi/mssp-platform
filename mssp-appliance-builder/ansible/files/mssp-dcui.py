#!/usr/bin/env python3
"""
Kevantic Appliance Console (DCUI) — local tty1 ONLY.

- Runs on Proxmox graphical Console → Linux /dev/tty1
- Refuses SSH / pts sessions (tamper-resistant by design)
- First-boot and ongoing management-network configuration
- Stdlib curses only (chopped OS friendly)
"""

from __future__ import annotations

import curses
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

VERSION = "1.2.0"
NETPLAN_PATH = Path("/etc/netplan/99-mssp-management.yaml")
NETPLAN_BACKUP = Path("/var/lib/kevantic/dcui-netplan.bak")
CLOUD_INIT_DISABLE = Path("/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg")
CONTROL_PLANE = os.environ.get(
    "KEVANTIC_DEFAULT_CONTROL_PLANE", "http://192.168.0.224:8000"
)

P_TEXT, P_TITLE, P_ACCENT, P_OK, P_BAD, P_MUTED, P_INPUT, P_BAR, P_PANEL, P_SHADOW = range(
    1, 11
)


@dataclass
class NetInfo:
    iface: str = "ens18"
    link_up: bool = False
    method: str = "static"
    address: str = ""
    prefix: int = 24
    gateway: str = ""
    dns1: str = ""
    dns2: str = ""
    hostname: str = "kevantic-appliance"


def require_local_console() -> None:
    """Hard gate: only /dev/tty1, never SSH/pts."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        _deny("SSH session detected")
    try:
        tty = os.ttyname(0)
    except OSError:
        _deny("no controlling terminal")
    real = os.path.realpath(tty)
    if real != "/dev/tty1" and not real.endswith("/tty1"):
        _deny(f"terminal is {real}, not /dev/tty1")


def _deny(reason: str) -> None:
    print("────────────────────────────────────────────", file=sys.stderr)
    print("  Kevantic Console is DISABLED over SSH.", file=sys.stderr)
    print("  Use the appliance local console only:", file=sys.stderr)
    print("    Proxmox → VM → Console (graphical / tty1)", file=sys.stderr)
    print(f"  ({reason})", file=sys.stderr)
    print("────────────────────────────────────────────", file=sys.stderr)
    sys.exit(2)


def sh(cmd: List[str], timeout: float = 10.0) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr or "").strip()
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def ifaces() -> List[str]:
    rc, out = sh(["bash", "-c", "ls -1 /sys/class/net 2>/dev/null | grep -v '^lo$'"])
    xs = [x.strip() for x in out.splitlines() if x.strip()] if rc == 0 else []
    return xs or ["ens18"]


def link_up(dev: str) -> bool:
    p = Path(f"/sys/class/net/{dev}/operstate")
    return p.is_file() and p.read_text().strip() == "up"


def ipv4_of(dev: str) -> Tuple[str, int]:
    rc, out = sh(["ip", "-4", "-o", "addr", "show", "dev", dev])
    m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", out)
    return (m.group(1), int(m.group(2))) if m else ("", 24)


def gateway() -> str:
    rc, out = sh(["ip", "route", "show", "default"])
    m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else ""


def dns_servers() -> Tuple[str, str]:
    vals: List[str] = []
    p = Path("/etc/resolv.conf")
    if p.is_file():
        for line in p.read_text(errors="replace").splitlines():
            if line.startswith("nameserver "):
                vals.append(line.split()[1])
    while len(vals) < 2:
        vals.append("")
    return vals[0], vals[1]


def os_name() -> str:
    p = Path("/etc/os-release")
    if not p.is_file():
        return "Linux"
    for line in p.read_text().splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "Linux"


def gather(preferred: str = "") -> NetInfo:
    nics = ifaces()
    nic = preferred if preferred in nics else nics[0]
    addr, pref = ipv4_of(nic)
    d1, d2 = dns_servers()
    return NetInfo(
        iface=nic,
        link_up=link_up(nic),
        method="static" if addr else "dhcp",
        address=addr,
        prefix=pref or 24,
        gateway=gateway(),
        dns1=d1,
        dns2=d2,
        hostname=socket.gethostname() or "kevantic-appliance",
    )


def valid_ip(s: str) -> bool:
    try:
        ipaddress.IPv4Address(s)
        return True
    except Exception:
        return False


def to_prefix(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        n = int(s)
        if not 1 <= n <= 32:
            raise ValueError("prefix must be 1-32")
        return n
    return ipaddress.IPv4Network(f"0.0.0.0/{s}").prefixlen


def prefix_mask(p: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{p}").netmask)


def set_hostname(hn: str) -> None:
    if not re.match(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$", hn):
        raise ValueError("invalid hostname")
    sh(["hostnamectl", "set-hostname", hn])
    hosts = Path("/etc/hosts")
    lines = []
    if hosts.is_file():
        lines = [ln for ln in hosts.read_text().splitlines() if not ln.startswith("127.0.1.1")]
    lines.append(f"127.0.1.1\t{hn}")
    hosts.write_text("\n".join(lines) + "\n")


def write_netplan(n: NetInfo) -> None:
    NETPLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLOUD_INIT_DISABLE.parent.mkdir(parents=True, exist_ok=True)
    CLOUD_INIT_DISABLE.write_text("network: {config: disabled}\n")
    for p in Path("/etc/netplan").glob("*.yaml"):
        if p.resolve() != NETPLAN_PATH.resolve():
            try:
                p.unlink()
            except OSError:
                pass
    if n.method == "dhcp":
        dns = [n.dns1 or "192.168.0.1"] + ([n.dns2] if n.dns2 else [])
        dns_yaml = "\n".join(f'          - "{d}"' for d in dns)
        body = f"""# Managed by Kevantic DCUI (tty1 only)
network:
  version: 2
  ethernets:
    {n.iface}:
      dhcp4: true
      nameservers:
        addresses:
{dns_yaml}
"""
    else:
        dns = [n.dns1] + ([n.dns2] if n.dns2 else [])
        dns_yaml = "\n".join(f'          - "{d}"' for d in dns)
        body = f"""# Managed by Kevantic DCUI (tty1 only)
network:
  version: 2
  ethernets:
    {n.iface}:
      addresses:
        - "{n.address}/{n.prefix}"
      nameservers:
        addresses:
{dns_yaml}
      routes:
        - to: default
          via: "{n.gateway}"
"""
    NETPLAN_PATH.write_text(body)
    os.chmod(NETPLAN_PATH, 0o600)


def netplan_apply() -> Tuple[bool, str]:
    rc, err = sh(["netplan", "generate"], timeout=20)
    if rc != 0:
        return False, err or "generate failed"
    rc, err = sh(["netplan", "apply"], timeout=30)
    if rc != 0:
        return False, err or "apply failed"
    return True, "ok"


def backup_plan() -> None:
    NETPLAN_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if NETPLAN_PATH.is_file():
        shutil.copy2(NETPLAN_PATH, NETPLAN_BACKUP)
    elif NETPLAN_BACKUP.is_file():
        NETPLAN_BACKUP.unlink()


def restore_plan() -> None:
    if NETPLAN_BACKUP.is_file():
        shutil.copy2(NETPLAN_BACKUP, NETPLAN_PATH)
        netplan_apply()
    elif NETPLAN_PATH.is_file():
        NETPLAN_PATH.unlink(missing_ok=True)
        netplan_apply()


def ping_ok(host: str) -> bool:
    return bool(host) and sh(["ping", "-c", "1", "-W", "2", host], timeout=5)[0] == 0


def resolve_ok(url: str) -> bool:
    try:
        h = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        socket.getaddrinfo(h, None)
        return True
    except Exception:
        return False


class ConsoleUI:
    def __init__(self, stdscr: "curses._CursesWindow") -> None:
        self.stdscr = stdscr
        self.status = ""
        self.status_ok = True
        self.net = gather()
        curses.curs_set(0)
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        self._colors()

    def _colors(self) -> None:
        self.has_color = False
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            curses.init_pair(P_TEXT, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(P_TITLE, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(P_ACCENT, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(P_OK, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(P_BAD, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(P_MUTED, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(P_INPUT, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(P_BAR, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(P_PANEL, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(P_SHADOW, curses.COLOR_BLACK, curses.COLOR_BLACK)
            self.has_color = True
            self.stdscr.bkgd(" ", curses.color_pair(P_TEXT))
        except curses.error:
            self.has_color = False

    def A(self, pair: int, bold: bool = False, dim: bool = False) -> int:
        if not self.has_color:
            a = curses.A_NORMAL
            if bold:
                a |= curses.A_BOLD
            if dim:
                a |= curses.A_DIM
            return a
        try:
            a = curses.color_pair(pair)
        except curses.error:
            return curses.A_NORMAL
        if bold:
            a |= curses.A_BOLD
        if dim:
            a |= curses.A_DIM
        return a

    def put(
        self,
        y: int,
        x: int,
        text: str,
        pair: int = P_TEXT,
        bold: bool = False,
        dim: bool = False,
    ) -> None:
        h, w = self.stdscr.getmaxyx()
        if not (0 <= y < h and 0 <= x < w - 1):
            return
        try:
            self.stdscr.addnstr(y, x, text, w - x - 1, self.A(pair, bold, dim))
        except curses.error:
            pass

    def hline(self, y: int, x: int, width: int, pair: int = P_ACCENT) -> None:
        try:
            self.stdscr.hline(y, x, curses.ACS_HLINE, max(1, width), self.A(pair))
        except curses.error:
            self.put(y, x, "─" * width, pair)

    def panel(self, y: int, x: int, rows: int, cols: int, title: str = "") -> None:
        """Framed panel with optional title inset."""
        try:
            win = self.stdscr.derwin(rows, cols, y, x)
            win.attrset(self.A(P_ACCENT, True))
            win.box()
            if title:
                label = f" {title} "
                win.addnstr(0, 2, label[: max(1, cols - 4)], cols - 4, self.A(P_TITLE, True))
            win.attroff(self.A(P_ACCENT, True))
        except curses.error:
            self.put(y, x, "+" + ("-" * (cols - 2)) + "+", P_ACCENT, True)
            for i in range(1, rows - 1):
                self.put(y + i, x, "|" + (" " * (cols - 2)) + "|", P_ACCENT)
            self.put(y + rows - 1, x, "+" + ("-" * (cols - 2)) + "+", P_ACCENT, True)
            if title:
                self.put(y, x + 2, f" {title} ", P_TITLE, True)

    def chrome(self, title: str, footer: str) -> None:
        self.stdscr.erase()
        if self.has_color:
            try:
                self.stdscr.bkgd(" ", curses.color_pair(P_TEXT))
            except curses.error:
                pass
        h, w = self.stdscr.getmaxyx()
        left = "  KEVANTIC APPLIANCE  "
        right = f"  v{VERSION}  "
        try:
            self.stdscr.addnstr(0, 0, " " * (w - 1), w - 1, self.A(P_BAR, True))
            self.stdscr.addnstr(0, 0, left[: w - 1], w - 1, self.A(P_BAR, True))
            mx = max(0, (w - len(title)) // 2)
            self.stdscr.addnstr(0, mx, title[: max(0, w - mx - 1)], w - 1, self.A(P_BAR, True))
            rx = max(0, w - len(right) - 1)
            self.stdscr.addnstr(0, rx, right[: w - rx - 1], w - 1, self.A(P_BAR, True))
            self.stdscr.addnstr(
                h - 1, 0, ("  " + footer).ljust(w - 1)[: w - 1], w - 1, self.A(P_BAR, True)
            )
        except curses.error:
            pass
        # Policy strip
        self.put(1, 0, " " * (w - 1), P_TEXT)
        self.put(1, 2, "● LOCAL CONSOLE ONLY", P_OK, True)
        self.put(1, 26, "·  SSH / remote config permanently disabled  ·  Management network", P_MUTED, dim=True)

    def kv(self, y: int, label: str, value: str, pair: int = P_TEXT, bold: bool = False) -> None:
        self.put(y, 6, f"{label:<14}", P_MUTED, dim=True)
        self.put(y, 22, value, pair, bold)

    def home(self) -> str:
        while True:
            self.net = gather(self.net.iface)
            n = self.net
            self.chrome(
                "CONSOLE SETUP",
                "F2 Configure network   F3 Diagnostics   F12 Power   Esc Recovery shell",
            )
            self.panel(3, 2, 17, 76, title="STATUS")

            self.put(5, 5, "SYSTEM", P_TITLE, True)
            self.hline(6, 5, 70, P_ACCENT)
            self.kv(7, "Hostname", n.hostname, P_TEXT, True)
            self.kv(8, "Platform", os_name(), P_TEXT)

            self.put(10, 5, "MANAGEMENT NETWORK", P_TITLE, True)
            self.hline(11, 5, 70, P_ACCENT)
            self.kv(12, "Interface", n.iface, P_ACCENT, True)
            if n.link_up:
                self.kv(13, "Link", "●  UP", P_OK, True)
            else:
                self.kv(13, "Link", "●  DOWN", P_BAD, True)
            self.kv(14, "IPv4", n.address or "— not configured —", P_TEXT, True)
            self.kv(15, "Subnet", f"/{n.prefix}   ({prefix_mask(n.prefix)})", P_TEXT)
            self.kv(16, "Gateway", n.gateway or "—", P_TEXT)
            dns = n.dns1 or "—"
            if n.dns2:
                dns = f"{n.dns1}  ·  {n.dns2}"
            self.kv(17, "DNS", dns, P_TEXT)
            self.kv(18, "Mode", n.method.upper(), P_ACCENT, True)

            if self.status:
                badge = "OK" if self.status_ok else "ATTENTION"
                pair = P_OK if self.status_ok else P_BAD
                self.put(21, 2, f"[{badge}]", pair, True)
                self.put(21, 14, self.status, pair, True)

            self.stdscr.refresh()
            ch = self.stdscr.getch()
            if ch == curses.KEY_F2:
                return "cfg"
            if ch == curses.KEY_F3:
                return "test"
            if ch == curses.KEY_F12:
                return "power"
            if ch == 27:
                return "shell"

    def prompt_line(self, label: str, default: str) -> Optional[str]:
        h, w = self.stdscr.getmaxyx()
        y = h - 3
        self.put(y, 2, " " * (w - 4), P_TEXT)
        prompt = f"{label}: "
        self.put(y, 2, prompt, P_ACCENT, True)
        curses.echo()
        curses.curs_set(1)
        self.stdscr.refresh()
        x = 2 + len(prompt)
        try:
            self.put(y, x, (default + " " * 40)[:40], P_INPUT)
            self.stdscr.move(y, x)
            raw = self.stdscr.getstr(y, x, 40)
            val = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            val = ""
        finally:
            curses.noecho()
            curses.curs_set(0)
        return default if val == "" else val

    def configure(self) -> None:
        n = gather(self.net.iface)
        nics = ifaces()
        self.chrome("CONFIGURE MANAGEMENT NETWORK", "Enter through fields  ·  empty keeps default")
        self.put(3, 4, f"NICs: {', '.join(nics)}", P_MUTED)
        self.stdscr.refresh()

        iface = self.prompt_line("Management NIC", n.iface) or n.iface
        if iface not in nics:
            self.status, self.status_ok = f"Unknown NIC '{iface}'", False
            return
        method = (self.prompt_line("IP mode [static/dhcp]", n.method) or n.method).lower()
        if method not in ("static", "dhcp"):
            self.status, self.status_ok = "Mode must be static or dhcp", False
            return
        hn = self.prompt_line("Hostname", n.hostname) or n.hostname
        dns1 = self.prompt_line("Primary DNS", n.dns1 or "192.168.0.1") or "192.168.0.1"
        dns2 = self.prompt_line("Secondary DNS (optional)", n.dns2 or "") or ""

        addr = gw = ""
        prefix = 24
        try:
            if method == "static":
                addr = self.prompt_line("IPv4 address", n.address or "192.168.0.226") or ""
                pref_s = self.prompt_line("Prefix length", str(n.prefix or 24)) or "24"
                gw = self.prompt_line("Default gateway", n.gateway or "192.168.0.1") or ""
                if not valid_ip(addr):
                    raise ValueError("bad IPv4")
                prefix = to_prefix(pref_s)
                if not valid_ip(gw):
                    raise ValueError("bad gateway")
            if not valid_ip(dns1):
                raise ValueError("bad primary DNS")
            if dns2 and not valid_ip(dns2):
                raise ValueError("bad secondary DNS")
            set_hostname(hn)
        except Exception as exc:  # noqa: BLE001
            self.status, self.status_ok = f"Validation failed: {exc}", False
            return

        new = NetInfo(
            iface=iface,
            link_up=link_up(iface),
            method=method,
            address=addr,
            prefix=prefix,
            gateway=gw,
            dns1=dns1,
            dns2=dns2,
            hostname=hn,
        )

        self.chrome("CONFIRM NETWORK SETTINGS", "Enter = Apply   Esc = Cancel")
        self.panel(3, 2, 13, 76, title="REVIEW")
        self.kv(5, "NIC", new.iface, P_ACCENT, True)
        self.kv(6, "Mode", new.method.upper(), P_TEXT, True)
        self.kv(7, "Address", f"{new.address}/{new.prefix}" if method == "static" else "DHCP", P_TEXT, True)
        self.kv(8, "Gateway", new.gateway or "—", P_TEXT)
        self.kv(9, "DNS", f"{new.dns1}  {new.dns2}".strip(), P_TEXT)
        self.kv(10, "Hostname", new.hostname, P_TEXT)
        self.put(13, 5, "Review carefully — wrong settings can isolate this appliance.", P_MUTED, dim=True)
        self.stdscr.refresh()
        while True:
            ch = self.stdscr.getch()
            if ch == 27:
                self.status, self.status_ok = "Cancelled.", True
                return
            if ch in (10, 13, curses.KEY_ENTER):
                break

        if self._apply_safe(new):
            self.status, self.status_ok = "Network applied. You can SSH / register now.", True
            self.net = gather(new.iface)

    def _apply_safe(self, n: NetInfo) -> bool:
        backup_plan()
        try:
            write_netplan(n)
        except Exception as exc:  # noqa: BLE001
            self.status, self.status_ok = f"Write failed: {exc}", False
            return False
        ok, err = netplan_apply()
        if not ok:
            restore_plan()
            self.status, self.status_ok = f"Apply failed (reverted): {err}", False
            return False
        deadline = time.time() + 10
        while True:
            left = max(0, int(deadline - time.time()))
            self.chrome("APPLYING — CONFIRM OR AUTO-REVERT", "Enter = Keep settings")
            self.panel(4, 2, 11, 76, title="SAFETY WINDOW")
            self.put(6, 5, "Network settings are live on this console.", P_OK, True)
            self.put(8, 5, f"Press ENTER within {left}s to KEEP them.", P_TITLE, True)
            self.put(9, 5, "No confirmation → automatic REVERT (anti-lockout).", P_BAD, True)
            self.put(11, 5, f"Target: {n.address or 'DHCP'} on {n.iface}", P_TEXT)
            self.stdscr.refresh()
            self.stdscr.timeout(200)
            ch = self.stdscr.getch()
            self.stdscr.timeout(-1)
            if ch in (10, 13, curses.KEY_ENTER):
                return True
            if left <= 0:
                restore_plan()
                self.status, self.status_ok = "Timed out — settings reverted.", False
                return False

    def test_net(self) -> None:
        n = gather(self.net.iface)
        rows = [
            ("Link UP", n.link_up),
            ("Ping gateway", ping_ok(n.gateway)),
            ("Ping primary DNS", ping_ok(n.dns1)),
            ("Resolve appliance management", resolve_ok(CONTROL_PLANE)),
        ]
        self.chrome("DIAGNOSTICS", "Enter / Esc = Back")
        self.panel(3, 2, 13, 76, title="CONNECTIVITY")
        self.put(5, 5, f"Management endpoint: {CONTROL_PLANE}", P_MUTED, dim=True)
        y = 7
        for name, ok in rows:
            tag = "PASS" if ok else "FAIL"
            self.put(y, 5, f"[{tag}]", P_OK if ok else P_BAD, True)
            self.put(y, 13, name, P_TEXT)
            y += 1
        self.stdscr.refresh()
        while True:
            if self.stdscr.getch() in (27, 10, 13, curses.KEY_ENTER):
                return

    def power(self) -> None:
        self.chrome("POWER", "1 Restart  ·  2 Shutdown  ·  3 Cancel")
        self.panel(4, 2, 10, 60, title="ACTIONS")
        self.put(6, 5, "1   Restart appliance", P_TEXT)
        self.put(7, 5, "2   Shut down appliance", P_TEXT)
        self.put(8, 5, "3   Cancel", P_TEXT)
        self.stdscr.refresh()
        while True:
            ch = self.stdscr.getch()
            if ch == ord("1"):
                sh(["systemctl", "reboot"])
                time.sleep(8)
            elif ch == ord("2"):
                sh(["systemctl", "poweroff"])
                time.sleep(8)
            elif ch in (ord("3"), 27):
                return

    def shell(self) -> None:
        # Local tty1 recovery only — require explicit confirmation
        self.chrome("RECOVERY SHELL", "Type shell then Enter  ·  Esc cancel")
        self.panel(4, 2, 9, 70, title="CONFIRM")
        self.put(6, 5, "Opens a root shell on this local console only.", P_TEXT)
        self.put(7, 5, "Type  shell  to continue (Esc cancels).", P_MUTED, dim=True)
        self.stdscr.refresh()
        ans = self.prompt_line("Confirm", "")
        if (ans or "").strip().lower() != "shell":
            self.status, self.status_ok = "Recovery shell cancelled.", True
            return
        curses.endwin()
        print("\n=== Local console shell (exit returns to Kevantic Console) ===\n")
        os.system("bash -l" if Path("/bin/bash").exists() else "sh -l")
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        curses.curs_set(0)
        self._colors()

    def run(self) -> None:
        while True:
            act = self.home()
            if act == "cfg":
                self.configure()
            elif act == "test":
                self.test_net()
            elif act == "power":
                self.power()
            elif act == "shell":
                self.shell()


def main() -> int:
    require_local_console()
    if os.geteuid() != 0:
        # Only meaningful on tty1; sudo still re-checks tty after re-exec
        os.execvp("sudo", ["sudo", "-n", sys.executable, *sys.argv])
    os.environ["TERM"] = "linux"
    os.environ.setdefault("NCURSES_NO_UTF8_ACS", "1")
    try:
        curses.wrapper(lambda s: ConsoleUI(s).run())
    except KeyboardInterrupt:
        return 0
    except curses.error as exc:
        print(f"Console UI error: {exc}", file=sys.stderr)
        print("Open Proxmox graphical Console (VGA/tty1), not Serial or SSH.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
