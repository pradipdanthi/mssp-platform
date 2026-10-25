# NikTiar Secure Edge

Self-hosted Cloudflare-class edge (WAF + abuse) with **hybrid multi-tenant**.

**Stack:** Coraza CRS (`ghcr.io/coreruleset/coraza-crs:caddy-alpine`) + CrowdSec + NikTiar agent  
**Modes:** `shared` (SMB — many tenants by Host) · `dedicated` (enterprise — one tenant)  
**Lab:** Proxmox VM 116 / `192.168.0.217`  
**Commercial:** add-on on any Silver/Gold/Platinum tier  

See `docs/KB114_NIKTIAR_SECURE_EDGE.md`.
