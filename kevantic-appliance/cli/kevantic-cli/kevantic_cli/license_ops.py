"""Apply / show / enforce Kevantic signed licenses on the appliance."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

# Must match backend-api/app/services/niktiar_license.py ISSUER.
LICENSE_ISSUER = "kevantic-license"
SKEW_SECONDS = 300
CATALOGUE_SERVICE_IDS = {
    "svc-01",
    "svc-02",
    "svc-03",
    "svc-04",
    "svc-05",
    "svc-06",
    "svc-07",
    "svc-08",
    "svc-09",
    "svc-10",
}


def _state_root() -> Path:
    return Path(
        os.environ.get("KEVANTIC_STATE_DIR")
        or os.environ.get("NIKTIAR_STATE_DIR")
        or "/var/lib/kevantic"
    )


def _pubkey_candidates() -> list[Path]:
    out: list[Path] = []
    for env_name in ("KEVANTIC_LICENSE_PUBKEY", "NIKTIAR_LICENSE_PUBKEY"):
        env = os.environ.get(env_name, "").strip()
        if env:
            out.append(Path(env))
    out.extend(
        [
            Path("/etc/kevantic/trust/keys/licensing-ed25519-v1.pub"),
            Path("/etc/niktiar/trust/keys/licensing-ed25519-v1.pub"),
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


def verify_and_parse(
    token: str,
    pubkey_path: Path,
    fingerprint: str = "",
    *,
    allow_expired: bool = False,
) -> dict[str, Any]:
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
    if int(claims.get("nbf", 0)) > now + SKEW_SECONDS:
        raise ValueError("not yet valid")
    expired = int(claims.get("exp", 0)) < now - SKEW_SECONDS
    if expired and not allow_expired:
        raise ValueError("expired")
    if claims.get("iss") != LICENSE_ISSUER:
        raise ValueError("bad issuer")
    if fingerprint and claims.get("fp") and claims["fp"] != fingerprint:
        raise ValueError("fingerprint mismatch")
    claims["_expired"] = expired
    return claims


def _run_reconcile() -> Optional[dict[str, Any]]:
    for helper in (
        "/usr/bin/kevantic-reconcile-services",
        "/usr/bin/junexis-reconcile-services",
    ):
        if not Path(helper).is_file():
            continue
        proc = subprocess.run(
            [helper],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        try:
            return json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return {
                "stdout": (proc.stdout or "")[:300],
                "stderr": (proc.stderr or "")[:300],
                "rc": proc.returncode,
            }
    return None


def _write_entitlements(ents: dict[str, Any]) -> Path:
    state = _state_root()
    state.mkdir(parents=True, exist_ok=True)
    ents_path = state / "entitlements.json"
    tmp = ents_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ents, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(ents_path)
    return ents_path


def entitlements_from_claims(claims: dict[str, Any], *, expired: bool = False) -> dict[str, Any]:
    raw_ids = list(claims.get("svc") or [])
    service_ids: list[str] = []
    seen: set[str] = set()
    for raw in raw_ids:
        sid = str(raw).strip().lower()
        if sid in CATALOGUE_SERVICE_IDS and sid not in seen:
            seen.add(sid)
            service_ids.append(sid)
    core = bool(claims.get("core", False))
    if expired:
        service_ids = []
        core = False
    elif core and "svc-01" not in seen:
        service_ids.insert(0, "svc-01")
    return {
        "service_ids": service_ids,
        "core": core,
        "tenant_id": claims.get("sub"),
        "appliance_id": claims.get("aid"),
        "fingerprint": claims.get("fp"),
        "contract_id": claims.get("contract"),
        "jti": claims.get("jti"),
        "exp": claims.get("exp"),
        "expired": expired,
        "verified_at": int(time.time()),
        "signed": True,
    }


def apply_license_token(token: str, fingerprint: str = "") -> dict[str, Any]:
    pub = find_pubkey()
    claims = verify_and_parse(token, pub, fingerprint=fingerprint)
    state = _state_root()
    state.mkdir(parents=True, exist_ok=True)
    (state / "license.jws").write_text(token.strip() + "\n", encoding="utf-8")
    ents = entitlements_from_claims(claims, expired=bool(claims.get("_expired")))
    _write_entitlements(ents)
    return {"ok": True, "entitlements": ents, "reconcile": _run_reconcile()}


def apply_license_file(path: Path, fingerprint: str = "") -> dict[str, Any]:
    token = path.read_text(encoding="utf-8").strip()
    return apply_license_token(token, fingerprint=fingerprint)


def _mask_catalogue(*, reason: str, claims: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    ents = {
        "service_ids": [],
        "core": False,
        "expired": True,
        "signed": False,
        "note": reason,
        "verified_at": int(time.time()),
    }
    if claims:
        ents["jti"] = claims.get("jti")
        ents["exp"] = claims.get("exp")
        ents["tenant_id"] = claims.get("sub")
        ents["appliance_id"] = claims.get("aid")
        ents["signed"] = True
    _write_entitlements(ents)
    return {"ok": True, "status": "masked", "reason": reason, "entitlements": ents, "reconcile": _run_reconcile()}


def enforce_license(fingerprint: str = "") -> dict[str, Any]:
    """Re-verify license.jws and reconcile units. Unsigned entitlements are masked."""
    state = _state_root()
    lic_path = state / "license.jws"
    ents_path = state / "entitlements.json"
    if not lic_path.is_file():
        existing: dict[str, Any] = {}
        if ents_path.is_file():
            try:
                existing = json.loads(ents_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        if existing.get("service_ids"):
            return _mask_catalogue(reason="unsigned entitlements rejected; no license.jws")
        return {
            "ok": True,
            "status": "no_license",
            "entitlements": existing,
            "reconcile": _run_reconcile(),
        }

    token = lic_path.read_text(encoding="utf-8").strip()
    pub = find_pubkey()
    try:
        claims = verify_and_parse(
            token, pub, fingerprint=fingerprint, allow_expired=True
        )
    except Exception as exc:  # noqa: BLE001
        return _mask_catalogue(reason=f"license verify failed: {exc}")

    if claims.get("_expired"):
        return _mask_catalogue(reason="license expired", claims=claims)

    ents = entitlements_from_claims(claims, expired=False)
    _write_entitlements(ents)
    return {
        "ok": True,
        "status": "active",
        "entitlements": ents,
        "reconcile": _run_reconcile(),
    }


def show_license() -> dict[str, Any]:
    state = _state_root()
    ents_path = state / "entitlements.json"
    lic_path = state / "license.jws"
    ents: dict[str, Any] = {}
    if ents_path.is_file():
        ents = json.loads(ents_path.read_text(encoding="utf-8"))
    return {
        "entitlements_path": str(ents_path),
        "license_present": lic_path.is_file(),
        "pubkey": str(find_pubkey()) if any(p.is_file() for p in _pubkey_candidates()) else None,
        "issuer": LICENSE_ISSUER,
        "service_ids": ents.get("service_ids", []),
        "core": ents.get("core"),
        "tenant_id": ents.get("tenant_id"),
        "appliance_id": ents.get("appliance_id"),
        "exp": ents.get("exp"),
        "expired": ents.get("expired"),
        "signed": ents.get("signed"),
        "jti": ents.get("jti"),
    }
