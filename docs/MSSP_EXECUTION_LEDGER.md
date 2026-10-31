# MSSP execution ledger (persistent)

Started: 2026-10-30T21:00Z · Baseline git `a2453bf` · Branch `kb112-sovereign-edge`  
Latest deployed backend image: `sha256:ebee1adbdc3beb715f9423b30f8132efeaf1a6a41ee2786b6a5e52d9686ae2c6` (2026-10-31T06:35:17Z)  
Golden snapshot: `kb-edr-key-202610311152` (VM 199)

States: `NOT STARTED` | `IN PROGRESS` | `IMPLEMENTED` | `DEPLOYED` | `VERIFIED` | `FAILED` | `BLOCKED` | `N/A`

## Checkpoint

| Item | Value |
|---|---|
| Portals | Admin/Customer/SOC authenticated workflows verified (not homepage-only) |
| Alert corpus reconcile | Backup 2026-10-30_143106Z → **524** alerts / **313** incidents. Live empty board caused by intentional `./scripts/purge_lab_alerts_incidents.sh` in prior SOC session ([SOC purge chat](0f0fa4e2-99b0-40ad-9a25-f67b58f3e41e)). Same DB identity; not silent corruption. |
| EDR key | Dedicated key published to central (8 groups) + appliance (2); canary + fleet VERIFIED; golden baked |
| Rollback | Backend prior `f804c4e0…` / images; Wazuh `ossec.conf.bak.gate1-*`; EDR `mssp-callback.key.bak.pre-edr-canary` on ALPHA; do **not** reverse migration 125 blindly |

## Requirements

| ID | Finding | Pri | Status | Evidence |
|---|---|---|---|---|
| E1 | APP_ENV=development | P0 | VERIFIED | production |
| E2 | Wazuh TLS verify | P0 | VERIFIED | pin + authenticate OK |
| E3 | EDR callback shared key | P0 | VERIFIED | dedicated key; sync/invalid 401; wrong agent 404; good 200→verified; fleet+appliance+golden |
| E4 | Sample seed | P0 | VERIFIED | fail-closed production |
| E5 | Agent HTTPS | P0 | VERIFIED | prior + active |
| E6a | Linux source→incident | P0 | VERIFIED | agent 001 `linux-endpoint-lab` logger → appliance rule 100901 → CP `c76efe84…` / `INC-BETAWINCORP-J3FW-APP-0001` → assign/comment/**closed** authorized_benign lab |
| E6b | Network Suricata→incident | P0 | VERIFIED | live eve `GPL ATTACK_RESPONSE id check returned root` → Wazuh 100611 → CP `4987505d…` source_tool=suricata BETA; mirror tap105→106 active |
| E6c | Windows agent SSH | P0 | BLOCKED | 192.168.0.214 SSH denied; agent 006 still active on central for ingress tests |
| E7 | Notifications | P0 | VERIFIED (local) | file sink sent; webhook retries→failed@4; WhatsApp blocked (missing token/phone); **ack was harness `acknowledge()`, not a person** |
| E8 | Isolated restore | P0 | VERIFIED | decrypt+extract ~4s; DB restore path ~6s total; 3 tenants / 7 users / 524 alerts / 313 incidents; tenant counts; hashes present; no workers bound; live untouched |
| E9 | Ownership visibility | P1 | VERIFIED | ownership_state/age_hours |
| E10 | Ops scope draft | P1 | IMPLEMENTED | docs/MSSP_OPS_SCOPE_DRAFT.md |
| E11 | Indexer :9200 | P1 | N/A | not opened |
| E12 | TIA typed | P2 | VERIFIED | greetings; goodbye; Suricata+Zeek status; Shuffel; Bro; customers jobs_delta=0; criticality; mic **UNVERIFIED** |
| E13 | Autonomous closure | P2 | BLOCKED | policy |
| E14 | Physical mic | P2 | BLOCKED | operator |
| E15 | Inference sandbox | P1 | VERIFIED (code) | cli_exec sandbox |
| E16 | Ingress token logs | P0 | VERIFIED | redacted (markers present; plaintext absent); current token accepted on `/integrations/soc/hooks/wazuh/{token}` (422 unbound probe agent — auth OK); retired full-backup token 404; garbage 404; no pending rotate/reload task |
| E17 | Appliance ingress gap | P0 | VERIFIED | installed custom-mssp-ingress on 226; Linux path depends on it |

## Journal

- 2026-10-31: EDR canary ALPHA → full central+appliance publish → golden `kb-edr-key-202610311152`.
- Appliance lacked control-plane ingress; installed; Linux BETA real detection closed as lab acceptance.
- Suricata live mirrored detection landed as high BETA alert.
- Alert wipe cause: `purge_lab_alerts_incidents.sh` in prior session (not unexplained loss).
- TIA goodbye + multi-engine health regex fixes deployed.
