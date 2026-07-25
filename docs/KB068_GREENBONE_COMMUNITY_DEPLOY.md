# KB-068 — Greenbone Community Edition Deploy (VM 109)

Status: **Live install completed** — Greenbone Community Edition on VM 109 (`greenbone` / `192.168.0.219`, **9 GB**).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Infrastructure automation + live scanner deploy** — safe-default Ansible role (`preflight` → approved `install` → `validate`).

Builds on: `docs/KB052_GREENBONE_VULNERABILITY_MANAGEMENT_PLAN.md`, `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md`.

Related next: KB-053 (vuln → recommendation workflow), control-plane `vulnerability` schema/adapter (separate KB).

---

## 1. Purpose

Deploy **VM 109 (`greenbone`)** as the MSSP lab **vulnerability scanner** using **Greenbone Community Edition** (official Docker Compose containers).

Greenbone is **SOC-only**. Customers never get the Greenbone UI, raw NVT output, or scan XML/PDF files.

---

## 2. Target VM

| Field | Value |
|---|---|
| **VM ID** | 109 |
| **Hostname** | `greenbone` |
| **Management IP** | `192.168.0.219` |
| **RAM / vCPU / disk** | **9 GB** (8 GB class) / 4 / **80 GB** (official recommended RAM/disk class) |
| **OS** | Ubuntu 24.04 cloud image + cloud-init |
| **NIC** | Single `vmbr0` management (no capture NIC) |
| **GSA UI** | `https://192.168.0.219` (port 443); convenience `:9392` |
| **Default admin user** | `admin` — password stored **host-local only** at `/opt/mssp-greenbone/admin.secret.env` (never Git) |

---

## 3. Architecture

```
Lab assets / protected_assets (tenant-scoped)
  → Greenbone scan tasks on VM 109 (SOC-operated)
  → Findings stay in Greenbone until future MSSP adapter
  → Future: normalize → vulnerability rows → KB-053 recommendations
  → Customer portal: customer-safe summaries only (never raw Greenbone)
```

---

## 4. Customer safety

- No Greenbone console for customers
- No raw scan reports / NVT dumps / IPs in customer APIs (follow KB-052 / KB-036 §9)
- No secrets in Git
- Admin password generated on the scanner host only

---

## 5. Ansible

Safe default = **preflight** (no install).

```bash
# On VM 112 automation controller (rsync from /opt/mssp-control first)
cd /home/secadmin/mssp-automation/ansible

ansible-playbook -i inventory/hosts.yml playbooks/greenbone.yml

ansible-playbook -i inventory/hosts.yml playbooks/greenbone.yml \
  -e greenbone_execution_mode=install \
  -e greenbone_live_install_approved=true

ansible-playbook -i inventory/hosts.yml playbooks/greenbone.yml \
  -e greenbone_execution_mode=validate
```

### What install does

1. Installs Docker Engine + Compose plugin
2. Downloads official `compose.yaml` from Greenbone docs
3. Patches nginx bind from `127.0.0.1` → all interfaces (lab SOC remote access)
4. `docker compose pull` + `up -d`
5. Waits for HTTPS :443
6. Sets a strong `admin` password into host-local secret file
7. Writes install marker under `/var/lib/mssp/greenbone/`

**Note:** First vulnerability feed sync can take a long time in the background. The install marker means **UI is up**, not that every feed is finished.

---

## 6. Explicit deferrals

| Item | Deferred to |
|---|---|
| `vulnerabilities` PostgreSQL schema + adapter | Future control-plane KB |
| Auto high/critical → recommendations | KB-053 implementation |
| Authenticated scan credential UI | Future admin KB |
| Customer vuln summary pages | After adapter + KB-053 |

---

## 7. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb068_validate_greenbone_community_deploy.sh
./scripts/kb068_validate_greenbone_community_deploy.sh
```

Expected final line:

```text
KB-068 GREENBONE COMMUNITY DEPLOY VALIDATION PASSED
```

---

## 8. Rollback (lab)

1. Stop compose on VM 109: `docker compose -f /opt/mssp-greenbone/community/compose.yaml -p greenbone-community-edition down`
2. Optional: remove `/opt/mssp-greenbone` and install marker
3. Optional: stop/delete Proxmox VM 109 — does not affect VM 100 control plane
