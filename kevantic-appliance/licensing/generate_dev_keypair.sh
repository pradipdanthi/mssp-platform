#!/usr/bin/env bash
# Generate Ed25519 license keypair for lab/dev.
# PUBLIC key → licensing/keys/ and Ansible role files/ (safe to ship on the image)
# PRIVATE key → .cache/licensing/ (NEVER commit; wire into control plane via env)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUB_DIR="$ROOT/licensing/keys"
ROLE_FILES="$ROOT/ansible/roles/license_enforcer/files"
PRIV_DIR="$ROOT/.cache/licensing"
mkdir -p "$PUB_DIR" "$ROLE_FILES" "$PRIV_DIR"

python3 - <<'PY' "$PUB_DIR" "$PRIV_DIR" "$ROLE_FILES"
import shutil
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

pub_dir = Path(sys.argv[1])
priv_dir = Path(sys.argv[2])
role_files = Path(sys.argv[3])
pub_path = pub_dir / "licensing-ed25519-v1.pub"
priv_path = priv_dir / "licensing-ed25519-v1.pem"
if pub_path.is_file() and priv_path.is_file():
    shutil.copyfile(pub_path, role_files / "licensing-ed25519-v1.pub")
    print(f"Kept existing public key:  {pub_path}")
    print(f"Kept existing private key: {priv_path} (do not commit)")
    print(f"Synced role files copy:    {role_files / 'licensing-ed25519-v1.pub'}")
    print("Control plane: export KEVANTIC_LICENSE_PRIVATE_KEY_FILE=<that pem path>")
    print("Alias also accepted: NIKTIAR_LICENSE_PRIVATE_KEY_FILE")
    raise SystemExit(0)

priv = Ed25519PrivateKey.generate()
priv_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
pub_pem = priv.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
priv_path.write_bytes(priv_pem)
priv_path.chmod(0o600)
pub_path.write_bytes(pub_pem)
shutil.copyfile(pub_path, role_files / "licensing-ed25519-v1.pub")
print(f"Wrote public key:  {pub_path}")
print(f"Wrote private key: {priv_path} (do not commit)")
print(f"Synced role files copy: {role_files / 'licensing-ed25519-v1.pub'}")
print("Control plane: export KEVANTIC_LICENSE_PRIVATE_KEY_FILE=<that pem path>")
print("Alias also accepted: NIKTIAR_LICENSE_PRIVATE_KEY_FILE")
PY
