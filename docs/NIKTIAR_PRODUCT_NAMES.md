# NikTiar product names (no upstream brands in the product)

**Rule:** Customer portals, Admin/SOC UI copy, Secure Edge appliance UI, and marketing never
show open-source or third-party engine names. Internal code, Docker images, Ansible, and
operator engineering docs may still use real package names where required to build/run.

| Capability (what users see) | Never say in product UI |
|---|---|
| **NikTiar™ Core Telemetry** | Wazuh, Fluent Bit |
| **NikTiar™ DeepSight NDR** | Suricata, Zeek |
| **NikTiar™ Aegis Scanning** | Nuclei, Vuls, Greenbone, OpenVAS |
| **NikTiar™ Apex Orchestrator** | TheHive, Shuffle |
| **NikTiar™ Threat Intelligence** | MISP |
| **NikTiar™ Spectre Forensics** | Velociraptor |
| **NikTiar™ Secure Edge** | Cloudflare (as product) |
| **NikTiar™ WAF** | Coraza, OWASP CRS, ModSecurity |
| **NikTiar™ Firewall** / **NikTiar™ NGFW** | generic “iptables-only” framing; show as NikTiar Firewall |
| **NikTiar™ Bot Defense** | CrowdSec |
| **NikTiar™ Edge Engine** | Caddy (as product name) |
| **NikTiar™ Identity Protection** | Okta / Entra raw product dump in customer views |

## Secure Edge console labels

| UI label | Meaning |
|---|---|
| NikTiar WAF | Managed web application firewall rules |
| NikTiar Firewall | IP / geo / UA access rules |
| NikTiar NGFW Policies | Ordered allow/deny/challenge policies |
| NikTiar URL Filter | Category + custom URL path filtering |
| NikTiar DNS Filter | Category feeds + domain blocklists (DNS + optional WAF Host) |
| NikTiar Ransomware Defense | DNS ransomware category + WAF dropper/note/WebDAV layers |
| NikTiar Security Profiles | NGFW-style File Blocking, Anti-Spyware, URL Filtering, EDL |
| NikTiar Rate Limit | Per-path request throttling |
| NikTiar Bot Defense | Scanner/bot/abuse decisions |
| NikTiar Zones | Protected hostnames (sites) on a dedicated edge |
| Dedicated HA pair | Default Secure Edge form factor (virtual active pair) |
| Physical Secure Edge | Same stack on 1U hardware at customer site |

Secure Edge is **dedicated per customer** only — no shared multi-tenant edge offering.

Code map: `backend-api/app/services/customer_safe_labels.py`.
Verifier: `scripts/verify_platform_state.py` CHECK 6 (`FORBIDDEN_UI_ENGINE_NAMES`).
