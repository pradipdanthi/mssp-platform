# KB-078 — Nuclei + Vuls Free Vulnerability Stack ($0)

Status: **Approved install** — primary free vulnerability scanning stack until ~5–10 customers (no paid Greenbone Enterprise license yet).  
Module type: Infrastructure install + Ansible automation + control-plane source tags.  
Date: 2026-07-28  
Branch: `kb039-kb060-platform-roadmap-execution`

Builds on: KB-052, KB-068–070, KB-077 (Enterprise deferred), KB-069 vuln sync contract.

---

## 1. Locked decision (this module)

| Decision | Value |
|---|---|
| Primary free scanners | **Nuclei** (ProjectDiscovery) + **Vuls** (future-architect) |
| Cost | **$0** license — OSS only |
| Greenbone Community (VM 109) | **Keep running** as optional classic NVT backup — not the paid Enterprise path |
| Greenbone Enterprise | **Deferred** until customer volume justifies spend (see KB-077) |
| Customer exposure | Never — no Nuclei/Vuls/Greenbone UIs for customers |
| Control plane | Findings normalize through existing `POST /integrations/vuln/sync` (`source_platform`: `nuclei` / `vuls`) |

---

## 2. Honest coverage vs Greenbone

**Condition you set:** install only if they cover **better than Greenbone**.

| Dimension | Greenbone Community | Nuclei + Vuls (together) | Verdict for $0 MSSP |
|---|---|---|---|
| Modern CVE / misconfig / web / network templates | Weaker (Community Feed) | **Stronger** (Nuclei templates, frequent updates) | Free stack wins |
| Host OS package CVEs (Ubuntu/Debian/RHEL…) | Partial via NVTs | **Stronger** (Vuls + OVAL/gost/NVD) | Free stack wins |
| Classic deep network NVT / some appliance checks | **Stronger** (OpenVAS engine) | Weaker | Keep Greenbone CE as backup |
| Full Greenbone **Enterprise Feed** (paid) | N/A on CE | Does **not** match paid Enterprise | Still deferred |

**Bottom line:** Nuclei + Vuls together give **better overall free MSSP coverage** than Greenbone Community alone for modern exposure and host CVEs. They do **not** replace paid Greenbone Enterprise. We keep CE optional until Enterprise is purchased later.

---

## 3. Install locations

| Phase | Host | Path | Notes |
|---|---|---|---|
| **Live target** | VM 109 `greenbone` (`192.168.0.219`) | `/opt/mssp-vuln-free` | Co-located with Greenbone CE — scanners stay **off** the control plane |
| Access | SSH as `secadmin` + `sudo` | Key: `~/.ssh/id_ed25519_greenbone` (Host `greenbone` in SSH config) | **Root SSH login is not used** |

Control plane (VM 100) must **not** host Nuclei/Vuls binaries or Vuls Docker images.


---

## 4. Architecture

```
Protected assets / agreed scan targets (tenant-scoped)
  → Nuclei (template CVE/misconfig/web/network) and/or Vuls (host package CVEs)
  → SOC normalizes → POST /integrations/vuln/sync (source_platform=nuclei|vuls)
  → vulnerabilities + optional recommendations (KB-053/069)
  → Customer portal: customer-safe summaries only
```

Optional: Greenbone CE → existing KB-070 hook path remains available.

---

## 5. Customer safety

- No Nuclei/Vuls console for customers
- No raw JSON, template IDs as customer copy, IPs, or internal notes in customer APIs
- No secrets in Git
- Scan results stay SOC/backend until promoted

---

## 6. Ansible (safe default = preflight)

Targets **VM 109 only** (`vuln_free_stack` inventory group). SSH as `secadmin` with become.

```bash
cd /opt/mssp-control/ansible

ansible-playbook -i inventory/hosts.yml playbooks/vuln-free-stack.yml

ansible-playbook -i inventory/hosts.yml playbooks/vuln-free-stack.yml \
  -e vuln_free_execution_mode=install \
  -e vuln_free_live_install_approved=true

ansible-playbook -i inventory/hosts.yml playbooks/vuln-free-stack.yml \
  -e vuln_free_execution_mode=validate
```

---

## 7. Live install (on VM 109)

```bash
# From control plane (VM 100) — uses Host "greenbone" SSH config
ssh greenbone 'sudo bash -s' < /opt/mssp-control/scripts/kb078_install_vuln_free_stack.sh

# Or skip long first DB fetch:
FETCH_VULN_DBS=0 ssh greenbone 'sudo -E bash -s' < /opt/mssp-control/scripts/kb078_install_vuln_free_stack.sh
```

What it does:

1. Creates `/opt/mssp-vuln-free` on **VM 109**
2. Installs Nuclei binary (pinned release) + updates official templates
3. Pulls Vuls Docker images (`vuls/vuls`, dictionaries)
4. Fetches essential vulnerability DBs (NVD + Ubuntu OVAL + gost + KEV) — **first run can take a long time**
5. Writes host-local `config.toml` stub (no secrets in Git)
6. Writes install marker under `/var/lib/mssp/vuln-free/`

Validate (from control plane; checks docs + remote VM 109):

```bash
./scripts/kb078_validate_nuclei_vuls_free_stack.sh
```

---

## 8. Ops notes

| Item | Detail |
|---|---|
| Nuclei version (initial pin) | `3.11.0` (update intentionally) |
| Nuclei templates | Updated on install via `nuclei -update-templates` |
| Vuls | Docker images on VM 109; SQLite DBs under `/opt/mssp-vuln-free/vuls/` |
| SSH | `secadmin` + sudo become — not root-over-SSH |
| Scan approval | Do not scan customer networks without written scope |
| Adapter pullers | Future KB — normalize JSON → vuln sync (same contract as KB-069) |

---

## 9. Out of scope (this KB)

- Paid Greenbone Enterprise license/appliance
- Automatic customer-facing Vulnerability page unlock (still entitlement-driven)
- Full multi-tenant scan orchestration UI
- Replacing Greenbone CE containers on VM 109
