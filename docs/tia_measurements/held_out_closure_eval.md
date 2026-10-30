# Held-out closure evaluation set

Status: **prepared for independent SOC review**. Labels below are case identifiers only.
This agent generated the set. It must **not** be treated as an independent review, and it
must not be used to claim production-ready false-positive closure.

Policy: `tia-closure-1`. Production enablement of `authorized_scanner` remains off.

## How to use

A reviewer who did not write the playbook fills `reviewer_label` (`agree` / `disagree` /
`abstain`) and `notes` on each row after inspecting the stored evidence. Agreement is
computed only over reviewed rows (`tia_playbooks.shadow_report`).

## Sample (synthetic, throwaway-rig identities)

| id | detection | intended disposition | playbook | expected outcome | independent review |
|---|---|---|---|---|---|
| H1 | nmap port scan from approved scanner, in scope, live approval | authorized_benign | authorized_scanner v1 | close | UNREVIEWED |
| H2 | nmap from unapproved address | refuse (not FP) | authorized_scanner v1 | refuse | UNREVIEWED |
| H3 | nmap from approved address, destination outside named CIDR | refuse | authorized_scanner v1 | refuse | UNREVIEWED |
| H4 | nmap, approval expired | refuse | authorized_scanner v1 | refuse | UNREVIEWED |
| H5 | nmap, correlation store unavailable | review | authorized_scanner v1 | review | UNREVIEWED |
| H6 | nmap plus ransomware-like sibling on same incident | review | authorized_scanner v1 | review | UNREVIEWED |
| H7 | credential dumping from scanner address | refuse (rule family) | authorized_scanner v1 | refuse | UNREVIEWED |
| H8 | analyst already closed the alert | already_terminal | authorized_scanner v1 | no overwrite | UNREVIEWED |

## Coverage (this set)

- Sample size: 8 synthetic cases, 0 independently reviewed.
- Wrong closures observed by this agent: not an independent figure.
- Missed threats: not scored; independent review required.
- Abstentions: 8/8 until a SOC reviewer labels them.

Zero observed wrong closures on this finite unreviewed set is **not** a guarantee of zero
production errors.

## Genuine false-positive playbook

**Explicitly incomplete.** There is no detection-specific, human-reviewed misfire corpus in
`tia_runbooks` (only test inserts for `wazuh:rule:99991`). `_matches_known_fp_pattern` is a
generic signed-binary/admin-user heuristic and is not a playbook. Required before implementing:

1. A named detection key (engine + rule id) with a documented misfire condition.
2. Approved scanner/identity is **not** enough — that is authorized activity, not a false positive.
3. At least two independently reviewed examples of the same detection firing on confirmed-benign
   customer evidence, with the contradictory-telemetry checks that would have failed a lookalike.
4. Tenant enablement and customer authorisation recorded the same way as `authorized_scanner`.
