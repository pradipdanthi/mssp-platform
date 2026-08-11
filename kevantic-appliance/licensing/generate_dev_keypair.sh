#!/usr/bin/env bash
# Generate Ed25519 license keypair for lab/dev.
# PUBLIC key → licensing/keys/ (safe to ship on ISO)
# PRIVATE key → .cache/licensing/ (NEVER commit; wire into control plane via env)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUB_DIR="$ROOT/licensing/keys"
PRIV_DIR="$ROOT/.cache/licensing"
mkdir -p "$PUB_DIR" "$PRIV_DIR"

python3 - <<'PY' "$PUB_DIR" "$PRIV_DIR"
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

pub_dir = Path(sys.argv[1])
priv_dir = Path(sys.argv[2])
priv = Ed25519PrivateKey.generate()
priv_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
pub_pem = priv.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
(priv_dir / "licensing-ed25519-v1.pem").write_bytes(priv_pem)
(priv_dir / "licensing-ed25519-v1.pem").chmod(0o600)
(pub_dir / "licensing-ed25519-v1.pub").write_bytes(pub_pem)
print(f"Wrote public key:  {pub_dir / 'licensing-ed25519-v1.pub'}")
print(f"Wrote private key: {priv_dir / 'licensing-ed25519-v1.pem'} (do not commit)")
print("Control plane: export KEVANTIC_LICENSE_PRIVATE_KEY_FILE=<that pem path>")
PY
