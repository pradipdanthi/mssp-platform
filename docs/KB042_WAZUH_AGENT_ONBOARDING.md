# KB-042 — Wazuh Agent Onboarding (Windows / Linux)

Status: Automation prepared for Linux preflight; Windows remains a deferred stub.
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / safe-default Ansible** — **NOT** live agent enrollment until
endpoint VMs exist and enrollment is separately approved.

Builds on: **KB-036**, **KB-037**, **KB-038**, **KB-039**, **KB-040**, and **KB-041**
(Wazuh Manager on VM 101 is now live).

---

## 1. Purpose

Define **Wazuh agent onboarding** for lab endpoint VMs and provide Ansible
automation for:

- **Linux agents** — `ansible/playbooks/wazuh-agent-linux.yml` + role `wazuh_agent`
- **Windows agents** — `ansible/playbooks/wazuh-agent-windows.yml` (stub)

Agents register with the Wazuh Manager on **VM 101** (`192.168.0.211`). Enrollment
keys come from **Vault** — **no secrets** in Git.

---

## 2. VM references

| VM | Hostname | OS | Role | Status |
|---|---|---|---|---|
| **VM 104** | `windows-endpoint-lab` | Windows | Wazuh agent — Windows onboarding test | Not provisioned (`192.168.0.214`) |
| **VM 105** | `linux-endpoint-lab` | Linux | Wazuh agent — Linux onboarding test | **Decommissioned** — VM removed from Proxmox; manual Ubuntu reinstall at operator discretion (reuse VMID 105 / `192.168.0.215` when ready) |
| **VM 101** | `wazuh-stack` | Linux | Wazuh Manager — enrollment target | **Live** — Wazuh 4.14.6 |

Ansible groups: `endpoint_lab` (hosts), `wazuh_stack` (manager).

---

## 3. Onboarding flow (planned)

### 3.1 Cloud / hybrid tenants (KB-038)

```
Endpoint (VM 104/105 or customer host)
  → Wazuh agent installed
  → Registers with Manager on VM 101 (or tenant-assigned cluster)
  → Agent appears in manager + appliance registry (KB-037 deployment_role)
  → Alerts normalized via MSSP adapter → control plane → customer-safe summary
```

### 3.2 On-prem tenants

- Agents register with **on-prem appliance Manager** — not VM 101
- Only metadata syncs to control plane — **raw logs never leave customer site**

---

## 4. Prepared automation

| File | Target hosts | Purpose |
|---|---|---|
| `wazuh-agent-linux.yml` | `linux-endpoint-lab` | Role-driven preflight / enroll / validate |
| `roles/wazuh_agent/` | VM 105 only | Identity, OS, disk, Manager port reachability, enrollment gate |
| `wazuh-agent-windows.yml` | `windows-endpoint-lab` | Deferred stub until VM 104 exists |

### 4.1 Safety interlocks (Linux)

- Defaults: `wazuh_agent_execution_mode=preflight` and
  `wazuh_agent_live_enroll_approved=false`
- Enrollment requires a non-placeholder Vault/runtime enrollment password
- Role refuses any host except `vm_id=105` / `deployment_role=wazuh_agent_linux`
- Manager address is the public lab IP `192.168.0.211` (not a secret)

Windows playbook remains a **stub** with deferred install steps.

---

## 5. Relationship to KB-036 / KB-037 / KB-038

| KB | Relevance |
|---|---|
| **KB-036** | VM 104/105 endpoint lab layout; Wazuh agents as collection layer |
| **KB-037** | Agent host maps to appliance registry (`deployment_role`, `source_platform`) |
| **KB-038** | Cloud/hybrid agents enroll to shared cluster; on-prem agents stay local |

---

## 6. Security and no secrets

- Wazuh enrollment password / auth key: **Vault only**
- Manager address for lab is documented; credentials never are
- Never expose agent keys in customer APIs or portal
- Appliance registration tokens (KB-016) remain separate from Wazuh enrollment

---

## 7. Customer safety

- Agents collect endpoint telemetry for **SOC processing** — customers see normalized alert summaries only
- Customer portal: **no raw logs**, **no agent enrollment keys**, **no manager internal URLs**
- Wrong-tenant agent assignment prevented by control-plane appliance registry + tenant isolation (future enforcement KB)

---

## 8. Deferred live execution

| Item | Deferred to |
|---|---|
| VM 104/105 provisioning | Next lab ops step (Linux first) |
| Wazuh Manager on VM 101 | **Complete** — KB-041 live install |
| Manager API / Dashboard reachability | Confirmed from VM 112 (API HTTP 401 auth challenge; Dashboard HTTP 302) |
| `ansible-playbook wazuh-agent-linux.yml` enroll mode | After VM 105 exists + Vault secret + separate approval |
| Windows stub → full role | After VM 104 exists |
| Appliance ↔ agent linkage in DB | Future implementation KB |
| Production GPO / MDM deployment | Out of scope — document only |

**KB-042 does not enroll live agents yet.** Package install remains deferred.

---

## 9. What KB-042 changes (and must not)

### Changes

- `docs/KB042_WAZUH_AGENT_ONBOARDING.md` (this file)
- `scripts/kb042_validate_wazuh_agent_onboarding.sh`
- `ansible/playbooks/wazuh-agent-linux.yml`
- `ansible/playbooks/wazuh-agent-windows.yml`
- `ansible/roles/wazuh_agent/defaults/main.yml`
- `ansible/roles/wazuh_agent/tasks/main.yml`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 10. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb042_validate_wazuh_agent_onboarding.sh
./scripts/kb042_validate_wazuh_agent_onboarding.sh
```

Expected final line:

```text
KB-042 WAZUH AGENT ONBOARDING VALIDATION PASSED
```
