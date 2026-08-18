# Kevantic marketing website

Fortune-500-style static site for **kevantic.com** (Hostinger `public_html`).
Operated by **Kevantic Cyber Security Private Limited**. No public Admin/SOC links.

## Preview (lab — permanent until Hostinger cutover)

The lab site runs as a Docker nginx container on **port 8080** (`restart: unless-stopped`, survives reboot).

```bash
# Start / recreate
/opt/mssp-control/website-junexis/lab-serve.sh

# Status
docker ps --filter name=junexis-website-lab
```

Open **http://192.168.0.201:8080/** (or http://127.0.0.1:8080/).

`js/site-config.js` points Customer Login at the lab portal `http://192.168.0.201:3001` while in lab. Change back to `https://portal.kevantic.com` before Hostinger publish.

Optional systemd unit file is also present (`junexis-website-lab.service`) if you prefer host nginx/python later.

## Upload to Hostinger

Upload the entire folder contents into `public_html`. Enable SSL. Create `sales@kevantic.com`.
Set customer portal URL in `js/site-config.js` (`portal.kevantic.com`).

## Structure

| Path | Role |
|------|------|
| `index.html` | Full homepage wireframe |
| `services.html` | 10-service portfolio |
| `platform.html` | Customer portal showcase |
| `solutions.html` | Audience solutions |
| `about.html` | Brand + company story |
| `contact.html` | Demo form |
| `privacy.html` / `terms.html` | Placeholders |
| `css/styles.css` | Design system |
| `js/site-config.js` | Portal URL |
| `js/app.js` | Nav, deploy sim, form, reveal |
| `assets/mark.svg` / `logo.svg` | Brand marks |

## Catalog accuracy

- **Core (2):** Log & Event Monitoring · Incident Response & Casework
- **Add-ons (8):** Automation · VMaaS · CaaS · NDR · Threat Intel · Forensics · EASM · ITDR
- Public pages use the **Kevantic NikTiar™** engine suite only (Core Telemetry, DeepSight NDR, Aegis Scanning, Apex Orchestrator, Spectre Forensics, Edge Node). No Wazuh / Suricata / Zeek / MISP / TheHive / Velociraptor names.
