# KB-114 — NikTiar Secure Edge (self-hosted WAF / bot edge)

**Status:** Lab MVP live (2026-10-25).  
**Product:** Optional **add-on on any Silver / Gold / Platinum** tier — not a replacement for Edge Node (EDR mid-layer).  
**Related code:** `/opt/mssp-control/niktiar-secure-edge/`, `backend-api/app/api/routes/secure_edge.py`, `postgres/init/050_secure_edge.sql`.

---

## 1. Purpose

Give customers a **Cloudflare-class edge they control**: reverse-proxy WAF + abuse detection in front of their origin (on-prem or cloud VPC), with heartbeats into the NikTiar control plane.

This is **not** “Edge Node” (endpoint/agent plane). Secure Edge sits on **HTTP/S ingress**.

---

## 2. Lab deployment

| Item | Value |
|---|---|
| Proxmox VM | **116** `niktiar-secure-edge` |
| IP | `192.168.0.217` |
| RAM / vCPU | 8 GiB / 4 (reclaimed from VM 115) |
| Stack path on VM | `/opt/niktiar-secure-edge` |
| Public ports | 80 → WAF `:8080`, 443 → WAF `:8443` |

**MVP stack**

1. **WAF** — `owasp/modsecurity-crs:nginx-alpine` (OWASP CRS)  
2. **Abuse** — CrowdSec (`crowdsecurity/crowdsec`) reading nginx logs  
3. **Demo origin** — static nginx banner (replace with real `BACKEND`)  
4. **Agent** — Python heartbeat → `POST /api/v1/secure-edge/heartbeat`

**Coraza + Caddy:** intended long-term stack; GHCR `coraza-caddy` returned registry **denied** during bake. CRS nginx ships first; Coraza swap is Phase 2.

**Smoke checks (lab)**

- `GET http://192.168.0.217/` → **200** (demo origin through WAF)  
- SQLi-style query → **403** (CRS block)

---

## 3. Control plane

| Endpoint | Auth | Role |
|---|---|---|
| `POST /api/v1/secure-edge/heartbeat` | Optional bearer (MVP) | Appliance |
| `POST /api/v1/secure-edge/events` | Optional bearer | Appliance (placeholder) |
| `GET /admin/secure-edge/nodes` | SOC JWT | Admin inventory |

**Schema:** `secure_edge_nodes`; entitlement flag `tenant_entitlements.secure_edge_enabled`.  
**Catalog key:** `secure_edge_waf` — pricing display **Add-on — any tier**.

---

## 4. Ops

```bash
# On VM 116
cd /opt/niktiar-secure-edge
sudo docker compose -f docker/docker-compose.yml --env-file docker/.env ps
sudo docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f waf
```

Point at a real origin: set `BACKEND` / compose env to the customer origin URL and recreate `waf`.

Bootstrap a fresh host: `scripts/bootstrap_host.sh` then sync tree + `scripts/deploy_stack.sh`.

---

## 5. Follow-ups (not blocking MVP)

- Coraza/Caddy image path when registry access works  
- CrowdSec firewall/nginx bouncer enforce mode + portal decisions  
- Hardened appliance API-key auth on heartbeat  
- Customer portal “Secure Edge” status card  
- TLS ACME on edge for production hostnames  
- Multi-site / multi-tenant routing profiles  

---

## 6. Commercial one-liner

**NikTiar Secure Edge** — self-hosted WAF and bot protection as an add-on on any tier; traffic stays in the customer’s VPC or on-prem lab, with SOC visibility in NikTiar.
