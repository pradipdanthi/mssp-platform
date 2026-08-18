# Release checklist

The canonical production / cloud cutover checklist is:

[`deploy/RELEASE_CHECKLIST.md`](../deploy/RELEASE_CHECKLIST.md)

## Mandatory platform verification

Run this **before any production release or cloud deployment**. Do not declare the work complete if it reports FAILED or GAP.

```bash
cd /opt/mssp-control
python3 scripts/verify_platform_state.py --release
```

`--release` must report **CLOUD-READY: YES** with **0 FAILED** and **0 GAP**. The six cutover gaps are closed:

1. Zeek has a dedicated, inventory-driven playbook (`ansible/playbooks/zeek.yml`) in the engine deploy order.
2. MISP has a dedicated Ansible role and playbook (`ansible/playbooks/misp.yml`).
3. MISP live install is gated (`misp_execution_mode` / `misp_live_install_approved`) and listed for cloud cutover.
4. Velociraptor live install is gated the same way and listed for cloud cutover.
5. Ansible roles identify hosts by `deployment_role` + `ansible_host` (no lab `vm_id` asserts).
6. Playbooks resolve Manager/sensor addresses from inventory (`wazuh_manager_ip`, `ansible_host`) — no hardcoded `192.168.0.x`.

Day-to-day lab work may run without `--release` (FAILED still exits 1; GAP is reported but does not fail the process). Live engine installs still require explicit per-playbook approval flags; this checklist does not install Zeek/MISP/Velociraptor on lab VMs.

Whenever architecture, API schemas, engine rules, or agent installers change: **update `scripts/verify_platform_state.py` with new assertions and re-run it**.
