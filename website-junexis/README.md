# Kevantic marketing website

Fortune-500-style static site for **kevantic.com** (Hostinger `public_html`).
Operated by **Kevantic Cyber Security Private Limited**. No public Admin/SOC links.

## Preview (lab)

The lab site runs as a Docker nginx container (`restart: unless-stopped`, survives reboot).

```bash
# Start / recreate
/opt/mssp-control/website-junexis/lab-serve.sh

# Status
docker ps --filter name=junexis-website-lab
```

Open the lab preview on this host via loopback (`http://127.0.0.1` plus the lab nginx listen port). Do not publish lab host addresses in public HTML.

`js/site-config.js` in this lab tree may point Customer Login at the private control-plane consoles for VM preview only. Production / Hostinger builds must use the coming-soon `portal.html` path (see the Hostinger source tree). Never ship lab host addresses in public copy.

Optional systemd unit file is also present (`junexis-website-lab.service`) if you prefer host nginx later.

## Upload to Hostinger

Upload the entire folder contents into `public_html`. Enable SSL. Create `sales@kevantic.com`.
Set customer portal URL in `js/site-config.js` (`portal.kevantic.com` or `/portal.html` until login is public).

## Structure

| Path | Role |
|------|------|
| `index.html` | Full homepage |
| `services.html` | Service portfolio |
| `platform.html` | Control plane / client portal showcase |
| `solutions.html` | Audience solutions |
| `about.html` | Brand + company story |
| `contact.html` | Demo form |
| `privacy.html` / `terms.html` | Placeholders |
| `css/styles.css` | Design system |
| `js/site-config.js` | Portal URL |
| `js/app.js` | Nav, deploy sim, form, reveal |
| `assets/brand/` | Logos, favicons, OG image |

## Catalog accuracy

- **Core (2):** Log & Event Monitoring · Incident Response & Casework
- **Add-ons (8):** Automation · VMaaS · CaaS · NDR · Threat Intel · Forensics · EASM · ITDR
- Public pages use the **Kevantic NikTiar™** engine suite only (NikTiar™ Core, NikTiar™ DeepSight NDR, NikTiar™ Aegis, NikTiar™ Apex Orchestrator, NikTiar™ Spectre DFIR, Edge Node). No Wazuh / Suricata / Zeek / MISP / TheHive / Velociraptor names.
