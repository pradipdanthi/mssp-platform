# KB-114 — NikTiar™ Secure Edge

**Status:** v4.1 DNS Filter + NGFW pack (2026-10-26) — NikTiar WAF, Firewall, URL Filter, DNS Filter, Bot Defense.

---

## Access

| Surface | URL |
|---|---|
| **Appliance dashboard (NikTiar WAF + Firewall)** | **http://192.168.0.217:9080/** |
| Edge traffic | http://192.168.0.217/ |
| Admin portal | http://192.168.0.201:3000/secure-edge |
| Customer portal | http://192.168.0.201:3001/secure-edge |

Dashboard login: `admin` / `EDGE_DASHBOARD_PASSWORD` (default lab password — rotate for prod).

---

## Product capabilities (NikTiar names only)

| Capability | What operators configure |
|---|---|
| **NikTiar™ Zones** | Public hostname → origin |
| **NikTiar™ WAF** | Security Level, managed rules, simulate/block, Under Attack Mode |
| **NikTiar™ custom WAF rules** | Simple expressions (`path contains …`) |
| **NikTiar™ Firewall** | IP allow/block, UA block, geo block |
| **NikTiar™ NGFW policies** | Ordered Allow / Deny / Challenge |
| **NikTiar™ URL Filter** | Category + custom path filtering |
| **NikTiar™ DNS Filter** | Category feeds + domain blocklists (UDP/TCP 53); optional WAF Host mirror |
| **NikTiar™ Rate Limit** | Per-path throttling (HTTP 429) |
| **NikTiar™ Bot Defense** | Scanner/bot abuse decisions |
| **SSL / TLS modes** | off / flexible / full / strict |
| **Caching** | Bypass / Standard (+ edge TTL) |
| **Analytics** | Requests & blocks |
| **Advanced defenses** | API Shield, GraphQL Guard, Page Shield, Waiting Room, Virtual Patching, Auth Hardening, Sensitive Data Detection, Honeypot, Advanced Bot/PoW, Leaked Credentials, Logpush, mTLS |

Configure on the appliance: **How this works** → policies / URL Filter / DNS Filter / NikTiar WAF → **Apply changes**.

Product naming standard: `docs/NIKTIAR_PRODUCT_NAMES.md` (never show upstream package brands in UI).

---

## NikTiar DNS Filter

| Item | Detail |
|---|---|
| Listen | UDP/TCP **53** on the edge LAN IP (`NIKTIAR_DNS_BIND_IP`, lab default `192.168.0.217`) — point LAN/DHCP DNS here |
| Dashboard | **NikTiar DNS Filter** tab — categories, custom domains, feed status |
| APIs | `GET/PUT /api/dns-filter`, `POST /api/dns-filter/resync`, `GET /api/dns-filter/catalog` |
| Open feeds | URLhaus, Phishing Army, OISD, StevenBlack multi (malware/phish/ads/adult/gambling/social) |
| Commercial hook | `NIKTIAR_DNS_COMMERCIAL_FEED_URL` + `NIKTIAR_DNS_COMMERCIAL_API_KEY` (JSON `{ "categories": { "malware": ["…"], … } }`); optional `NIKTIAR_DNS_COMMERCIAL_BLOCKLIST_URL` |
| WAF Host mirror | Enforced-category domains also denied on HTTP Host header (capped, default 5000) |
| Runtime dirs | `/runtime/dns-feeds/`, `/runtime/dns-filter/config.yml`, `policy.json` |

---

## Stack (engineering — not shown in product UI)

Runtime uses industry open-source components under NikTiar branding. Operator-facing UI and portals must use NikTiar names only.

Lab VM **116** `192.168.0.217`. **Not** part of mssp-appliance golden VM 199 — skip golden bake for Secure Edge-only changes.

---

## Smoke (lab)

- `GET /healthz` → 200
- SQLi query → 403 (NikTiar WAF)
- `/.env`, `/actuator/env`, headless UA → 403
- `TRACE` → 405; Page Shield headers present
- `/cdn-cgi/challenge-platform/pow` → 200 PoW interstitial
- Dashboard `/api/ngfw/catalog` returns URL categories + app profiles
- Dashboard `/api/dns-filter/catalog` returns DNS categories; `/api/dns-filter` shows feed status
- Dashboard `/api/enterprise` catalog = 12 advanced controls
- DNS: dig @192.168.0.217 a known-blocked domain → sinkhole `0.0.0.0` when category enforced

---

## Deployment model (dedicated only)

Shared multi-tenant edges are **not** offered. See **KB-115**.

| Control | Behavior |
|---|---|
| Offering | **Dedicated** per customer — HA pair (default) or physical 1U |
| Env | `SECURE_EDGE_MODE=dedicated` · `SECURE_EDGE_FORM_FACTOR=ha_pair\|physical` · `NIKTIAR_TENANT_CODE` |
| Unknown `Host` | **421** — no default origin fallthrough |
| Routing | Exact `Host` → that zone’s origin only (same customer’s sites) |
| Firewall / UA / custom rules | **Chained to zone Host** |
| Customer portal | Strict `tenant_short_code` on sites/events |
| Appliance dashboard | Deployment tab shows Dedicated · HA pair / Physical |

Dashboard top-left shows **Dedicated · HA pair** (or Physical) — never “shared”.
