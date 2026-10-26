# KB-117 — NikTiar Secure Edge vs industry NGFW (Palo Alto–style) map

**Purpose:** Show how we matched **reputable NGFW ransomware / firewall practice** without claiming we are Palo Alto PAN-OS, WildFire, or Cortex.

---

## What leading NGFWs do for ransomware (public best practice)

| Industry control | Typical product name (examples) | Intent |
|---|---|---|
| File Blocking | File Blocking / AV profile | Stop PE, scripts, ISO, macros used as loaders |
| Anti-Spyware + DNS sinkhole | Anti-Spyware, DNS Security | Block C2 / malicious DNS |
| URL Filtering | PAN-DB / URL categories | Block malware, phishing, proxy, DDNS, parked |
| Vulnerability Protection | IPS / Threat Prevention | Block exploits (SQLi, RCE paths) |
| External Dynamic Lists | EDL | Operator + intel IOC lists |
| Cloud sandbox | WildFire-class | Detonate unknown files |
| Endpoint EDR | Cortex XDR-class | Stop encryption on the host |

Sources (public docs / best-practice articles): Palo Alto ransomware prevention KBs, NGFW subscription docs (Threat Prevention, DNS Security, URL Filtering, WildFire), industry “test your NGFW for ransomware” checklists.

---

## What NikTiar Secure Edge implements

| Industry control | NikTiar implementation | Status |
|---|---|---|
| File Blocking | **Security Profiles → File Blocking** (extensions, MZ upload, download-path PE) | Shipped |
| Anti-Spyware / DNS | **DNS Filter** categories + **Anti-Spyware** DGA / tunnel Host + C2 paths | Shipped |
| URL Filtering | **NikTiar URL Filter** + categories (malware, phishing, ransomware, proxy, DDNS, parked) | Shipped |
| Vulnerability Protection | **NikTiar WAF** + Virtual Patching + Security Level | Shipped |
| EDL | `/runtime/edl/{domains,ips,urls}.txt` compiled into WAF | Shipped |
| Ransomware pack | **Ransomware Defense** + **Strict Ransomware** preset | Shipped |
| Cloud sandbox | Optional `NIKTIAR_SANDBOX_WEBHOOK_URL` hook | Optional / commercial |
| Endpoint EDR | **Out of scope** for Secure Edge — sell with endpoint product | Partner / separate |

---

## Honest gaps (do not oversell)

1. **No full SSL outbound decryption** without customer enterprise PKI (MITM) — same constraint every reverse-proxy edge has unless explicitly designed as a decrypting forward proxy.
2. **No WildFire-equivalent sandbox** unless you wire a commercial analysis API.
3. **No Cortex-equivalent endpoint ransomware rollback** — Secure Edge is network/web edge.
4. We use an **open + curated intel** model; commercial feeds make DNS denser (ThreatFox key / commercial URL).

---

## Operator: enable the Palo-style pack

1. Open appliance → **Security Profiles**
2. Click **Apply Strict Ransomware**
3. Keep **Ransomware Defense** enabled
4. Point LAN DNS at the dedicated edge for DNS sinkhole
5. Pair sale with **EDR + immutable backups**

APIs: `GET/PUT /api/security-profiles`, `POST /api/security-profiles/preset/strict_ransomware`
