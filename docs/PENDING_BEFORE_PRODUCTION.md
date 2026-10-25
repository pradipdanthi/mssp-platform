# Pending before production

**Last updated:** 2026-10-25  
**Owner:** solo founder  
**Rule:** Cursor must remind these at the start of every new work request until cleared.

YouTube / yt-ai-media VM103 is **unrelated** to MSSP, stopped, and must not appear in capacity planning.

---

## Priority order (owner-picked)

| Pri | Item | Status |
|-----|------|--------|
| P0 | Re-prove alert ingest | **DONE** 2026-10-25 14:14 — Suricata high → BETAWINCORP |
| P0 | Delete `/home/secadmin/.env.bak.20261015` | **DONE** |
| P1 | Website Okta overclaim → Entra/M365 | **Local fixed**; commit + publish to kevantic.com still needed |
| P2 | Admin catalog copy: tiers are bundles (not à-la-carte SKUs) | Next |
| P3 | Zeek → Wazuh notice rules (SOC paging) | Open — needs default rule pack |
| P4 | rclone own Google client_id | Needs your Google Cloud console |
| P5 | `soc_notifier` MAX_ATTEMPTS | Only when WhatsApp/Telegram unparked |
| — | Host RAM headroom | Monitor only (~7 GB free today); zram safety net |

## Parked

- WhatsApp / Telegram + deep-triage / notifier enable  
- Voice escalation  
- 5 Cursor agents  
- SDLC handoff pack (P1 handbook + P2 process + P3 ADRs) — later  
- Retro-hunt demo (needs Platinum tenant)

## Healthy snapshot

- CLOUD-READY YES; appliance online; NDR mirror OK; Zeek logging; DR through 2026-10-18  
- Golden: `engine-rundir-hbtimer-202610150613`
