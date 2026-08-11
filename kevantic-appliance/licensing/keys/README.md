# Kevantic license verify keys

- Commit **public** keys only (e.g. `licensing-ed25519-v1.pub`).
- **Never** commit private signing keys.
- Generate lab keys: `../generate_dev_keypair.sh` (private lands in `../../.cache/licensing/`).
- Control plane minting uses `KEVANTIC_LICENSE_PRIVATE_KEY_PEM` or `KEVANTIC_LICENSE_PRIVATE_KEY_FILE`.
- Appliance verifies with the public key under `/etc/kevantic/trust/keys/`.
