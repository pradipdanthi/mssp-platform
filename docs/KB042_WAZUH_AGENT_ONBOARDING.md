# KB-042 — Wazuh Agent Onboarding (Windows / Linux)

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / Ansible playbook stubs only** — **NOT** live agent enrollment.

Builds on: **KB-036** (`docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`), **KB-037**, **KB-038**, **KB-039**, **KB-040**, and **KB-041**.

---

## 1. Purpose

Define **Wazuh agent onboarding** for lab endpoint VMs and document Ansible playbook stubs for:

- **Linux agents** — `ansible/playbooks/wazuh-agent-linux.yml`
- **Windows agents** — `ansible/playbooks/wazuh-agent-windows.yml`

Agents register with the Wazuh Manager on **VM 101** (when deployed). Enrollment keys and manager addresses come from **Vault** — never Git.

---

## 2. VM references

| VM | Hostname | OS | Role |
|---|---|---|---|
| **VM 104** | `windows-endpoint-lab` | Windows | Wazuh agent — Windows onboarding test |
| **VM 105** | `linux-endpoint-lab` | Linux | Wazuh agent — Linux onboarding test |
| **VM 101** | `wazuh-stack` | Linux | Wazuh Manager — enrollment target |

Ansible groups: `endpoint_lab` (hosts), `wazuh_stack` (manager).

---

## 3. Onboarding flow (planned)

### 3.1 Cloud / hybrid tenants (KB-038)

```
Endpoint (VM 104/105 or customer host)
  → Wazuh agent installed
  → Registers with Manager on VM 101 (or tenant-assigned cluster)
  → Agent appears in manager + appliance registry (KB-037 deployment_role = cloud_collector)
  → Alerts normalized via MSSP adapter → control plane → customer-safe summary
```

### 3.2 On-prem tenants

- Agents register with **on-prem appliance Manager** — not VM 101
- Only metadata syncs to control plane — **raw logs never leave customer site**

---

## 4. Playbook stubs

| File | Target hosts | Purpose |
|---|---|---|
| `wazuh-agent-linux.yml` | `linux-endpoint-lab` | Install agent package, configure manager address, start service |
| `wazuh-agent-windows.yml` | `windows-endpoint-lab` | Install MSI, configure manager, register agent |

Both stubs use `debug` tasks only — no package installs until VMs exist.

---

## 5. Relationship to KB-036 / KB-037 / KB-038

| KB | Relevance |
|---|---|
| **KB-036** | VM 104/105 endpoint lab layout; Wazuh agents as collection layer in cloud data flow |
| **KB-037** | Agent host maps to appliance registry (`deployment_role`, `source_platform`) |
| **KB-038** | Cloud/hybrid agents enroll to shared cluster; on-prem agents stay local |

---

## 6. Security and no secrets

- Wazuh enrollment password / auth key: **Vault only**
- Manager URL placeholder in group_vars — real value at deploy time
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
| VM 104/105 provisioning | Lab ops / future KB |
| Wazuh Manager on VM 101 | KB-041 live execution |
| `ansible-playbook wazuh-agent-*.yml` | After manager + endpoints exist |
| Appliance ↔ agent linkage in DB | Future implementation KB |
| Production GPO / MDM deployment | Out of scope — document only |

**KB-042 does not enroll live agents.**

---

## 9. What KB-042 changes (and must not)

### Changes

- `docs/KB042_WAZUH_AGENT_ONBOARDING.md` (this file)
- `scripts/kb042_validate_wazuh_agent_onboarding.sh`
- `ansible/playbooks/wazuh-agent-linux.yml`, `ansible/playbooks/wazuh-agent-windows.yml`

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
