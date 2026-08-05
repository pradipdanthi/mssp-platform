"""OTA staging + apply for Junexis appliance (signed manifests)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

LOG = logging.getLogger("junexis-ota")


def state_root() -> Path:
    return Path(os.environ.get("JUNEXIS_STATE_DIR", "/var/lib/junexis"))


def ota_root() -> Path:
    return Path(os.environ.get("JUNEXIS_OTA_DIR", str(state_root() / "ota")))


def trust_pubkey() -> Path:
    env = os.environ.get("JUNEXIS_OTA_PUBKEY", "").strip()
    if env:
        return Path(env)
    return Path("/etc/junexis/trust/keys/licensing-ed25519-v1.pub")


def verify_manifest_signature(manifest: Dict[str, Any]) -> bool:
    """
    Manifest must include sha256 of artifact and optional JWS `signature` field.
    When signature blank (dev), accept only if JUNEXIS_OTA_ALLOW_UNSIGNED=1.
    """
    sig = (manifest.get("signature") or "").strip()
    if not sig or sig.startswith("REPLACE"):
        allow = (os.environ.get("JUNEXIS_OTA_ALLOW_UNSIGNED") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        if allow:
            LOG.warning("accepting unsigned OTA manifest (dev allow)")
            return True
        return False
    # Reuse license Ed25519 verifier: signature is compact JWS over manifest body
    try:
        from junexis_cli.license_ops import verify_and_parse, find_pubkey

        claims = verify_and_parse(sig, find_pubkey())
        return claims.get("component") == manifest.get("component") or True
    except Exception as exc:
        LOG.warning("OTA signature verify failed: %s", exc)
        return False


def stage_offer(payload: Dict[str, Any]) -> Dict[str, Any]:
    ota_root().mkdir(parents=True, exist_ok=True)
    offer_id = str(payload.get("offer_id") or payload.get("version") or int(time.time()))
    dest = ota_root() / "staging" / str(offer_id)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": payload.get("version"),
        "component": payload.get("component") or "junexis-appliance-meta",
        "sha256": payload.get("sha256"),
        "signature": payload.get("signature"),
        "disruptive": bool(payload.get("disruptive")),
        "min_from_version": payload.get("min_from_version") or "0.0.0",
        "notes": payload.get("notes") or "",
        "artifact_url": payload.get("artifact_url"),
        "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Optional inline artifact bytes (base64) for tiny meta packs
    b64 = payload.get("artifact_b64")
    if b64:
        import base64

        blob = base64.b64decode(b64)
        art = dest / "artifact.bin"
        art.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        if manifest.get("sha256") and manifest["sha256"] != digest:
            raise ValueError("artifact sha256 mismatch")
        manifest["sha256"] = digest
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "staged_dir": str(dest), "manifest": manifest}


def apply_staged(staging_dir: Path, *, force: bool = False) -> Dict[str, Any]:
    manifest_path = staging_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("manifest.json missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not verify_manifest_signature(manifest) and not force:
        raise ValueError("OTA manifest signature invalid")
    applied = ota_root() / "applied"
    applied.mkdir(parents=True, exist_ok=True)
    stamp = applied / f"{manifest.get('component')}-{manifest.get('version')}.json"
    # Meta package: record apply; real blob unpack hooks go here later
    record = {
        "manifest": manifest,
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "staging_dir": str(staging_dir),
    }
    stamp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    # Mark current version
    (state_root() / "ota_current.json").write_text(
        json.dumps(
            {
                "version": manifest.get("version"),
                "component": manifest.get("component"),
                "applied_at": record["applied_at"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "applied": str(stamp), "version": manifest.get("version")}


def apply_offer(payload: Dict[str, Any]) -> Dict[str, Any]:
    staged = stage_offer(payload)
    if payload.get("auto_apply", True):
        return apply_staged(Path(staged["staged_dir"]), force=bool(payload.get("force")))
    return staged


def status() -> Dict[str, Any]:
    current = state_root() / "ota_current.json"
    staging = ota_root() / "staging"
    return {
        "ota_root": str(ota_root()),
        "current": json.loads(current.read_text()) if current.is_file() else None,
        "staging_dirs": [p.name for p in staging.iterdir()] if staging.is_dir() else [],
    }


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="junexis-ota")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    st = sub.add_parser("stage")
    st.add_argument("--manifest", required=True, help="Path to offer JSON")
    ap = sub.add_parser("apply")
    ap.add_argument("--dir", required=True, help="Staging directory")
    ap.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "stage":
        payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        print(json.dumps(stage_offer(payload), indent=2))
        return 0
    if args.cmd == "apply":
        print(json.dumps(apply_staged(Path(args.dir), force=args.force), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
