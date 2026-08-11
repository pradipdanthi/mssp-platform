"""Apply / show Kevantic signed licenses on the appliance."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


def _state_root() -> Path:
    return Path(os.environ.get("KEVANTIC_STATE_DIR", "/var/lib/kevantic"))


def _pubkey_candidates() -> list[Path]:
    env = os.environ.get("KEVANTIC_LICENSE_PUBKEY", "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    out.extend(
        [
            Path("/etc/kevantic/trust/keys/licensing-ed25519-v1.pub"),
            Path(__file__).resolve().parents[3]
            / "licensing"
            / "keys"
            / "licensing-ed25519-v1.pub",
        ]
    )
    return out


def find_pubkey() -> Path:
    for p in _pubkey_candidates():
        if p.is_file():
            return p
    raise FileNotFoundError(
        "No licensing public key found under /etc/kevantic/trust/keys/"
    )


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def verify_and_parse(token: str, pubkey_path: Path, fingerprint: str = "") -> dict[str, Any]:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
    except ImportError as exc:
        raise RuntimeError("python3-cryptography is required on the appliance") from exc

    data = pubkey_path.read_bytes()
    pub = load_pem_public_key(data)
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("public key is not Ed25519")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError("not a compact JWS")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    pub.verify(_b64url_decode(parts[2]), signing_input)
    header = json.loads(_b64url_decode(parts[0]))
    if header.get("alg") != "EdDSA":
        raise ValueError("unsupported alg")
    claims = json.loads(_b64url_decode(parts[1]))
    now = int(time.time())
    if int(claims.get("nbf", 0)) > now + 300:
        raise ValueError("not yet valid")
    if int(claims.get("exp", 0)) < now - 300:
        raise ValueError("expired")
    if claims.get("iss") != "kevantic-license":
        raise ValueError("bad issuer")
    if fingerprint and claims.get("fp") and claims["fp"] != fingerprint:
        raise ValueError("fingerprint mismatch")
    return claims


def apply_license_file(path: Path, fingerprint: str = "") -> dict[str, Any]:
    token = path.read_text(encoding="utf-8").strip()
    pub = find_pubkey()
    claims = verify_and_parse(token, pub, fingerprint=fingerprint)
    state = _state_root()
    state.mkdir(parents=True, exist_ok=True)
    lic_path = state / "license.jws"
    ents_path = state / "entitlements.json"
    lic_path.write_text(token + "\n", encoding="utf-8")
    ents = {
        "service_ids": list(claims.get("svc") or []),
        "core": bool(claims.get("core", False)),
        "tenant_id": claims.get("sub"),
        "appliance_id": claims.get("aid"),
        "fingerprint": claims.get("fp"),
        "contract_id": claims.get("contract"),
        "jti": claims.get("jti"),
        "exp": claims.get("exp"),
        "verified_at": int(time.time()),
    }
    if ents["core"] and "svc-01" not in ents["service_ids"]:
        ents["service_ids"].insert(0, "svc-01")
    tmp = ents_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ents, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(ents_path)

    reconcile: Optional[dict[str, Any]] = None
    if Path("/usr/bin/kevantic-reconcile-services").is_file():
        proc = subprocess.run(
            ["/usr/bin/kevantic-reconcile-services"],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            reconcile = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            reconcile = {"stdout": proc.stdout, "stderr": proc.stderr, "rc": proc.returncode}

    return {"ok": True, "entitlements": ents, "reconcile": reconcile}


def show_license() -> dict[str, Any]:
    state = _state_root()
    ents_path = state / "entitlements.json"
    lic_path = state / "license.jws"
    ents = {}
    if ents_path.is_file():
        ents = json.loads(ents_path.read_text(encoding="utf-8"))
    return {
        "entitlements_path": str(ents_path),
        "license_present": lic_path.is_file(),
        "service_ids": ents.get("service_ids", []),
        "core": ents.get("core"),
        "tenant_id": ents.get("tenant_id"),
        "appliance_id": ents.get("appliance_id"),
        "exp": ents.get("exp"),
        "jti": ents.get("jti"),
    }
