# KB-048 — Shuffle SOAR Deployment Plan (VM 103)

Status: Implemented (pending validation/commit).  
Branch: `kb039-kb060-platform-roadmap-execution`  
Module type: **Planning / documentation only** — no runtime code, schema, compose, or `.env` changes.

Builds on: `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md`, `docs/KB037_CLUSTER_APPLIANCE_REGISTRY_PLANNING.md`, `docs/KB047_THEHIVE_DEPLOYMENT_PLAN.md`.

---

## 1. Purpose

Define the **lab deployment plan** for **Shuffle SOAR** on **VM 103** (`shuffle`) — playbook orchestration, webhook endpoints, integration credentials model, and connectivity to Wazuh (VM 101) and TheHive (VM 102) — before the end-to-end workflow KB-049.

This KB is **planning only**. No VM creation, Shuffle install, or live playbooks in this module.

---

## 2. Current baseline

| Area | Status |
|---|---|
| VM 103 `shuffle` | **Not created** — roadmap placeholder (KB-036) |
| Shuffle SOAR | **Not deployed** |
| Wazuh webhooks / API | **Not configured** — KB-040/041 |
| TheHive API | **Not available** — KB-047 |
| Control plane automation | No Shuffle adapter — future KB-057+ |

---

## 3. Architecture

### 3.1 Shuffle role in MSSP stack

Shuffle is the **automation orchestration layer** between detection tools and case management:

- Receives alerts (webhook, polling, or API) from Wazuh and future sources
- Runs playbooks: enrich, deduplicate, route, escalate
- Creates/updates TheHive cases via API
- May call future MISP/Greenbone integrations (KB-050+)

```
Alert sources (Wazuh VM 101, future Suricata/Zeek rules)
  → Shuffle webhooks / workflows (VM 103)
  → TheHive case API (VM 102)
  → Optional notifications / control-plane hooks (future)
```

### 3.2 Planned VM specification (lab)

| Item | Planned value |
|---|---|
| VM ID | **103** |
| Hostname | `shuffle` |
| OS | Ubuntu LTS (KB-039 baseline) |
| vCPU / RAM | 4 vCPU, 8 GB RAM minimum |
| Disk | 40+ GB |
| Network | Reachable from VM 101 (Wazuh) and VM 102 (TheHive); not customer-facing |

### 3.3 Deployment components (implementation checklist — not executed in KB-048)

1. Create VM 103 in Proxmox.
2. Deploy Shuffle (Docker Compose or KB-039 playbook).
3. Configure Shuffle org, admin user, API keys — **secrets in env only**.
4. Document inbound webhook URL pattern for Wazuh integration (KB-049).
5. Store TheHive API credentials in Shuffle encrypted app auth — not in Git.
6. Health check: Shuffle UI login, test workflow execution, outbound API to TheHive.

---

## 4. VM references

| VM | Name | Role |
|---|---|---|
| **VM 103** | `shuffle` | Shuffle SOAR — **this KB's focus** |
| **VM 101** | `wazuh-stack` | Primary alert source for playbooks |
| **VM 102** | `thehive` | Case destination for playbook actions |
| **VM 100** | `mssp-control` | Future metadata/notifications — not raw playbook internals |

---

## 5. Tenant isolation

- Playbooks must **propagate `tenant_id` or tenant short code** into every TheHive case they create.
- Planning rules:
  - Wazuh alert → tenant mapping resolved in playbook (agent group, rule tag, or lookup table)
  - No playbook may create a case without tenant context when alert is tenant-scoped
  - Shuffle execution logs with raw alert payloads — **SOC only**, never customer API
- Customer portal: no Shuffle URLs, workflow IDs, or execution logs.

---

## 6. Customer portal safety

Customer portal must **never** expose:

- Shuffle playbook definitions, execution logs, or webhook URLs
- **Raw logs** from Wazuh, Suricata, or Zeek in customer-facing APIs
- Raw Wazuh/Suricata/Zeek payloads passed through workflows
- Shuffle or TheHive API credentials
- Internal automation error stack traces

Customers receive outcomes only via **normalized incidents/alerts** in the control plane (KB-057).

**No secrets** in Git, docs, or customer API responses.

---

## 7. Relationship to prior KBs

| KB | Relationship |
|---|---|
| **KB-036** | Shuffle in SOAR phase; VM 103 placement |
| **KB-037/038** | Tenant mapping inputs for playbooks |
| **KB-039** | Ansible deployment for VM 103 |
| **KB-040/041** | Wazuh stack alert export to Shuffle |
| **KB-047** | TheHive API target for case creation |
| **KB-049** | Reference workflow: Wazuh → Shuffle → TheHive |
| **KB-057** | Control-plane sync of case outcomes to `incidents` |

---

## 8. Explicit deferrals

| Item | Deferred to |
|---|---|
| VM 103 provisioning | KB-048 implementation KB |
| Shuffle install and org setup | KB-048 implementation KB |
| Production playbook library | KB-049 + ops KB-060 |
| Wazuh webhook configuration | KB-049 |
| MISP/Greenbone playbook apps | KB-050–053 |
| Customer notification from Shuffle | Future notification worker KB |

---

## 9. Decision summary (approved defaults)

| # | Decision | Choice |
|---|---|---|
| D1 | SOAR VM | VM 103 `shuffle` |
| D2 | Primary upstream | Wazuh Manager alerts (VM 101) |
| D3 | Primary downstream | TheHive API (VM 102) |
| D4 | Tenant context | Mandatory in automated case-creation playbooks |
| D5 | Secrets | Shuffle/TheHive credentials in env — **no secrets** in Git or docs |

---

## 10. What KB-048 changes (and must not)

### Changes

- `docs/KB048_SHUFFLE_SOAR_DEPLOYMENT_PLAN.md` (this file)
- `scripts/kb048_validate_shuffle_soar_deployment_plan.sh`

### Must not change

- `backend-api/`, `frontend-customer/`, `frontend-admin/`
- `postgres/init/`, `docker-compose.yml`, `.env`

---

## 11. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb048_validate_shuffle_soar_deployment_plan.sh
./scripts/kb048_validate_shuffle_soar_deployment_plan.sh
```

Expected final line:

```text
KB-048 SHUFFLE SOAR DEPLOYMENT PLAN VALIDATION PASSED
```
