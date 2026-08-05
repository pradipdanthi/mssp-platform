"""junexis-cli entrypoint (KB-093 B1 + Track-1 register/heartbeat)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from junexis_cli import __version__, bootstrap, license_ops, network, register_ops, state


def _out(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    elif isinstance(data, dict):
        for k, v in data.items():
            print(f"{k}: {v}")
    else:
        print(data)


def cmd_version(_: argparse.Namespace) -> int:
    print(f"junexis-cli {__version__}")
    print(
        f"appliance_train "
        f"{Path(__file__).resolve().parents[3].joinpath('VERSION').read_text(encoding='utf-8').strip() if Path(__file__).resolve().parents[3].joinpath('VERSION').is_file() else 'unknown'}"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    app = state.load_appliance_state()
    boot = state.load_bootstrap_state()
    ents = state.load_entitlements()
    payload = {
        "cli_version": __version__,
        "registration": app.get("registration"),
        "appliance_name": app.get("appliance_name"),
        "appliance_id": app.get("appliance_id"),
        "deploy_method": app.get("deploy_method"),
        "control_plane": app.get("control_plane"),
        "network_mode": state.get_network_mode(),
        "bootstrap_last_result": boot.get("last_result"),
        "bootstrap_last_run_at": boot.get("last_run_at"),
        "channel": "phase_a_heartbeat",
        "entitlements": ents.get("service_ids"),
        "handoff_ready": (
            state.get_network_mode() == "locked" and boot.get("last_result") == "success"
        ),
        "note": "TheHive is not installed on appliance; cases stay in Cloud SOC",
        "appliance_mgmt_plane": "separate server in production (not permanent on mssp-control)",
    }
    ch_path = state.state_root() / "channeld.status.json"
    if ch_path.is_file():
        try:
            payload["channel"] = "phase_b_channeld"
            payload["channel_status"] = json.loads(ch_path.read_text(encoding="utf-8"))
        except Exception:
            payload["channel_status"] = {"ok": False}
    _out(payload, args.json)
    return 0


def cmd_channel(args: argparse.Namespace) -> int:
    from pathlib import Path

    status_path = state.state_root() / "channeld.status.json"
    payload = {
        "channel": "phase_b_channeld",
        "unit_installed": Path("/etc/systemd/system/junexis-channeld.service").is_file(),
        "status_file": str(status_path),
        "status": None,
        "hint": "systemctl status junexis-channeld; heartbeat timer remains Phase A fallback",
    }
    if status_path.is_file():
        try:
            payload["status"] = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            payload["status_error"] = str(exc)
    _out(payload, args.json)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    state.ensure_dirs()
    app = state.load_appliance_state()
    if not args.token:
        print("error: --token is required", file=sys.stderr)
        return 1
    app["appliance_name"] = args.appliance_name or app.get("appliance_name") or "junexis-appliance"
    app["site_name"] = args.site_name or app.get("site_name") or ""
    app["control_plane"] = args.control_plane
    app["deploy_method"] = args.deploy_method or ""
    app["registration"] = "pending_register"
    app["token_presented"] = True
    app["token_fingerprint"] = f"sha256_prefix:{args.token[:4]}…len={len(args.token)}"
    state.save_appliance_state(app)
    state.set_network_mode("bootstrap")
    msg = {
        "ok": True,
        "registration": app["registration"],
        "appliance_name": app["appliance_name"],
        "network_mode": "bootstrap",
        "next": [
            "junexis-cli bootstrap update",
            "junexis-cli network lock --yes",
            "junexis-cli register --token <ACTIVATION_TOKEN>",
            "systemctl enable --now junexis-heartbeat.timer",
        ],
        "warning": "Raw activation token was not written to disk — pass it again to register",
    }
    _out(msg, args.json)
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    if not args.token:
        print("error: --token is required", file=sys.stderr)
        return 1
    try:
        result = register_ops.register(
            activation_token=args.token,
            control_plane=args.control_plane or None,
            appliance_name=args.appliance_name or None,
            local_ip=args.local_ip or None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _out(result, args.json)
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    try:
        result = register_ops.heartbeat(include_inventory=not args.no_inventory)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 3
    _out(result, args.json)
    return 0 if result.get("ok") else 4


def cmd_bootstrap(args: argparse.Namespace) -> int:
    if args.bootstrap_cmd == "status":
        _out(state.load_bootstrap_state() | {"network_mode": state.get_network_mode()}, args.json)
        return 0
    if args.bootstrap_cmd == "update":
        result = bootstrap.run_bootstrap_update(
            os_only=args.os_only,
            engines_only=args.engines_only,
            dry_run=args.dry_run,
        )
        _out(result, args.json)
        return 0 if result.get("last_result") == "success" else 4
    print("usage: junexis-cli bootstrap {status|update}", file=sys.stderr)
    return 1


def cmd_network(args: argparse.Namespace) -> int:
    if args.network_cmd == "status":
        _out(
            {
                "network_mode": state.get_network_mode(),
                "bootstrap": state.load_bootstrap_state().get("last_result"),
                "profiles": str(state.nft_profiles_dir()),
            },
            args.json,
        )
        return 0
    if args.network_cmd == "lock":
        if not args.yes:
            print("error: refusing lock without --yes", file=sys.stderr)
            return 10
        boot = state.load_bootstrap_state()
        if boot.get("last_result") != "success" and not args.force:
            print(
                "error: bootstrap last_result is not success; "
                "run bootstrap update first or pass --force",
                file=sys.stderr,
            )
            return 4
        try:
            msg = network.apply_network_mode("locked", dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 4
        _out({"ok": True, "message": msg, "network_mode": state.get_network_mode()}, args.json)
        return 0
    if args.network_cmd == "unlock":
        if not args.yes or args.confirm != "BREAK_GLASS":
            print(
                "error: unlock requires --yes --confirm BREAK_GLASS",
                file=sys.stderr,
            )
            return 10
        try:
            msg = network.apply_network_mode("bootstrap", dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 4
        _out(
            {
                "ok": True,
                "message": msg,
                "network_mode": state.get_network_mode(),
                "audit": "break_glass_unlock",
            },
            args.json,
        )
        return 0
    print("usage: junexis-cli network {status|lock|unlock}", file=sys.stderr)
    return 1


def cmd_license(args: argparse.Namespace) -> int:
    if args.license_cmd == "show":
        _out(license_ops.show_license(), args.json)
        return 0
    if args.license_cmd == "apply":
        if not args.file:
            print("error: --file is required", file=sys.stderr)
            return 1
        path = Path(args.file)
        if not path.is_file():
            print(f"error: file not found: {path}", file=sys.stderr)
            return 1
        try:
            result = license_ops.apply_license_file(path, fingerprint=args.fingerprint or "")
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 4
        _out(result, args.json)
        return 0
    print("usage: junexis-cli license {show|apply}", file=sys.stderr)
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    payload = {
        "state_dir": str(state.state_root()),
        "config_dir": str(state.config_root()),
        "nft_dir": str(state.nft_profiles_dir()),
        "bootstrap_profile": str(network.profile_path("bootstrap")),
        "locked_profile": str(network.profile_path("locked")),
        "bootstrap_exists": network.profile_path("bootstrap").is_file(),
        "locked_exists": network.profile_path("locked").is_file(),
        "network_mode": state.get_network_mode(),
        "api_key_present": register_ops.api_key_path().is_file(),
        "thehive_on_appliance": False,
        "production_appliance_mgmt": "separate_server",
    }
    _out(payload, args.json)
    return 0 if payload["bootstrap_exists"] and payload["locked_exists"] else 4


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="JSON output")
    common.add_argument("--quiet", "-q", action="store_true")

    p = argparse.ArgumentParser(
        prog="junexis-cli",
        description="Junexis Appliance management CLI",
        parents=[common],
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="Show CLI version", parents=[common])
    sub.add_parser("status", help="Appliance status summary", parents=[common])
    sub.add_parser("doctor", help="Local diagnostics", parents=[common])
    sub.add_parser("channel", help="SOC channel status (channeld)", parents=[common])

    setup = sub.add_parser("setup", help="First-boot wizard (local state)", parents=[common])
    setup.add_argument("--token", required=True)
    setup.add_argument("--control-plane", default="https://soc.junexis.com")
    setup.add_argument("--appliance-name", default="")
    setup.add_argument("--site-name", default="")
    setup.add_argument("--deploy-method", choices=["factory", "customer-vm"], default="")
    setup.add_argument("--proxy", default="")

    reg = sub.add_parser("register", help="Redeem activation token with control plane", parents=[common])
    reg.add_argument("--token", required=True)
    reg.add_argument("--control-plane", default="")
    reg.add_argument("--appliance-name", default="")
    reg.add_argument("--local-ip", default="")

    hb = sub.add_parser("heartbeat", help="Push health + agent inventory; pull jobs", parents=[common])
    hb.add_argument("--no-inventory", action="store_true")

    boot = sub.add_parser("bootstrap", help="First-time critical updates", parents=[common])
    boot_sub = boot.add_subparsers(dest="bootstrap_cmd", required=True)
    boot_sub.add_parser("status", parents=[common])
    boot_up = boot_sub.add_parser("update", parents=[common])
    boot_up.add_argument("--os-only", action="store_true")
    boot_up.add_argument("--engines-only", action="store_true")
    boot_up.add_argument("--dry-run", action="store_true")

    net = sub.add_parser("network", help="Bootstrap vs locked posture", parents=[common])
    net_sub = net.add_subparsers(dest="network_cmd", required=True)
    net_sub.add_parser("status", parents=[common])
    net_lock = net_sub.add_parser("lock", parents=[common])
    net_lock.add_argument("--yes", "-y", action="store_true")
    net_lock.add_argument("--force", action="store_true")
    net_lock.add_argument("--dry-run", action="store_true")
    net_unlock = net_sub.add_parser("unlock", parents=[common])
    net_unlock.add_argument("--yes", "-y", action="store_true")
    net_unlock.add_argument("--confirm", default="")
    net_unlock.add_argument("--dry-run", action="store_true")

    lic = sub.add_parser("license", help="Apply / show Junexis-signed license", parents=[common])
    lic_sub = lic.add_subparsers(dest="license_cmd", required=True)
    lic_sub.add_parser("show", parents=[common])
    lic_apply = lic_sub.add_parser("apply", parents=[common])
    lic_apply.add_argument("--file", required=True, help="Path to .jws license file")
    lic_apply.add_argument("--fingerprint", default="", help="Expected appliance fingerprint")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "version": cmd_version,
        "status": cmd_status,
        "setup": cmd_setup,
        "register": cmd_register,
        "heartbeat": cmd_heartbeat,
        "channel": cmd_channel,
        "bootstrap": cmd_bootstrap,
        "network": cmd_network,
        "license": cmd_license,
        "doctor": cmd_doctor,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
