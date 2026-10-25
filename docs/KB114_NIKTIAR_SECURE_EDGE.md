# KB-114 — NikTiar Secure Edge (Cloudflare-parity appliance)

**Status:** Configurable lab appliance with CF-style security controls (2026-10-25).

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

Configure everything in the appliance dashboard → **Apply changes**. Settings live in `/runtime/edge_config.json` and compile into Coraza `rules.d` + Caddy snippets.

---

## Stack

Coraza CRS Caddy · CrowdSec + firewall bouncer · hybrid multi-tenant agent · dashboard `:9080`

Lab VM **116** `192.168.0.217`.
