# Production release checklist (KB-094)

Use this before any **production** or **cloud** cutover, and after major lab milestones you want to preserve.

## 1. Code freeze

- [ ] All intended changes **committed** on `main` (or release branch)
- [ ] `git status` clean (except intentional local `.env`)
- [ ] Validators PASS for touched modules (see below)

## 2. Tag the release

```bash
cd /opt/mssp-control
git tag -a release-YYYY-MM-DD -m "Production portability release YYYY-MM-DD"
# git push origin release-YYYY-MM-DD   # when remote is configured
```

Record tag name in `docs/AI_PROMPT_LEDGER.md`.

## 3. Backup (mandatory for production)

```bash
python3 scripts/dr_backup_engine.py
bash scripts/dr_cold_copy_control_plane.sh /path/to/MSSP_Full_Backup
```

- [ ] Encrypted DB archive on USB/offsite
- [ ] Cold copy includes `.env` + `.secrets` (never in git)

## 4. Environment pack

- [ ] `.env` from `deploy/environments/control-plane.production.example.env`
- [ ] Engine URLs from `deploy/environments/engines.production.example.env`
- [ ] `APP_ENV=production`
- [ ] `ADMIN_PORTAL_BASE_URL` / `CUSTOMER_PORTAL_BASE_URL` set to real TLS URLs
- [ ] `.secrets/*` populated from vault

## 5. Deploy control plane

```bash
./scripts/production_deploy_control_plane.sh
```

- [ ] `/health` → database + redis ok
- [ ] Admin `:3000` and Customer `:3001` → 200
- [ ] Bad login → **401** (not 502)
- [ ] `python3 scripts/verify_e2e_midlayer_edr.py` → PASSED (Windows ZIP embeds `Sysmon64.exe` when cached; Linux ZIP includes auditd helper)
- [ ] Air-gapped Windows sites: `Sysmon64.exe` present under `backend-api/app/endpoint_configs/` before rebuild (`./scripts/cache_sysmon_offline.sh` or copy the binary; never commit it). Skip with `MSSP_SKIP_SYSMON_CACHE=1` only when you already cached it.

## 6. Bootstrap (fresh production only)

```bash
./scripts/bootstrap_platform_admin.sh
```

- [ ] **Do not** run `scripts/seed_demo_data.sh`

## 7. Engines (when ready)

```bash
# Copy ansible/inventory/production.example.yml → hosts.yml on controller; fill placeholders
MSSP_ENGINE_DEPLOY_APPROVED=1 ./scripts/production_deploy_engines.sh
# Then run approved playbooks per ansible/README.md
# After Wazuh Manager is up:
#   ansible-playbook playbooks/mssp-linux-midlayer-manager.yml
# (listed in production_deploy_engines.sh PLAYBOOK_ORDER; does not install Wazuh)
```

- [ ] Manager has `mssp_linux_exec_rules.xml` (rules 110001–110005)
- [ ] Default shared `agent.conf` includes Linux `mssp-linux-exec-localfile` (Windows `mssp-edr-ar-sync` still present)

## 8. Appliances

- [ ] Golden image **VM 199** (or cloud equivalent) updated from git tag
- [ ] Fleet reporting baked (`./scripts/kb101_validate_golden_fleet_reporting.sh`; live bake: `kevantic-appliance/scripts/bake_golden_vm199_fleet_reporting.sh`)
- [ ] Clone/register per customer; forwarder enabled (KB-093P)
- [ ] Telemetry → SOC control plane; heartbeat → appliance mgmt plane

## 9. Regression validators (minimum)

```bash
./scripts/kb011_validate_protected_apis.sh
./scripts/kb036_validate_mssp_platform_architecture_roadmap.sh
./scripts/kb094_validate_production_portability_pack.sh
./scripts/kb105_validate_linux_midlayer_edr.sh
python3 scripts/verify_e2e_midlayer_edr.py
```

Add module-specific scripts for anything changed since last tag.

## 10. DNS + TLS

- [ ] `admin.kevantic.com` → control plane / reverse proxy
- [ ] `portal.kevantic.com` → customer portal
- [ ] TLS certificates valid; HSTS as per your policy

## 11. Rollback plan

- [ ] Proxmox snapshot or cloud VM image **before** cutover
- [ ] Know which `release-*` tag to redeploy
- [ ] DR passphrase and `.enc` archive location documented offline

---

**Lab note:** You may skip DNS/TLS and use IPs; still tag + backup before large changes.
