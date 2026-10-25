# Pending before production

**Last updated:** 2026-10-25 (all actionable items cleared except Google OAuth interactive)

YouTube VM103 is unrelated / stopped — out of scope.

## Cleared today

| Item | Result |
|------|--------|
| Alert ingest re-prove | Suricata + Zeek high alerts into BETAWINCORP |
| `.env.bak` secrets file | Deleted |
| Website Okta → Entra/M365 | Published to kevantic.com (Okta_count=0); local commit `d9ba0f4` |
| Catalog tier bundle pricing | Admin/DB aligned (`cbcaa80`) |
| Zeek → Wazuh SOC rules | Rules 100700–100712 live; notice.log localfile; Zeek site policy; IP attribution for Zeek `src`/`dst` |
| soc_notifier MAX_ATTEMPTS | Wired to `attempts` column + `SOC_NOTIFIER_MAX_ATTEMPTS` |
| Ingress token leak on ConnectionError | Logs redacted; token rotated again; integration hardened |

## Remaining (cannot finish without Google interactive login)

| Item | Status |
|------|--------|
| rclone own Google `client_id` | Drive still works on shared client (warns retirement 2026). Apply script ready: `scripts/dr_apply_rclone_own_client.sh` + `.secrets/rclone_google_oauth.env`. Google Cloud Console sign-in is required to *create* the OAuth client — no stored GCP session on this host. |

## Parked (product hold)

WhatsApp/Telegram enable, voice, Cursor agents, SDLC handbook pack.
