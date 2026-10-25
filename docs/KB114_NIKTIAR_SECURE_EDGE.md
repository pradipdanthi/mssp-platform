# KB-114 — NikTiar Secure Edge (complete appliance)

**Status:** Feature-complete lab appliance (2026-10-25).  
**Product:** Add-on on **any** Silver / Gold / Platinum tier.  
**Not** Edge Node (EDR) — this is HTTP(S) ingress WAF / bot edge.

---

## Access

| Surface | URL |
|---|---|
| **Appliance dashboard** | **http://192.168.0.217:9080/** |
| WAF / sites | http://192.168.0.217/ |
| Health | http://192.168.0.217/healthz |
| Admin portal | http://192.168.0.201:3000/ → **Secure Edge** |
| Customer portal | http://192.168.0.201:3001/ → **Secure Edge** |

Dashboard login (lab defaults in `docker/.env`):

- User: `admin`
- Password: `NikTiarEdge!ChangeMe` (**change in production**)

---

## Stack

| Layer | Component |
|---|---|
| WAF | `ghcr.io/coreruleset/coraza-crs:caddy-alpine` |
| Edge | Caddy Host routing + TLS :443 listener + scanner path blocks |
| Abuse | CrowdSec + **firewall bouncer** (iptables) |
| Agent | Heartbeat, site-map sync, ACME site render, event ship |
| Dashboard | Local management UI + APIs on **:9080** |
| Control plane | Nodes / sites / events / admin + customer portals |

**Hybrid multi-tenant**

- `SECURE_EDGE_MODE=shared` — many tenants by `Host` (SMB)
- `SECURE_EDGE_MODE=dedicated` — one tenant per appliance (enterprise)

---

## Features

- Coraza CRS reverse-proxy WAF (block)
- Hybrid site map from control plane + local dashboard add/remove
- CrowdSec detection + firewall enforce
- WAF block event ingest to NikTiar
- Appliance dashboard (overview, sites, blocks, CrowdSec, system)
- Admin Secure Edge page (nodes, sites CRUD, events)
- Customer Secure Edge page (sites + events)
- TLS listener + `tls_mode=acme` generation (needs public DNS)
- Catalog key `secure_edge_waf` / entitlement `secure_edge_enabled`

Lab VM: **116** @ `192.168.0.217`.
