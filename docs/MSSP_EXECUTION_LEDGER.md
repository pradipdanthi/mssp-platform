# MSSP execution ledger (persistent)

Started: 2026-10-30T21:00Z · Baseline git `a2453bf` · Branch `kb112-sovereign-edge`  
**Release baseline (preserve):** `a3df314` (docs `7973f34` / `0248cd7` / `4f078f9+`) on `kb112-sovereign-edge`  
Latest deployed backend image: `sha256:ebee1adbdc3beb715f9423b30f8132efeaf1a6a41ee2786b6a5e52d9686ae2c6` (2026-10-31T06:35:17Z) — **unchanged this pass**  
EDR remediate ZIP sha256: `f9cf3eae0d67db6301cbcc5eb9c987003b185a19fbb3ecb6e410ff19ba9ffcb6`  
**Documented golden release tip:** `kb-firstboot-netplan-202610311451` (source **`6b18744`**) — unattended first-boot network **VERIFIED**.  
Prior tip `kb-firstboot-identity-202610310829` required manual guestfish MAC/IP (not unattended). Parents preserved through `kb-edr-key-202610311152` … `kb-firstboot-netplan-202610311430` / `…1445`.  
Acceptance clone **219** (**stopped**) · appliance `2c2048cc-38fd-4c5a-bfba-e032361ad88c` · `.236` · `ALPHAWINCORP-6VS2`.

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
| Golden | Tip `kb-firstboot-netplan-202610311451` (`6b18744`). Rollback to prior snaps if needed. No fleet key republish. |

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

## Golden image — release tip

| Snap | Source | Role |
|---|---|---|
| `kb-edr-key-202610311152` | `a2453bf` | Recoverable parent |
| `kb-firstboot-identity-202610310829` | `4f078f9` | Prior tip — **manual** MAC/IP only (not unattended) |
| `kb-firstboot-netplan-202610310909` | `c2ac85e` | Failed auto-provision (MAC only; IP stuck `.225`) |
| `kb-firstboot-netplan-202610311451` | **`6b18744`** | **Current tip** — cidata IP + `netplan apply` after networkd |

### Unattended packaging test (2026-10-31 ~20:25 IST) — PASSED

Clone 219 from tip, Proxmox `ipconfig0=192.168.0.236/24` only, **no guestfish**.

| Check | Result |
|---|---|
| Automatic network on first boot | **VERIFIED** — SSH `.236` at FOUND_AT=2; `addr_online=192.168.0.236`; `netplan_apply=ok` |
| Fresh machine / Wazuh identity | machine-id `32191b5a78b944f1875706e4e72d8203`; `client.keys` 0; marker gone |
| Enroll → lab tenant/group | appliance `2c2048cc…`; `tenant_ALPHAWINCORP_6VS2`; group created |
| Reboot preserves identity + network | MID/NET/GROUP preserved; marker still gone |
| No embedded callback secret | no `mssp-callback.key` under `/var/ossec` |
| Clone final | **stopped** |

## Adapter / TIA / ops separation (explicit)

| Area | Status |
|---|---|
| Broader TIA reasoning quality | Out of scope — not claimed |
| Physical voice / mic | BLOCKED (operator) |
| Paging / staffing / WhatsApp delivery | BLOCKED (provider + ops) |
| Autonomous closure activation | BLOCKED (`tia-closure-1` shadow) |
| **E6d Zeek security detection → SOC** | **VERIFIED** | Contract: rules `110110+` (level≥10) are SOC detections; `110101` CaptureLoss stays health (level 3, not ingress). Lab stimulus: Zeek **engine** `NOTICE(SSH::Password_Guessing)` → live `notice.log` → Wazuh agent 002 → rule **110110** alert `1793459427.7609981` → CP alert **`7a6a07ed-c59e-42ee-aef9-a3e2b4d2d081`** `source_tool=zeek` tenant **BETAWINCORP-J3FW** → `INC-BETAWINCORP-J3FW-TH-0002`. SOC analyst GET alert **200**. Dedup re-POST → `duplicate:true`, `ext_count=1`. ALPHA customer on BETA alert/incident → **404**. Label: engine notice stimulus (not packet-capture replay). CaptureLoss health rows in CP: **0**. |
| **E6e MISP analyst sync lifecycle** | **VERIFIED** | Components (226bcce, reused): (1) Zeek alert `7a6a07ed…` IOC `192.168.0.99` live **NO_MATCH**; (2) corpus `185.220.101.45` live **MATCH** attr `1` event `1` ts `1785607324` comment source-provided `APT29: C2 infrastructure` (not independently confirmed attribution; conf=0 / SUSPICIOUS schema — supporting intel, not auto-malicious); (3) analyst sync `POST /admin/threat-intel/…/sync` → `GET …/iocs` with MISP refs; customer admin sync **403**; (4) MOCKED `test_misp_enrichment_outcomes.py` match/no-match/unavailable. Client exact `casefold` filter. Health≠enrichment. **Bridge runtime patch undeployed** (ansible `misp_api.py` exact-match in repo; live VM 108 not redeployed; CP client filter covers). |
| **E6f MISP alert→TI hit (synthetic)** | **VERIFIED** | **SYNTHETIC** harness alert `55072cf0-4875-47f7-ab52-221c6c73d544` ext `SYNTH-MISP-ENRICH-1793460607` title labelled synthetic; `source_tool=suricata` tenant **BETAWINCORP-J3FW**; extracted `source_ip=185.220.101.45` → enrich/`POST …/ai-triage` **threat_intel.hit=true** match_count=1 summary source-provided `APT29: C2 infrastructure` → analyst TI IOC attr `1` event `1` ts `1785607324`. Zeek `7a6a07ed…` untouched. No MISP record writes; indicator not contacted; no remediation. Status restored to `new` after triage side-effect. |
| **MISP enrichment workflow (complete)** | **VERIFIED** | E6e lifecycle + E6f positive alert path. |
| Zeek hunts / enrichment / deeper NDR product depth | PARTIAL | Backlog — not claimed this pass |

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
- 2026-10-31 ~14:45 IST: Packaging bake `kb-firstboot-netplan-202610310909` (`c2ac85e`); unattended clone network **FAILED** (IP pinned `.225`).
- 2026-10-31 ~20:25 IST: Tip promoted to `kb-firstboot-netplan-202610311451` (`6b18744`); unattended `.236` + enroll + reboot **PASSED**; clone 219 stopped; fleet keys unchanged.
- 2026-10-31 ~20:45 IST: E6d Zeek detection path VERIFIED (`7a6a07ed…` / `INC-BETAWINCORP-J3FW-TH-0002`); no code deploy; golden tip unchanged.
- 2026-10-31 ~21:00 IST: E6e MISP analyst sync lifecycle VERIFIED (live no-match; corpus match + analyst sync/API; client exact-match fix; CP deploy). Golden/Zeek untouched. Bridge runtime undeployed.
- 2026-10-31 ~21:10 IST: E6f synthetic alert→TI hit VERIFIED (`55072cf0…` / `185.220.101.45` / MISP attr1 event1); MISP enrichment workflow complete; no CP code change; Zeek untouched.
