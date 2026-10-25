# KB-114 — NikTiar Secure Edge (Cloudflare-parity appliance)

**Status:** v3.0 enterprise pack live on lab (2026-10-25) — CF Advantage-class controls on-appliance.

---

## Access

| Surface | URL |
|---|---|
| **Appliance dashboard (configure WAF here)** | **http://192.168.0.217:9080/** |
| WAF / traffic | http://192.168.0.217/ |
| Admin portal | http://192.168.0.201:3000/secure-edge |
| Customer portal | http://192.168.0.201:3001/secure-edge |

Dashboard login: `admin` / `EDGE_DASHBOARD_PASSWORD` (default `NikTiarEdge!ChangeMe`).

---

## Cloudflare → NikTiar mapping

| Cloudflare concept | NikTiar Secure Edge |
|---|---|
| Zone | **Zone / Site** (hostname → origin) |
| Security Level | **Off / Essentially Off / Low / Medium / High / I'm Under Attack!** |
| Managed Rules (OWASP) | **Coraza + OWASP CRS** (paranoia + anomaly) |
| Custom Rules | **Custom WAF rules** (`path/ua/ip/query` expressions) |
| IP Access Rules | **Firewall** IP allow/block + UA block |
| Bot Fight Mode | **Bot Fight Mode** toggle |
| Browser Integrity Check | **BIC** toggle |
| Under Attack Mode | **UAM** challenge page (`/cdn-cgi/challenge-platform`) |
| Rate limiting | **Rate limit rules** per path |
| SSL/TLS mode | **off / flexible / full / strict** |
| Caching | **Bypass / Standard** (+ edge TTL) |
| Analytics | **Analytics** tab (requests / blocks) |
| API Shield | **Enterprise → API Shield** (JSON on `/api`, TRACE block, body caps) |
| GraphQL protection | **Enterprise → GraphQL Guard** (batch / depth / alias) |
| Page Shield | **Enterprise → Page Shield** (CSP + Referrer + Permissions-Policy) |
| Waiting Room | **Enterprise → Waiting Room** (`/cdn-cgi/waiting-room/pass`) |
| Bot Management / PoW | **Enterprise → Advanced Bot** + `/cdn-cgi/challenge-platform/pow` |
| Virtual patches / CVE paths | **Enterprise → Virtual Patching** (`.env`, actuators, WP, phpMyAdmin) |
| Auth / credential stuffing | **Enterprise → Auth Hardening** + zone rate limits |
| DLP / sensitive data | **Enterprise → Sensitive Data Detection** (PAN/SSN response scan) |
| Leaked credentials | **HIBP k-anonymity** via `/api/enterprise/hibp-check` |
| Logpush | **Enterprise → Logpush** webhook |
| mTLS | **Enterprise → mTLS stub** (enable + wire CA on dedicated edges) |
| Deception | **Enterprise → Honeypot paths** |

Configure in the appliance dashboard (**Enterprise** tab + classic WAF tabs) → **Apply changes**. Settings live in `/runtime/edge_config.json` and compile into Coraza `rules.d` (`11040-enterprise.conf`) + `/runtime/enterprise.caddy`.

---

## Stack

Coraza CRS Caddy · CrowdSec + firewall bouncer · hybrid multi-tenant agent · dashboard `:9080` (v3 enterprise pack)

Lab VM **116** `192.168.0.217`. **Not** part of mssp-appliance golden VM 199 — skip golden bake for Secure Edge-only changes.

---

## Smoke (lab)

- `GET /healthz` → 200
- SQLi query → 403 (CRS)
- `/.env`, `/actuator/env`, headless UA → 403
- `TRACE` → 405; Page Shield CSP headers present
- `/cdn-cgi/challenge-platform/pow` → 200 PoW interstitial
- Dashboard `/api/enterprise` catalog = 12 controls
