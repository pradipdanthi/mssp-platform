# PM-002B — Configure NikTiar MSSP Project Control Model in OpenProject

## OBJECTIVE

Configure the approved Version 1 NikTiar MSSP engineering/project-management model in the existing OpenProject Community Edition instance.

OpenProject:

`http://192.168.0.238:8080`

Server:

`pm-server`
`192.168.0.238`

PM-001 foundation is complete.

PM-002A design has been reviewed by the Software Architect and deliberately simplified.

This task IS authorized to configure OpenProject.

Do NOT modify the MSSP source repository.

Do NOT modify Proxmox.

Do NOT modify MSSP runtime infrastructure.

---

# IMPORTANT DESIGN DECISION

Use ONE OpenProject project initially.

Project name:

`NikTiar MSSP Platform`

Do NOT create twelve domain subprojects yet.

The twelve engineering domains will initially be represented using the `Domain` custom field.

Future subprojects may be introduced only if actual usage proves they are needed.

---

# PHASE 1 — PRE-CONFIGURATION BACKUP

Before changing OpenProject configuration:

Create a fresh OpenProject backup using the existing official Compose backup mechanism.

Verify PostgreSQL and assets backup archives are non-zero.

Record filenames.

If backup fails:

STOP.

Do not configure OpenProject.

---

# PHASE 2 — CREATE MASTER PROJECT

Create:

Name:
`NikTiar MSSP Platform`

Identifier:
choose a concise stable identifier such as:

`niktiar-mssp`

Description:

`Engineering and product-control workspace for the NikTiar multi-tenant MSSP platform.`

Enable only appropriate modules initially, including:

- Work packages
- Boards if Community Edition supports required basic board
- Wiki/document capability if useful
- Time tracking only if already enabled by default and harmless

Do not enable unnecessary modules merely because available.

---

# PHASE 3 — PRODUCT DOMAINS

Create one work-package custom field:

`Domain`

Type:
single-select list

Values exactly:

`PLT — Platform & Architecture`

`CTL — Control Plane & Identity`

`POR — Portals`

`APP — Appliance Platform`

`SOC — Security Operations`

`DET — Detection & Response`

`EXP — Exposure & Assurance`

`INT — Integrations`

`AI — AI & Triage`

`SOV — Sovereign Edge`

`INF — Infrastructure & Lab`

`XCT — Cross-Cutting`

Enable it for the NikTiar MSSP Platform project.

Do not create domain subprojects.

---

# PHASE 4 — WORK PACKAGE TYPES

Configure these Version 1 work-package types:

1. Epic
2. Feature
3. Task
4. Bug
5. Architecture Decision
6. Security Finding
7. QA Validation
8. Technical Debt
9. Release

Reuse suitable existing OpenProject types where appropriate rather than creating duplicates.

Disable unnecessary types from the NikTiar project where safe.

Do not delete built-in types globally unless absolutely necessary.

---

# PHASE 5 — STATUSES

Create/use these statuses:

1. IDEA
2. BACKLOG
3. READY
4. IN PROGRESS
5. VALIDATION
6. SECURITY REVIEW
7. REWORK
8. BLOCKED
9. RELEASE READY
10. DONE
11. CANCELLED

Map OpenProject's existing statuses where semantically equivalent rather than creating duplicates unnecessarily.

DONE and CANCELLED should be treated as closed statuses.

---

# PHASE 6 — WORKFLOWS

Configure practical workflows for the Administrator/project-manager role.

Do not build an excessively restrictive workflow yet.

Expected normal feature/task flow:

IDEA
→ BACKLOG
→ READY
→ IN PROGRESS
→ VALIDATION

Then:

If security review required:

VALIDATION
→ SECURITY REVIEW

Security pass:
SECURITY REVIEW
→ RELEASE READY

Security failure:
SECURITY REVIEW
→ REWORK

No security review:

VALIDATION
→ RELEASE READY

Then:

RELEASE READY
→ DONE

Other paths:

IN PROGRESS / VALIDATION / SECURITY REVIEW
→ BLOCKED

BLOCKED
→ READY or IN PROGRESS

REWORK
→ IN PROGRESS

Any appropriate open state
→ CANCELLED

Allow reasonable administrative correction transitions during the initial adoption period.

Do not configure Enterprise-only automation/custom actions.

---

# PHASE 7 — PRIORITIES

Configure/use:

CRITICAL
HIGH
NORMAL
LOW
SOMEDAY

Set NORMAL as the default if OpenProject permits it.

Definitions:

CRITICAL
Security, production, data-loss or release-blocking emergency.

HIGH
Current release/sprint commitment or important dependency.

NORMAL
Normal planned roadmap work.

LOW
Useful but deferrable work.

SOMEDAY
Idea parking with no current commitment.

Do not delete system priorities globally unless safe.

---

# PHASE 8 — CUSTOM FIELDS

Create only these Version 1 custom fields:

## 1. Domain

Already created.

Required where practical.

## 2. Work ID

Type:
Text

Examples:
SEC-001
PM-002
SOV-001

## 3. Workstream

Type:
List

Values:

A — Active Workstream 1
B — Active Workstream 2
None

## 4. Architecture Status

Type:
List

Values:

Not Required
Proposed
Approved
Superseded

## 5. Security Status

Type:
List

Values:

Not Required
Required
In Review
Pass
Fail
Waived

## 6. QA Status

Type:
List

Values:

Not Started
Unit Pass
Integration Pass
Lab Pass
Regression Pass
Fail

## 7. Security Impact

Type:
List

Values:

None
Low
Medium
High
Critical

## 8. Git Branch

Type:
Text

## 9. Git Commit

Type:
Text

## 10. Source / Origin

Type:
List

Values:

Orchestrator
Audit
Lab Validation
Customer
Technical Debt
Incident
Historical Recovery

Enable fields on appropriate work-package types without making every field mandatory initially.

Only Domain and Work ID should be strongly considered for routine governance.

Do not add:

KB Reference
Impact Surface
Breaking Change
AI Prompt Reference
Implementation Agent
Git Tag
Dependency Risk

during PM-002B.

These remain future candidates.

---

# PHASE 9 — WORK ID POLICY

Do NOT try to replace OpenProject's native numeric work-package IDs.

Work ID is an additional human-readable governance identifier.

Title format:

`[WORK-ID] Concise outcome`

Examples:

`[SEC-001] Harden Sovereign unified portal authentication and RBAC`

`[QA-001] Sovereign release regression validation`

`[PM-002] Configure MSSP project management`

Historical IDs must never be renumbered.

---

# PHASE 10 — RELEASE / VERSION FOUNDATION

Use OpenProject native Versions for release planning.

Create only:

`sovereign-beta`

Do NOT create speculative product versions yet.

Git tags remain authoritative for source releases.

Do NOT create a Git tag.

---

# PHASE 11 — CREATE GOVERNANCE EPICS

Create:

## Epic 1

Work ID:
`SOV-REL-001`

Title:
`[SOV-REL-001] Sovereign Edge Release Readiness`

Domain:
SOV

Workstream:
A

Status:
IN PROGRESS

Priority:
HIGH

Description should state that this Epic tracks the current Sovereign Edge branch through security, QA, merge and release readiness.

## Epic 2

Work ID:
`PM-002`

Title:
`[PM-002] Establish MSSP Engineering Project Governance`

Domain:
PLT

Workstream:
B

Status:
IN PROGRESS

Priority:
HIGH

Description:
Establish OpenProject as the authoritative project-state and work orchestration layer.

---

# PHASE 12 — MIGRATE COMPLETED RECOVERY HISTORY

Create the following historical work packages.

Do not fabricate dates/evidence that are unknown.

## REC-001

Type:
Task

Title:
`[REC-001] Classify uncommitted Sovereign Edge development`

Domain:
XCT

Status:
DONE

Source:
Historical Recovery


## REC-002

Type:
Task

Title:
`[REC-002] Preserve Sovereign Edge work on dedicated branch`

Domain:
SOV

Status:
DONE

Git Branch:
`kb112-sovereign-edge`


## REC-003

Type:
QA Validation

Title:
`[REC-003] Perform Sovereign Edge merge-readiness review`

Domain:
SOV

Status:
DONE


## REC-004

Type:
QA Validation

Title:
`[REC-004] Perform controlled Sovereign runtime validation`

Domain:
SOV

Status:
DONE

In description explicitly note:

`Final classification at the time: PARTIALLY VALIDATED.`


## REC-005

Type:
Task

Title:
`[REC-005] Stabilize KB-113 logical HA validation`

Domain:
SOV

Status:
DONE

Git Branch:
`kb112-sovereign-edge`

Git Commit:
`46ff0f7`

QA Status:
Lab Pass


## SEC-001

Type:
Security Finding

Title:
`[SEC-001] Harden Sovereign portal authentication and RBAC`

Domain:
SOV

Status:
DONE

Git Branch:
`kb112-sovereign-edge`

Git Commit:
`87821f1`

Security Status:
Pass

Security Impact:
High

QA Status:
Lab Pass


## PM-001

Type:
Task

Title:
`[PM-001] Deploy OpenProject foundation`

Domain:
PLT

Status:
DONE

Source:
Historical Recovery


## PM-001A

Type:
Task

Title:
`[PM-001A] Expand OpenProject VM capacity`

Domain:
INF

Status:
DONE

Source:
Historical Recovery

Add concise descriptions based on known completion evidence.

Do not paste enormous terminal logs.

---

# PHASE 13 — RELATIONS / HISTORY

Create meaningful relations where supported.

At minimum:

REC-001
precedes
REC-002

REC-002
precedes
REC-003

REC-003
precedes
REC-004

REC-004
precedes
REC-005

REC-005
precedes
SEC-001

Do not use hard BLOCKS relations for already completed historical sequencing unless genuinely needed.

Relate REC-002 through SEC-001 to the Sovereign Release Epic where practical.

---

# PHASE 14 — CREATE CURRENT NEXT WORK

Create:

## QA-001

Type:
QA Validation

Title:

`[QA-001] Sovereign Edge release regression sign-off`

Domain:
SOV

Workstream:
A

Status:
READY

Priority:
HIGH

Security Status:
Not Required

QA Status:
Not Started

Git Branch:
`kb112-sovereign-edge`

Parent or relation:
SOV-REL-001

Description:

Final controlled QA gate before Sovereign branch merge-readiness review.

Do NOT execute QA-001 during PM-002B.

---

# PHASE 15 — PM-002 CURRENT STATE

Create or update:

`[PM-002] Establish MSSP Engineering Project Governance`

and represent the configuration work as active.

If useful, create child Task:

`[PM-002B] Configure OpenProject MSSP governance model`

Status:
IN PROGRESS

Domain:
PLT

Workstream:
B

Do not create another separate Work ID if OpenProject hierarchy becomes cumbersome; preserving PM-002 umbrella is more important than excessive granularity.

---

# PHASE 16 — ARCHITECTURE PLACEHOLDER

Create ONE initial Architecture Decision work package:

Work ID:

`ARCH-001`

Title:

`[ARCH-001] Define official customer appliance delivery model`

Domain:
APP

Status:
BACKLOG

Architecture Status:
Proposed

Priority:
HIGH

Description should summarize the unresolved decision:

- VM199 full-disk clone
- mkosi immutable image
- retired ISO path

Full ADR document will later live in Git.

Do not decide the architecture during PM-002B.

---

# PHASE 17 — INITIAL TECHNICAL DEBT ITEMS

Create only these high-value initial debt items:

## TD-001

`[TD-001] Remove or gate synthetic production data paths`

Domain:
appropriate domain/XCT

Status:
BACKLOG

Priority:
HIGH


## TD-002

`[TD-002] Remove hard-coded lab infrastructure defaults`

Domain:
INF

Status:
BACKLOG

Priority:
NORMAL


## TD-003

`[TD-003] Establish appliance automated test suite`

Domain:
APP

Status:
BACKLOG

Priority:
NORMAL


## TD-004

`[TD-004] Design control-plane high availability`

Domain:
CTL

Status:
BACKLOG

Priority:
NORMAL

Do not create every known debt item yet.

---

# PHASE 18 — SAVED VIEWS

Create saved Work Package views where Community Edition permits:

## Current Development

Filter:

Status =
IN PROGRESS
VALIDATION
SECURITY REVIEW
REWORK

Show:

Work ID
Subject
Type
Domain
Workstream
Status
Priority
Assignee


## Up Next

Filter:

Status = READY

Sort:

Priority descending


## Backlog

Filter:

Status = BACKLOG

Group by:

Domain


## Blocked

Filter:

Status = BLOCKED


## Security

Filter:

Type = Security Finding
OR Security Status in Required/In Review/Fail


## QA

Filter:

Type = QA Validation


## Technical Debt

Filter:

Type = Technical Debt

Group:
Domain


## Architecture Decisions

Filter:

Type = Architecture Decision


## Sovereign Edge

Filter:

Domain = SOV

Sort:
Status, Priority

If any desired grouping/filter is unavailable in Community Edition, document the limitation rather than forcing a workaround.

---

# PHASE 19 — BOARD

Create ONE initial board:

`Engineering Flow`

Prefer a simple/basic or status board supported by Community Edition.

Desired visual stages:

BACKLOG
READY
IN PROGRESS
VALIDATION
SECURITY REVIEW
BLOCKED
RELEASE READY
DONE

If a true status-action board is Enterprise-only in this installed version, use the Community-supported basic board and document the limitation.

Do not create multiple experimental boards yet.

---

# PHASE 20 — WIP VISIBILITY

Ensure Workstream field allows filtering:

A — Sovereign Release

B — Project Governance

Create saved views if practical:

`Workstream A — Sovereign`

`Workstream B — Governance`

Do NOT attempt automated enforcement.

WIP enforcement remains an orchestrator policy:

Maximum two major active Epics/workstreams.

---

# PHASE 21 — SOURCE OF TRUTH

Put this concise policy in the main project description or wiki:

OPENPROJECT
owns work state, priority, roadmap, dependencies, milestones and gate status.

GIT
owns code, ADR documents, KB documents, scripts, infrastructure definitions, commit history and source tags.

CHATGPT
owns architecture guidance, orchestration, task sequencing, Cursor prompts and implementation review.

CURSOR
owns implementation execution, terminal operations, testing and completion reports.

No AI conversation is the sole source of project truth.

---

# PHASE 22 — VALIDATION

Validate that:

- project exists
- 12 Domain values exist
- 9 work package types available
- intended statuses exist
- workflows permit normal transitions
- priorities exist
- 10 custom fields exist
- historical work packages exist
- Sovereign Epic exists
- QA-001 exists and is READY
- PM governance workstream exists
- ARCH-001 exists
- TD-001 through TD-004 exist
- saved views work
- board displays cards
- no unexpected Enterprise-only dependency prevents normal use

Create ONE temporary test Task if necessary:

`[TEST] PM-002B workflow validation`

Move it through:

BACKLOG
→ READY
→ IN PROGRESS
→ VALIDATION
→ RELEASE READY
→ DONE

Then DELETE the test work package if safely supported, otherwise mark CANCELLED with clear TEST label.

Do not leave misleading test data.

---

# PHASE 23 — BACKUP AFTER CONFIGURATION

After successful configuration:

Create another official OpenProject backup.

Verify PostgreSQL and assets archives are non-zero.

This becomes the PM-002B configuration baseline.

---

# REQUIRED COMPLETION REPORT

Return:

1. Pre-Configuration Backup
2. Project Created
3. Domains
4. Work Package Types
5. Statuses
6. Workflows
7. Priorities
8. Custom Fields
9. Version
10. Governance Epics
11. Historical Work Migration
12. Relations
13. QA-001
14. ARCH-001
15. Technical Debt
16. Saved Views
17. Board
18. WIP Views
19. Source-of-Truth Policy
20. Workflow Validation
21. Community Edition Limitations
22. Post-Configuration Backup
23. Final OpenProject Inventory
24. Readiness Decision
25. Recommended Next Action

Readiness must be:

OPENPROJECT GOVERNANCE READY

OPENPROJECT GOVERNANCE PARTIAL

OPENPROJECT CONFIGURATION FAILED

End exactly:

PM-002B COMPLETE

OpenProject modified: YES

MSSP repository modified: NO

MSSP runtime infrastructure modified: NO