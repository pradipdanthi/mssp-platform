# Release checklist

The canonical production / cloud cutover checklist is:

[`deploy/RELEASE_CHECKLIST.md`](../deploy/RELEASE_CHECKLIST.md)

## Mandatory platform verification

Run this **before any production release or cloud deployment**. Do not declare the work complete if it reports FAILED or GAP.

```bash
cd /opt/mssp-control
python3 scripts/verify_platform_state.py --release
```

`--release` treats documented architecture gaps (Zeek/MISP/Velociraptor live install, Ansible lab `vm_id` locks, hardcoded playbook IPs) as failures so they cannot be skipped.

Day-to-day lab work may run without `--release` (FAILED still exits 1; GAP is reported but does not fail the process).

Whenever architecture, API schemas, engine rules, or agent installers change: **update `scripts/verify_platform_state.py` with new assertions and re-run it**.
