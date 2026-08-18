# Kevantic license verify keys

- Commit **public** keys only (`licensing-ed25519-v1.pub`).
- **Never** commit private signing keys.
- Generate lab keys: `../generate_dev_keypair.sh` (private lands in `../../.cache/licensing/`).
- The same public key is copied into `ansible/roles/license_enforcer/files/` so golden/Ansible bake always installs `/etc/kevantic/trust/keys/licensing-ed25519-v1.pub`.
- Control plane minting uses `KEVANTIC_LICENSE_PRIVATE_KEY_PEM` or `KEVANTIC_LICENSE_PRIVATE_KEY_FILE`.
  `JUNEXIS_LICENSE_PRIVATE_KEY_PEM` / `JUNEXIS_LICENSE_PRIVATE_KEY_FILE` are accepted aliases.
- Appliance verifies with the baked public key under `/etc/kevantic/trust/keys/`.
- Compact JWS issuer (`iss`) is **`kevantic-license`** on both mint and verify.
