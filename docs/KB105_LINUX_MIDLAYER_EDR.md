# KB-105 — Linux mid-layer execve telemetry + Windows offline Sysmon fallback

Status: Implemented on control plane (VM 100). Bake/upgrade required for appliances.  
Date: 2026-08-18  
Purpose: Fill the two packaging gaps without changing Windows active-response scripts, `source_tool`, or VM 100 listen ports.

## What changed

### Windows (offline Sysmon)

`Enable-MsspWindowsTelemetry.ps1` (canonical: `backend-api/app/endpoint_configs/`) now:

1. Uses `Sysmon64.exe` / `Sysmon.exe` next to the installer if present.
2. Downloads Sysinternals **only** when the binary is missing **and** the host can reach the network.
3. Agent ZIP embeds `windows/Sysmon64.exe` when the control plane can cache it.

**Air-gapped / restricted Windows sites:** cache the Microsoft Sysinternals binary on the control plane (never commit it), then rebuild:

```bash
cd /opt/mssp-control
./scripts/cache_sysmon_offline.sh
./scripts/production_deploy_control_plane.sh
```

That writes `Sysmon64.exe` to `.cache/sysmon/` and `backend-api/app/endpoint_configs/` (gitignored). New tenant Windows ZIPs then include `windows/Sysmon64.exe`, so the installer does not need Sysinternals at runtime.

Confirm with:

```bash
python3 scripts/verify_e2e_midlayer_edr.py
```

The offline-embed line should be PASSED (no “ZIP has no Sysmon64.exe” warning).

### Linux (primary gap)

Linux installers (ZIP + `curl | sudo bash` one-liner) now:

1. Install **auditd** and load `/etc/audit/rules.d/mssp-exec.rules` (`execve`/`execveat`, key `mssp_exec`).
2. Append a Wazuh `<localfile>` `log_format=audit` reader for `/var/log/audit/audit.log`.
3. Restart `wazuh-agent`.

This is **collect ≠ alert**. Every process is recorded; only high-signal Manager rules (IDs **110001–110005**) raise level ≥ 10 so the existing integratord hook (`POST /integrations/soc/hooks/wazuh/{token}`) still fires. Backend parser `edr_process_tree.py` already maps `data.audit.*` to `raw_source=endpoint_audit_exec`.

Telemetry install is **fail-open**: wazuh-agent enrollment still succeeds if auditd cannot be installed.

### Appliances

Golden VM **199** bake and field upgrade copy Manager rules + the Linux helper, then `_publish_linux_midlayer_shared()` **appends** a Linux `agent_config` block. Existing Windows `mssp-edr-ar-sync` `agent.conf` is not replaced.

## Operator commands

```bash
cd /opt/mssp-control
./scripts/kb105_validate_linux_midlayer_edr.sh
./scripts/kb088_validate_windows_telemetry_onboarding.sh
./scripts/kb105_apply_linux_midlayer_manager.sh    # VM 101
python3 ./scripts/verify_e2e_midlayer_edr.py
./scripts/cache_sysmon_offline.sh                  # optional; offline Windows Sysmon ZIP embed
./kevantic-appliance/scripts/bake_golden_vm199_fleet_reporting.sh
./kevantic-appliance/scripts/upgrade_appliance_fleet_reporting.sh 192.168.0.226 junexis
```

Re-download tenant agent ZIPs after the control-plane rebuild. Existing Linux endpoints pick up the helper from Manager shared config (hourly wodle) or by re-running the installer.

## Cloud / production (no rework)

A `git clone` of this repo on a new cloud host is enough for mid-layer EDR **if** you use the existing deploy scripts:

1. `./scripts/production_deploy_control_plane.sh` caches `Sysmon64.exe` before the Docker build (skip with `MSSP_SKIP_SYSMON_CACHE=1` only when already cached). Air-gapped: copy `Sysmon64.exe` into `/opt/mssp-control/backend-api/app/endpoint_configs/` (never commit it).
2. After Wazuh Manager is installed, run `ansible/playbooks/mssp-linux-midlayer-manager.yml` (listed in `scripts/production_deploy_engines.sh`). It does **not** require lab VM ID 101.
3. Lab shortcut: `WAZUH_MANAGER_HOST=... WAZUH_SSH_KEY=... ./scripts/kb105_apply_linux_midlayer_manager.sh` — copies rules **and** appends Linux `agent.conf` localfile without replacing Windows `mssp-edr-ar-sync`.
4. Proof: `python3 scripts/verify_e2e_midlayer_edr.py` and `./scripts/kb105_validate_linux_midlayer_edr.sh`.

`wazuh-stack-install.yml` still asserts `vm_id == 101` (KB-041). Cloud inventory must set `vm_id: 101` on the Wazuh host until a later KB lifts that lock. That is **not** a KB-105 gap; the mid-layer playbook is already portable.

