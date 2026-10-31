# MSSP execution ledger (persistent)

Started: 2026-10-30T21:00Z · Baseline git `a2453bf` · Branch `kb112-sovereign-edge`  
**Release baseline (preserve):** `a3df314` (docs `7973f34` / `0248cd7` / `4f078f9+`) on `kb112-sovereign-edge`  
Latest deployed backend image: `sha256:ebee1adbdc3beb715f9423b30f8132efeaf1a6a41ee2786b6a5e52d9686ae2c6` (2026-10-31T06:35:17Z) — **unchanged this pass**  
EDR remediate ZIP sha256: `f9cf3eae0d67db6301cbcc5eb9c987003b185a19fbb3ecb6e410ff19ba9ffcb6`  
**Known-good golden snap (recoverable parent):** `kb-edr-key-202610311152` (VM 199)  
**Candidate golden snap (this pass):** `kb-firstboot-identity-202610310829` (git `4f078f9`, firstboot unit + `GOLDEN_TEMPLATE`)  
Acceptance clone: VM **219** `mssp-golden-clone-accept` (**stopped**) · appliance `b9a471a3-3744-4bbd-827a-15842ebde147` · site `golden-clone-accept-219` · tenant `ALPHAWINCORP-6VS2`

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
| Golden | Rollback VM 199 to snap `kb-edr-key-202610311152` if candidate `kb-firstboot-identity-202610310829` is rejected. Live customer appliances / fleet keys **untouched**. |

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

## Golden image — prerequisites vs acceptance

### Prerequisites (image / bake)

| Check | Status | Evidence |
|---|---|---|
| Firstboot mechanism in repo | IMPLEMENTED | `kevantic-appliance/scripts/kevantic-firstboot-identity.sh` + systemd unit; bake installs + `GOLDEN_TEMPLATE`; post-pass also rewrites netplan MAC on first boot (next bake) |
| Candidate bake preserving known-good | VERIFIED | Snap `kb-firstboot-identity-202610310829` child of `kb-edr-key-202610311152`; gold disk retains `GOLDEN_TEMPLATE`, script, enabled unit, `machine-id` still bake id until clone, `client.keys` empty, no embedded callback |
| Clone network | PREREQUISITE noted | Baked netplan pinned golden MAC `bc:24:11:59:e1:43`; clone NIC differed → no L3 until guestfish netplan MAC/IP `.235`. **Exact prerequisite for networked enroll of this candidate:** netplan `macaddress` must match guest NIC (manual guestfish this pass; firstboot MAC rewrite ships in tree for **next** bake). |

### Completed image / enrollment acceptance (clone 219)

| Check | Status | Evidence |
|---|---|---|
| Identity before enroll | VERIFIED | Firstboot on clone: `834826c3dce947ed900e60e42c2af5aa` ≠ gold `af934305…`; `GOLDEN_TEMPLATE` removed; `identity-initialized` set; `client.keys` 0 bytes |
| Fresh enroll → lab tenant/group | VERIFIED | `kevantic_cli register` → appliance `b9a471a3…`, tenant `ALPHAWINCORP-6VS2`; local Wazuh group `tenant_ALPHAWINCORP_6VS2` (`/var/lib/niktiar/wazuh_agent_group`); live `.226` BETA appliance untouched |
| Ordinary reboot preserves identities | VERIFIED | Post-reboot machine-id unchanged; group file still `tenant_ALPHAWINCORP_6VS2`; marker still gone |
| No privileged callback in image | VERIFIED | `NO_CALLBACK_ON_CLONE` under `/var/ossec` |
| Clone final state | — | VM **219 stopped**; CP row remains (lab acceptance appliance) |

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
