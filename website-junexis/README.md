# Junexis marketing website

Fortune-500-style static site for **junexis.com** (Hostinger `public_html`).
Operated by **Cicilia Consultancy**. No Keroxsys / Kestrel. No public Admin/SOC links.

## Preview

```bash
cd /opt/mssp-control/website-junexis
python3 -m http.server 8080
```

Open http://127.0.0.1:8080/

## Upload to Hostinger

Upload the entire folder contents into `public_html`. Enable SSL. Create `sales@junexis.com`.
Set customer portal URL in `js/site-config.js` (`portal.junexis.com`).

## Structure

| Path | Role |
|------|------|
| `index.html` | Full homepage wireframe |
| `services.html` | 10-service portfolio |
| `platform.html` | Customer portal showcase |
| `solutions.html` | Audience solutions |
| `about.html` | Brand + Cicilia |
| `contact.html` | Demo form |
| `privacy.html` / `terms.html` | Placeholders |
| `css/styles.css` | Design system |
| `js/site-config.js` | Portal URL |
| `js/app.js` | Nav, deploy sim, form, reveal |
| `assets/mark.svg` / `logo.svg` | Brand marks |

## Catalog accuracy

- **Core (2):** Log & Event Monitoring · Incident Response & Casework
- **Add-ons (8):** Automation · VMaaS · CaaS · NDR · Threat Intel · Forensics · EASM · ITDR
- Public pages use capability labels only (no Suricata/Wazuh/Velociraptor brand names)
