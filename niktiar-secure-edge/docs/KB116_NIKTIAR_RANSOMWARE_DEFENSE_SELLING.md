# KB-116 — NikTiar™ Ransomware Defense (Secure Edge) — effectiveness & selling

**Status:** Shipped on Secure Edge lab (2026-10-26).

---

## How effective is it today?

| Layer | Strength | What it actually does |
|---|---|---|
| DNS ransomware category | **Strong for known infra** | Sinkholes clearweb leak sites / panels / related hosts from ransomwatch + NikTiar seed (+ optional ThreatFox / commercial feeds) |
| Generic malware/phishing DNS | **Strong** | Large open feeds (URLhaus, Phishing Army, OISD) — overlaps many ransomware *delivery* domains |
| WAF ransomware pack | **Strong for web-borne staging** | Blocks ransom-note paths, double-extension droppers, script/ISO under download paths, WebDAV write, Tor2web |
| URL Filter ransomware category | **Medium** | Path keyword patterns on HTTP |
| Endpoint encryption stop | **Not this product** | Secure Edge is not EDR — it does not stop ransomware already running on a laptop |

**Before this pack:** ransomware DNS category existed but had ~0 dedicated domains — weak to sell.  
**After this pack:** dedicated ransomware DNS population + WAF layers + UI with honest claims.

---

## Safe selling points (no SLA breach)

Use these in proposals and customer conversations:

1. Dedicated Secure Edge **reduces ransomware exposure** by sinkholing known ransomware infrastructure domains (DNS).
2. Blocks common **web dropper and ransom-note URL patterns** before they hit origin.
3. Blocks **WebDAV write / PROPFIND** abuse often used to plant payloads on misconfigured shares.
4. Works as **defense-in-depth** with NikTiar WAF, Bot Defense, Rate Limit, and DNS Filter.
5. Designed for **dedicated HA / physical** customer deployments — not a shared multi-tenant edge.

## Never promise (creates SLA / liability risk)

- “We prevent 100% of ransomware”
- “Zero ransomware incidents guaranteed”
- “Stops encryption of files on endpoints”
- Any **availability/uptime SLA tied to ransomware outcomes**

**Recommended contract language:**  
“NikTiar Secure Edge provides layered controls intended to reduce the likelihood of ransomware-related network delivery and command-and-control communication through the edge. It does not replace endpoint detection and response (EDR), backup, or identity controls, and does not warrant the absence of ransomware incidents.”

---

## Operator checklist

1. Enable **Ransomware Defense** (default on).
2. Keep DNS categories: malware, phishing, **ransomware**, cryptomining, custom.
3. Point LAN DNS at the dedicated edge when using DNS Filter.
4. Optional: set `NIKTIAR_THREATFOX_AUTH_KEY` and/or commercial feed env for denser intel.
5. Always pair sale with **endpoint EDR + immutable backups + IR runbook**.

Appliance UI: **Ransomware Defense** tab on `:9080`.
