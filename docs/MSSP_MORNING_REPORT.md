# Continuity handover — after 4f078f9 ambiguity + golden candidate

Updated: 2026-10-31 ~14:25 IST  
**Baseline preserved:** release `a3df314` · backend `sha256:ebee1adb…` unchanged  
**Golden:** known-good `kb-edr-key-202610311152` · candidate `kb-firstboot-identity-202610310829` · clone **219 stopped**

## This pass

| Item | Result |
|---|---|
| E22 pre-deactivation token | Same JWT after disable → me/dashboard **403**; re-login **403**; no refresh endpoint (N/A) |
| E15/E12b investigation path | Inject-in-alert tests OK (converse data-not-command, playbook refuse, closure shadow, dossier redaction) — not routing-canary |
| Golden bake + enroll | Candidate baked; clone firstboot unique id; register → `tenant_ALPHAWINCORP_6VS2`; reboot preserved; no callback secret; **stopped** |
| Closed areas | Recovery/rollback/restore/ingress/portals/keys/lifecycle **not** reopened |

## Exact next operational step

Decide whether candidate snap `kb-firstboot-identity-202610310829` becomes the new golden tip (optional: one more bake after netplan-MAC firstboot tweak in tree), or keep `kb-edr-key-202610311152` as tip until that bake. Do **not** republish fleet keys unless a customer appliance needs the new firstboot image.

## Still separate / blocked

Paging delivery · staffing · physical mic · autonomous closure · adapter depth (Zeek CP rows, hunts, enrichment, deeper scans).
