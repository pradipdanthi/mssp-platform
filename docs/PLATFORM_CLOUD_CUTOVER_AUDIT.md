# Platform cloud-cutover audit

Status: Snapshot **2026-08-18** (lab VM 100).  
Related: [KB-094](KB094_PRODUCTION_PORTABILITY_PACK.md), [docs/RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), [deploy/RELEASE_CHECKLIST.md](../deploy/RELEASE_CHECKLIST.md).

Lab IPs in this document are **observed runtime evidence**, not recommended cloud inventory. Use `ansible/inventory/production.example.yml` and `deploy/environments/*.production.example.env` for cutover.

**Evidence:** `python3 scripts/verify_platform_state.py --release` on commit `21c5bc6` · Docker/HTTP probes 2026-08-18 17:18 IST · PostgreSQL counts on VM 100 · SSH systemd checks on VMs 101/102/106/108/109/110/114.

---

## Verdict

**Not 100% ready for a zero-gap cloud cutover.**

The architecture pack is cloud-portable: `verify_platform_state.py --release` reports **CLOUD-READY: YES** (94 passed, 0 GAP, 0 FAILED). That proves playbooks, adapters, and schemas exist. It does not prove a fresh cloud region can be stood up with no leftover lab defaults and every engine ingesting.

Remaining work: production `.env` + TLS at the load balancer, override Compose/config lab IP defaults, bake `VITE_APPLIANCE_GATEWAY_URL`, live-install gated engines with inventory hosts, and accept that WAF and Prometheus/Grafana are not product components today.

| Check | Result |
|---|---|
| Verifier CLOUD-READY | YES |
| Passed / GAP / Failed | 94 / 0 / 0 |
| Control plane + both portals | Live |
| Cutover actions still required | 8 (see checklist below) |

Coverage mix of 14 named engines/planes (lab runtime): **5** live ingest · **4** sparse · **3** automation-only · **2** out of product.

---

## 1. Open-source backend engines

Playbooks are inventory-driven (`deployment_role` + `ansible_host`, `wazuh_manager_ip`). Defaults stay preflight until explicit `*_live_install_approved=true`. Engine deploy order lives in `scripts/production_deploy_engines.sh` (dry-run unless `MSSP_ENGINE_DEPLOY_APPROVED=1`).

| Engine | Lab live status | Playbook | API ingest / persist | Cloud action |
|---|---|---|---|---|
| Wazuh 4.14.6 (VM 101) | **LIVE** — manager/indexer/dashboard/filebeat active. API :55000 → 401 (up). :1514/:1515 open. 4,250 `security_alerts`, 3,643 that day, latest 17:19 IST. | `wazuh-stack-install.yml` + `mssp-linux-midlayer-manager.yml` | `POST /integrations/soc/hooks/wazuh/{token}` → `security_alerts` (`source_tool=wazuh`). EDR isolate via AR. | Point `WAZUH_API_URL` at VPC DNS; run live install with approval flags; apply mid-layer rules playbook. |
| Suricata (VM 106) | **LIVE** — systemd `suricata=active`, `wazuh-agent=active`, `eve.json` ~81 MB. SSH :22 open. | `suricata-sensor.yml` + `suricata-wazuh.yml` | NDR table has 6 stale `analysis_adapter` rows (last 2026-08-02). Live path is Wazuh forwarding, not a hot `tenant_ndr_events` stream. | Keep Wazuh-forward path; optionally enable NDR sync so Suricata/Zeek land in `tenant_ndr_events` continuously. |
| Zeek NSM (co-located 106) | **PROCESS UP / UNIT DOWN** — systemd `zeek=inactive` but process `zeek -i enp6s19 local` (pid 1152). Playbook default iface is `enp6s20`. No Zeek rows in NDR table. | `zeek.yml` → `zeek-on-suricata-sensor.yml` (preflight until approved) | Adapter + `INSERT INTO tenant_ndr_events` exist (`ndr.py` / `ndr_service.py`). Not continuously ingesting. | Set capture iface from inventory; enable systemd unit; wire `notice.log` → Wazuh or NDR puller. |
| TheHive + Shuffle (VM 102) | **LIVE** — :9000 TheHive HTML 200; Shuffle :3001 HTML 200. Docker Swarm services up (thehive_*, shuffle-tools, http, email). | `case-soar.yml` | `THEHIVE_URL` + `SHUFFLE_WEBHOOK_URL_FILE` secrets. Cases/SOAR, not customer UI. | Replace lab URL defaults in Compose; TLS + private DNS; keep `THEHIVE_DEFAULT_ORG=MSSP`. |
| MISP-compatible API (VM 108) | **LIVE** — `mssp-misp-api.service` active. GET :8080/health → version `2.4.mssp`. This is the MSSP REST bridge, not full MISP UI. | `misp.yml` (systemd + host-generated API key) | `misp_client.py` → `threat_intel.py` `INSERT tenant_threat_intel_iocs`. 12 IOCs; latest 2026-08-12. | Use production `MISP_URL`; copy host key into `.secrets/misp_api_key`; optional later: official MISP Docker UI. |
| Velociraptor (VM 110) | **LIVE** — `velociraptor.service` + `mssp-velociraptor-bridge` active. GUI :8889 → 401; bridge :8001 listening (404 on `/`). | `velociraptor.yml` (preflight until approved) | `velociraptor_client.py` → `tenant_forensics_collections` (5 rows; latest that day 12:37 IST). | Set `VELOCIRAPTOR_SERVER_URL`; do not leave Compose default `192.168.0.220`. |
| Greenbone CE (VM 109) | **LIVE** — GSA :443 HTML 200. Docker: nginx, gsad, gvmd (healthy), ospd-openvas, openvasd, pg-gvm, redis. | `greenbone.yml` | Vuln adapters + `tenant_vulnerability_findings` (18 rows). Customer sees capability labels only. | Private hostname; keep scanners off the control-plane VM. |
| Nuclei (VM 109) | **BINARY PRESENT / AGENT INACTIVE** — `/opt/mssp-vuln-free/bin/nuclei` exists. `mssp-vuln-scan-agent` systemd inactive. 1 `vulnerabilities` row `source_platform=nuclei`. | `vuln-free-stack.yml` | POST vuln sync → `vulnerabilities` / `tenant_vulnerability_findings`. | Enable scan agent on cloud host after playbook install. |
| Vuls (VM 109) | **NOT INSTALLED** — no `/opt/mssp-vuln-free/bin/vuls`. | `vuln-free-stack.yml` | Schema allows source `vuls`; `customer_safe_labels` maps it. No live Vuls findings. | Run vuln-free-stack live install so the Vuls binary is present. |
| Sysmon / auditd (mid-layer EDR) | **PACKAGED / SPARSE INGEST** — ZIP builders + Manager rules 110001–110005 in git. 1 `edr_process_events` row (2026-08-12). 37 isolate executions. | `mssp-linux-midlayer-manager.yml`; Windows ZIP via control-plane deploy | Wazuh hook persists process-tree (`soc_sync.py`). Isolate AR hold-until-unisolate (KB-104). | Enroll endpoints with telemetry bootstrap; confirm rules on Manager after playbook. |
| WAF / OSPC | **NOT A DEPLOYED ENGINE** — no ModSecurity, Coraza, or open-appsec in repo. “Firewalls / WAF / VPN” is only an alert taxonomy label. | None | None | Do not list as a cutover engine. Add only via a future named KB. |
| Prometheus / Grafana (VM 111) | **NOT LIVE** — `192.168.0.221:3000` closed. Inventory placeholder only. | No production playbook in `PLAYBOOK_ORDER` | Not wired as a customer/SOC data source. | Optional observability later — not required for MSSP product cutover. |
| Appliance mgmt plane (VM 114) | **LIVE :8000** — GET `/health` → 200, plane `appliance_management`, `APP_ENV=development`. Docker + DB tunnel to VM 100. | Kevantic appliance tree (not SOC `PLAYBOOK_ORDER`) | Register/heartbeat/channel; isolate path VM 100 → 114 → Manager → agent. | TLS; `APP_ENV=production`; no hardcoded `192.168.0.224` in admin UI build. |
| EASM / Amass (co-located 109) | **HISTORICAL DATA** — 12 `tenant_easm_findings`. `mssp-easm-scan-agent` inactive. | `easm-recon-stack.yml` (exists, not in `PLAYBOOK_ORDER`) | `easm_sync` routes + tables exist. | Add to cloud runbook if EASM is in the first cutover wave. |

---

## 2. Frontend dashboards and portals

### Admin / SOC portal (`frontend-admin`, :3000)

- HTTP 200. Dummy login POST → **401** (proxy + auth alive). Login sends `portal: "admin"`; staff-only roles.
- `API_PREFIX="/api"` (relative). nginx `resolver 127.0.0.11` re-resolves `backend-api`. Dockerfile is a static Vite build.
- **Gap:** `frontend-admin/src/config/applianceGateway.ts` defaults `VITE_APPLIANCE_GATEWAY_URL` to `http://192.168.0.224:8000`. Dockerfile does not pass that build arg.

### Customer portal (`frontend-customer`, :3001)

- HTTP 200. Dummy login → **401**. Login sends `portal: "customer"`. Customer UI does not call `/admin`.
- Tenant mismatch → **404** via `require_tenant_match`. Customer-safe labels hide engine product names. Same `/api` nginx pattern.
- TLS: neither portal nginx listens 443. Cloud TLS belongs on the load balancer; set `ADMIN_PORTAL_BASE_URL` / `CUSTOMER_PORTAL_BASE_URL` / `CORS_ALLOWED_ORIGINS` in production `.env` (templates already use `admin.kevantic.com` / `portal.kevantic.com`).

| Auth / tenancy control | Evidence | Cloud-ready? |
|---|---|---|
| JWT + bcrypt auth | `POST /auth/login`, `GET /auth/me`, portal field on both frontends | Yes — no portal hostname in the SPA fetch path |
| Portal split | `_enforce_portal_login` in `auth.py`; admin vs customer role sets | Yes |
| RBAC on `/admin` | `Depends(require_roles(*ADMIN_SOC_ROLES))` on admin routers | Yes |
| Customer isolation | `require_tenant_match` → HTTP 404; `customer_visible` filters | Yes |
| CORS / public URLs | `CORS_ALLOWED_ORIGINS` override; defaults still include `192.168.0.201` | Override in production `.env` (template already does) |
| Appliance register command in Admin UI | Hardcoded lab gateway unless `VITE_APPLIANCE_GATEWAY_URL` at build | Must set at image build / rebuild |

---

## 3. Control plane, pipeline, and lab leftovers

- **Compose stack (VM 100):** `mssp-postgres` healthy, `mssp-redis` healthy, `mssp-backend-api` :8000, both frontends. `/health` → api/database/redis ok. `APP_ENV=development` (not production). `postgres/init/` holds additive migrations 001–035+.
- **196 FastAPI paths** loaded by the verifier. Required routes present: Wazuh hook, NDR, threat-intel, forensics, EDR execute. Active response is scripted (`deploy/wazuh-active-response`) not hardcoded to a playbook VM ID.
- **Deploy scripts:** `production_deploy_control_plane.sh` + `production_deploy_engines.sh` + env templates under `deploy/environments/`. Engine script still defaults `MSSP_ANSIBLE_CONTROLLER` to `192.168.0.222` — override with env on cloud.

### Hardcoded lab defaults that still exist (must override, not spoof VM IDs)

Ansible roles no longer assert `(vm_id | int) == N`. Inventory `production.example.yml` uses placeholders and `deployment_role`. Verifier GAP for those locks is closed.

| Location | What is hardcoded | Risk if you forget |
|---|---|---|
| `docker-compose.yml` | Default WAZUH/THEHIVE/MISP/VELOCIRAPTOR URLs = `192.168.0.x` | Cloud API keeps talking to the lab |
| `backend-api/app/core/config.py` | `WAZUH_MANAGER_HOST`, `CONTROL_PLANE_HOST`, SHUFFLE/THEHIVE/GREENBONE/SURICATA defaults | Same — env must win |
| `backend-api/app/core/cors.py` | Lab origins `192.168.0.201:3000/3001` if `CORS_ALLOWED_ORIGINS` unset | Wrong browser origin allow-list |
| `frontend-admin` `applianceGateway.ts` | `http://192.168.0.224:8000` | Admin copy-paste register commands point at lab VM 114 |
| `scripts/production_deploy_engines.sh` | `MSSP_ANSIBLE_CONTROLLER` default `192.168.0.222` | Engine sync targets the lab bastion |

---

## 4. Master summary

| Component | Lab live status | Cloud automation ready? | Action required for cloud |
|---|---|---|---|
| Control plane API + Postgres + Redis | Live (`APP_ENV=development`) | Yes — Compose + `production_deploy_control_plane.sh` | `APP_ENV=production`; fill `.env` from `control-plane.production.example.env`; TLS at LB |
| Admin portal :3000 | Live 200 / login 401 | Yes — nginx + relative `/api` | Rebuild with `VITE_APPLIANCE_GATEWAY_URL`; map `admin.kevantic.com` |
| Customer portal :3001 | Live 200 / login 401 | Yes — never calls `/admin` | Map `portal.kevantic.com`; CORS override |
| Wazuh | Live, ingesting (3,643 alerts that day) | Yes | New hosts + `WAZUH_API_URL`; mid-layer playbook |
| Suricata | Live `eve.json` + Wazuh agent | Yes | Inventory `ansible_host`; optional NDR sync |
| Zeek | Process up, systemd down; no NDR stream | Yes (gated playbook) | Approve live install; fix capture iface; ingest path |
| TheHive / Shuffle | Live Docker/Swarm | Yes | Private URLs + secrets files |
| MISP bridge | Live systemd API | Yes | `MISP_URL` + API key file; not full MISP UI |
| Velociraptor | Live server + bridge | Yes | `VELOCIRAPTOR_SERVER_URL`; no lab IP default |
| Greenbone CE | Live Docker GSA | Yes | Keep off control plane |
| Nuclei | Binary present, agent off | Yes | Enable scan agent |
| Vuls | Not installed | Yes (playbook) | Run vuln-free-stack live install |
| Sysmon / auditd EDR | Packaged; 1 process-tree row | Yes | Enroll endpoints with telemetry ZIP |
| Isolate / AR | 37 executions recorded | Yes (scripts, not VM-ID locked) | Manager allow 1514/1515 in cloud netpolicy |
| Appliance mgmt VM 114 | Live :8000 health | Partial (separate tree) | TLS; production `APP_ENV`; UI gateway URL |
| EASM | 12 old findings; agent inactive | Playbook exists, not in deploy order | Include only if first-wave scope |
| WAF / OSPC | Not in platform | No | Out of scope unless a new KB |
| Prometheus / Grafana | Host dark | No playbook in cutover order | Optional later |

---

## Cutover checklist (do these before calling it 100%)

1. Copy `deploy/environments/control-plane.production.example.env` and `engines.production.example.env` — no `192.168.0.x` left in runtime env.
2. Terminate TLS on the cloud load balancer; keep portal nginx on :80 inside Compose.
3. Rebuild Admin image with `VITE_APPLIANCE_GATEWAY_URL` pointing at the cloud appliance-management hostname.
4. Copy `ansible/inventory/production.example.yml` → controller `hosts.yml`; set `mssp_home_net` and `ansible_host` values.
5. Set `MSSP_ANSIBLE_CONTROLLER` + `MSSP_ENGINE_DEPLOY_APPROVED=1`, then per-playbook live flags (never a blind all-in).
6. Install Vuls via `vuln-free-stack`; enable Nuclei/EASM agents if those products are sold on day one.
7. Confirm Wazuh hook token, Shuffle webhook, and MISP/Velociraptor keys in `.secrets/` (never git).
8. Re-run `python3 scripts/verify_platform_state.py --release` on the cloud tree after env substitution.
