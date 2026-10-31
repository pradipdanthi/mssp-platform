# MSSP execution ledger (persistent)

Started: 2026-10-30T21:00Z · Baseline git `a2453bf` · Branch `kb112-sovereign-edge`  
**Release baseline (preserve):** `a3df314` (docs `7973f34` / `0248cd7` / `4f078f9+`) on `kb112-sovereign-edge`  
Latest deployed backend image: `sha256:ebee1adbdc3beb715f9423b30f8132efeaf1a6a41ee2786b6a5e52d9686ae2c6` (2026-10-31T06:35:17Z) — **unchanged this pass**  
EDR remediate ZIP sha256: `f9cf3eae0d67db6301cbcc5eb9c987003b185a19fbb3ecb6e410ff19ba9ffcb6`  
**Documented golden release tip (unchanged — unattended provisioning not proven):** `kb-firstboot-identity-202610310829` (git `4f078f9`). That tip **required manual guestfish MAC/IP** on clone `.235` and does **not** prove unattended provisioning.  
**Recoverable parents preserved:** `kb-edr-key-202610311152` → `kb-firstboot-identity-202610310829` → `kb-firstboot-netplan-202610310909` (VM 199 `current` points at latest disk; **tip not promoted**).  
**Held candidate (FAILED auto-provision):** `kb-firstboot-netplan-202610310909` source revision **`c2ac85e`**. Clone **219** (**stopped**).

Evidence classes: **code** · **deployed-runtime** · **simulated** · **real-source**

States: `NOT STARTED` | `IN PROGRESS` | `IMPLEMENTED` | `DEPLOYED` | `VERIFIED` | `FAILED` | `BLOCKED` | `DEFERRED` | `N/A`

## Safe rollback (a3df314+)

**Do not** restore `mssp-callback.key.bak.pre-edr-canary` or any SOC-sync-length callback key onto managers/endpoints.

| Layer | Procedure |
|---|---|
| App image | Tag/redeploy `mssp-control-backend-api:pre-tia-tls-workers-20261030T200932Z` (`sha256:ef21b00aa8d3…`) **only with current** `/run/secrets/edr_callback_api_key`, Wazuh CA, and `WAZUH_API_VERIFY_TLS=true`. |
| Migration 125 | **Keep** on DB if present. |
| EDR callbacks | Fail closed if dedicated key missing. Republish via `scripts/publish_edr_ar_fleet.sh` only when intentional — **not** this pass. |
| Ingress | Rotate forward only; never restore retired tokens. |
| Golden | Tip remains `kb-firstboot-identity-202610310829` until unattended provision PASSes. Held fail candidate `kb-firstboot-netplan-202610310909`. Rollback parents intact. No fleet key republish. |

## Closed evidence (do not re-open)

Recovery, rollback, restore→app, ingress token hygiene, portals/RBAC, EDR key-publication, Linux/Suricata/Windows lifecycle — remain **VERIFIED** as of `4f078f9` / prior ledger rows. Not retested this pass.

## Requirements — Gate 1 security (delta)

| ID | Requirement | Status | Evidence class | Evidence |
|---|---|---|---|---|
| E15 | Inference sandbox / tool rights | VERIFIED | code + deployed-runtime | **Runtime boundaries (not model refusal):** `cli_exec` sandbox suite 18 OK; SOC agent `secadmin` + TLS ExecStart; Ollama disabled on agent. Investigation dossier: redacted form withholds raw events/names/addresses; research `no_grant` refuses + records. TLS alone = E5. |
| E12b | Malicious instructions in alert evidence | VERIFIED | code (isolated) | **Investigation/model path (not converse routing):** `ConversationFlowTests.test_instructions_inside_alert_text_are_data_not_commands` — inject text is data; pending open_case targets real alert id not embedded UUID; no ui_command from inject. `RefusalTests.test_text_in_the_alert_cannot_authorise_its_own_closure` — playbook refuses; alert stays `new`. `ShadowModeTests.test_prompt_injection_in_the_note_does_not_authorize` — `partition_proposed_actions` holds write; `tenant_id` from model stripped; reason `shadow_mode`. Dossier redaction + research no-grant as above. Logs: `/tmp/e15_investigation_path.log`, `/tmp/e15_investigation_path2.log`. Prior typed canary (`classify other`) = **routing only** — not counted as isolation. |

## Requirements — Gate 2 (Windows wording)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| E6c | Windows collection→routing | VERIFIED | **Adjusted-payload transport/lifecycle proof:** live agent **006** archive sample POSTed via ingress with `rule.level=10` + acceptance groups (transport adjustment only — **no** manager/local_rules change). Alert `22da2daa…` → `INC-ALPHAWINCORP-6VS2-TH-0005` closed. |
| E6c-cfg | 92032 / 92205 honesty | VERIFIED | 92032 L10 = acceptance payload only. `__PSScriptPolicyTest_` → `create_incident=False` → alert `false_positive` (`82434ed2…`); does not close existing incidents; non-noise paths not suppressed (matrix). |

## Requirements — Gate 4 ops (E22 ambiguity)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| E22 | Offboarding / revocation | VERIFIED | **Token issued before deactivation:** disposable `e93ef4b0-1d21-4513-bdfc-375b23ffef1d` (`e22.pretok.a933d508@lab.local`): login→token→me **200** → PATCH `inactive` → **same pre-issued token** me/dashboard **403**; re-login **403**. Owner me **200**. Prior drill `525a3080…` same pattern. **Refresh/renewal:** no `/auth/refresh` (OpenAPI auth paths: login, me, change-password, MFA only) — renewal = new login, which respects `status≠active` via `get_current_user` (403). Users left inactive. |

## Golden image — tip vs held candidate

| Snap | Source | Role |
|---|---|---|
| `kb-edr-key-202610311152` | `a2453bf` | Recoverable parent |
| `kb-firstboot-identity-202610310829` | `4f078f9` | **Documented tip** — enroll proven only after **manual** MAC/IP guestfish; not unattended |
| `kb-firstboot-netplan-202610310909` | `c2ac85e` | **Held** — one bake + one clone; auto-provision **FAILED** |

### Unattended packaging test (2026-10-31 ~14:45 IST) — FAILED

Clone 219 from `kb-firstboot-netplan-202610310909`, Proxmox `ipconfig0=192.168.0.236/24` only, **no guestfish**.

| Check | Result |
|---|---|
| Automatic working network on first boot | **FAILED** — no SSH/ping on `.236` (~4 min) |
| Firstboot MAC rewrite | Ran: `netplan_mac_updated … mac=bc:24:11:79:ac:6b` (matches NIC) |
| Defect | Baked netplan **address stayed `192.168.0.225/24`** (golden IP); cloud-init `ipconfig0` `.236` not applied to on-disk netplan. Firstboot rewrites MAC only — does not sync address or `netplan apply` into a usable L3 config for the clone. |
| Machine id after firstboot | `8c1d5d4a36a94bc6b86634a57c0ebb74` (log); marker gone |
| Enroll / reboot preserve | **Not run** (provisioning held) |
| Clone final | **stopped**; evidence in firstboot log + netplan on disk |

**Provisioning held.** Tip not promoted. No further bake/repair this task.

## Adapter / TIA / ops separation (explicit)

| Area | Status |
|---|---|
| Broader TIA reasoning quality | Out of scope — not claimed |
| Physical voice / mic | BLOCKED (operator) |
| Paging / staffing / WhatsApp delivery | BLOCKED (provider + ops) |
| Autonomous closure activation | BLOCKED (`tia-closure-1` shadow) |
| Zeek CP SOC rows / hunts / enrichment / deeper vuln scans | Adapter backlog PARTIAL — not this pass |

## Bounded pass journal (2026-10-31 ~14:20 IST)

| Item | Result |
|---|---|
| E22 token-before + refresh | Documented + reconfirmed; refresh N/A (unsupported) |
| E15/E12b investigation path | Existing unit tests executed OK; boundaries listed |
| Golden candidate bake | `kb-firstboot-identity-202610310829`; known-good parent preserved |
| Clone enroll + reboot | VERIFIED; stopped |
| Deploy | Skipped — no control-plane runtime change |
| Fleet keys | Not republished |

## Journal (earlier)

- 2026-10-31 PM: Safe rollback; restore→app; Windows/Suricata lifecycle; Zeek manager processing; stability 88 turns; E20 lease jobs; E22 first drill; offline identity prototype on prior 219.
- 2026-10-31 ~13:15 IST: `4f078f9` bounded gap pass (E20/E15 honesty/firstboot code/E22/Windows cfg).
- 2026-10-31 ~14:20 IST: Ambiguity close + golden candidate bake/enroll acceptance; ledger split prerequisites vs enrollment.
- 2026-10-31 ~14:45 IST: Packaging bake `kb-firstboot-netplan-202610310909` (`c2ac85e`); unattended clone network **FAILED** (IP pinned `.225`); tip remains `kb-firstboot-identity-202610310829`; 219 stopped.
