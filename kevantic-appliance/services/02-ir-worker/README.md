# svc-02 — IR local worker (not TheHive)

Executes **signed remediation / containment jobs** pushed from Kevantic Cloud SOC.

## Hard exclusions

- **Do not** install TheHive, Cortex case UI, or any local ticketing database on the appliance
- Case creation, assignment, and analyst workflow stay in **Cloud SOC** only
- This module is an execution agent only

## Layout (target)

- `systemd/` or Quadlet unit templates
- `container/` image reference + config
- Job verifier (signature + entitlement) before any action

See `docs/SERVICE_MATRIX.md` and KB-093 §2.1 / §8 / §9.
