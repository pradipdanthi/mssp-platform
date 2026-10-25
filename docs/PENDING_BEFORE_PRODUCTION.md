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
| Zeek → Wazuh SOC rules | Rules **110100–110112** (MSSP band) live on Manager 101; notice.log localfile; Zeek site policy; IP attribution for Zeek `src`/`dst` |
| soc_notifier MAX_ATTEMPTS | Wired to `attempts` column + `SOC_NOTIFIER_MAX_ATTEMPTS` |
| Ingress token leak on ConnectionError | Logs redacted; token rotated again; integration hardened |
| Website Silver tier-card contrast | Dark-on-dark title fixed; published `styles.css?v=13` + inline Silver colors on index/services |

## Held / deferred (user decision)

| Item | Status |
|------|--------|
| rclone own Google `client_id` | **HOLD** until user decides. Drive still works on shared client (retirement warn 2026). Script ready: `scripts/dr_apply_rclone_own_client.sh` + `.secrets/rclone_google_oauth.env`. |
| ITDR one-click Entra contain (trial M365) | **Code shipped** (KB-113). Live Graph secrets + disposable-user test **deferred** until owner returns. |
| NikTiar Secure Edge (CF alternative) | **Lab complete** — VM 116 dashboard `:9080`, Coraza+CrowdSec+bouncer, hybrid multi-tenant, Admin/Customer portal pages (`bab682f`). Public ACME DNS + password rotate for prod. Distinct from Edge Node. |

## Parked (product hold — do not start until asked)

WhatsApp/Telegram enable, voice, Cursor agents, SDLC handbook pack.

## Go-live blocker list

Empty after today’s clears + rclone hold. Platform verify: **PASSED 141 / FAILED 0 / CLOUD-READY YES** (Zeek rule IDs renumbered into 110000–119999).
