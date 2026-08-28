# KB-093P — Appliance critical-alert forwarder (local Manager → cloud SOC)

Status: Implemented in `kevantic-appliance/` + control-plane ingest.  
Applies to deployment modes: **`on_prem_appliance`**, **`cloud_appliance`**, **`hybrid`** (KB-073).

## Golden image (mandatory — do this once)

This forwarder is part of the **appliance golden image**, not a per-customer manual step.

| Path | How it is baked in |
|------|--------------------|
| ISO firstboot | `ansible/playbooks/install-provision.yml` → `kevantic_runtime` installs unit + module and **fails provision if missing** |
| mkosi postinst | Enables unit when present in image tree |
| `kevantic-cli register` | Ensures forwarder enabled after local Manager comes up |

**After changing KB-093P code, update the golden image once** on Proxmox **VM 199** (`mssp-appliance-golden-build`, `192.168.0.225`). This is the permanent golden disk you clone for new customer appliances — rebuild in place or re-provision from `mssp-appliance-builder` when the recipe changes; do not destroy casually. Every new clone then ships with forwarding already enabled.

### Lab appliance → control-plane routing (locked)

| Traffic | Target (lab) | Why |
|---------|----------------|-----|
| Register / heartbeat / channel jobs | **VM 114** Appliance Mgmt (`192.168.0.224:8000`) | Edge plane for appliance ops |
| Critical-alert telemetry + SOC incidents | **VM 100** Control plane (`192.168.0.201:8000/api/v1/telemetry/ingest`) | Admin/Customer dashboards and `security_alerts` |

Beta (`192.168.0.226`) intentionally uses this split: heartbeat stays on 114; high/critical alert metadata goes to 100.

### Existing field appliances (one-time only)

Boxes built **before** KB-093P (e.g. current Beta) need a single upgrade:

```bash
cd /opt/mssp-control
./kevantic-appliance/scripts/upgrade_existing_appliance_forwarder.sh 192.168.0.226 junexis
# or:
ansible-playbook -i '192.168.0.226,' -e ansible_user=junexis -e ansible_become=true \
  kevantic-appliance/ansible/playbooks/upgrade-critical-alert-forwarder.yml
```

Do **not** treat SSH + manual copy as the normal process.

## Architecture (locked)

```text
Customer endpoints
  wazuh-agent  ──LAN──►  Appliance local Wazuh Manager
                              │
                              ├─ raw logs / datalake stay on-prem
                              └─ high/critical metadata only
                                   ──secure channel──►  Control plane
                                   POST /api/v1/telemetry/ingest
                                   (X-Appliance-ID + X-Appliance-API-Key)
```

Agents **never** enroll to cloud/central SIEM in this model.  
The appliance is the only egress path for SOC-visible alerts.

## What ships

| Piece | Path |
|-------|------|
| Watcher | `kevantic-appliance/appliance/telemetry/critical_alert_watcher.py` |
| Anonymizer | `appliance/common/privacy.py` (`to_cloud_alert`) |
| Buffer + POST | `appliance/telemetry/forwarder.py` |
| systemd unit | `configs/systemd/kevantic-critical-alert-forwarder.service` |
| Install helper | `scripts/install_critical_alert_forwarder.sh` |
| Ansible (future ISO) | `ansible/roles/kevantic_runtime` enables the unit |
| Register hook | `kevantic-cli register` enables forwarder after local Manager |
| CLI one-shot | `kevantic-cli forward-alerts` |
| Cloud ingest | `POST /api/v1/telemetry/ingest` → KB-057 safe alert store |
| Incidents | High/critical appliance alerts open `INC-<TENANT>-APP-*` |

## Forward policy

| Env | Default | Meaning |
|-----|---------|---------|
| `KEVANTIC_FORWARD_MIN_LEVEL` | `10` | Wazuh rule level ≥ 10 → **high** + **critical** |
| (set to `12`) | — | Critical-only |
| `KEVANTIC_WAZUH_ALERTS_PATH` | `/var/ossec/logs/alerts/alerts.json` | Local Manager JSON alert stream |
| `KEVANTIC_TELEMETRY_URL` | from register | `{control_plane}/api/v1/telemetry/ingest` |

On first start / log rotate, the watcher starts at **EOF** (no historical flood).

## Install on an existing appliance (Beta / field)

From the control-plane repo (copy tree to the appliance, then):

```bash
sudo bash /opt/mssp-control/kevantic-appliance/scripts/install_critical_alert_forwarder.sh
# or on the appliance after syncing kevantic-appliance/:
sudo bash ./scripts/install_critical_alert_forwarder.sh
systemctl status kevantic-critical-alert-forwarder --no-pager
```

Generate a level ≥ 10 alert on `linux-endpoint-lab` (local Manager). Within seconds it should appear under Admin → scoped to that tenant.

## Future ISO / new customers

1. Onboard tenant with `deployment_mode=on_prem_appliance` (or `cloud_appliance` / `hybrid`).
2. Issue activation token → `kevantic-cli register` on the appliance.
3. Register enables local Manager + tenant agent group + **critical-alert forwarder**.
4. Endpoints enroll to the **appliance** Manager only.
5. Heartbeat continues to push agent inventory metadata; forwarder pushes high/critical alerts.

## Validate (control plane)

```bash
cd /opt/mssp-control
./scripts/kb093p_validate_appliance_critical_alert_forward.sh
```

## Explicit non-goals

- Do not point customer agents at cloud Wazuh for this model.
- Do not forward raw logs, PCAP, or low/medium noise by default.
- Do not host TheHive on the appliance.

## Related: appliance-local AI gate (KB-108)

Optional Ollama triage runs **inside** `process_event()` before
`TelemetryForwarder` POST. See `docs/KB108_APPLIANCE_LOCAL_AI_TRIAGE.md`.
Default off (`ENABLE_LOCAL_AI_FILTER=false`); fail-open on AI outage.
