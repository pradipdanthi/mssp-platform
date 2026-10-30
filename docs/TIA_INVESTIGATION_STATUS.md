# TIA investigation status

Last updated: 2026-10-30 (voice workflow on the throwaway rig). Policy version: `tia-closure-1`.

This is a progress record, not a claim that autonomous closure is safe to enable.

## Round 10 — voice workflow on the throwaway test build (2026-10-30)

Artifacts: `docs/tia_measurements/2026-10-30_voice_workflow/`. Production containers were not rebuilt or recreated. VM 117 was not used as staging.

Simulated microphone (`http://127.0.0.1:15174/?voice=fixture`) drove: critical list → barge-in describe first (HOST-A2) → “yes, open it” with verified load of `/alerts/0104dd4a-…` → follow-up retained HOST-A2 → `investigate this` queued a durable job. A **real** worker+model run on HOST-A1 (synthetic dossier only, production `/api/v1/chat`, no production callback) wrote **TIA investigation note** on INC-E2E-001 at 16:39:30Z (28.9 s model, verdict Critical / disposition malicious, policy tia-closure-1, incident status unchanged).

Settle wait on finished commands cut from 1.3–1.7 s to 220–280 ms. Remaining simple-turn delay is neural TTS (~800–970 ms uncached). First useful audio on those turns ~0.9–1.2 s. Physical microphone is **not** in this evidence.

## Round 9 — exercised workflows (2026-10-30)

Artifacts: `docs/tia_measurements/2026-10-30_round9/`. Production containers were not rebuilt. VM 117 was not used as staging.

### Voice / navigation conversation — real integration demonstrated (e2e rig)

Operator typed the requested sequence on `http://127.0.0.1:15174` (SOC UI) against `http://127.0.0.1:18000` (throwaway API). Tenant E2EA.

| Item | Value |
|---|---|
| conversation_id | `a964643b-2a27-4543-918f-b96c1b8d440f` |
| session_id | `s00a963b23e1daee9122b` |
| request (count) | `2cacb9edbe4946b7` |
| request (describe) | `3f5b1e7e9f8b42ff` |
| request (open) | `2d95f0f248284ebe` |
| request (evidence) | `01f0aa3706fb4c8d` |
| alert / case | `0104dd4a-2634-48e9-8be1-92c56c9c7380` (Ransomware-like file renames on HOST-A2) |
| pending_action | `2cac80ba-46ed-4dab-bac3-3cb5d3c61d96` open_case, executed, expired 16:13:06Z |
| ui_command | `a032c465-59a1-4753-a2cb-e0494f7eeb09` acknowledged |
| ack | `loaded_alert_id` matched; `late=false` |
| frontend route | `/alerts/0104dd4a-2634-48e9-8be1-92c56c9c7380` |
| issue→ack | 153 ms |
| spoken confirmation | after ack only: "Confirmed: … is open on your screen" |

A generated "opened" sentence was not used as proof. Isolate-by-voice still refuses (`disruptive_refused`). Bare "yes" with nothing pending does nothing.

Physical microphone interruption: **pending**. Barge-in wiring (keep STT live, echo filter, release busy before TTS) is in `ChatPanel.tsx` + `tiaBargeIn.ts`. A test hook that calls `stop()` is not microphone proof.

### Latency — measured baseline, not an optimisation pass

See `latency_table.md`. Cursor CLI on VM 117 is the 18 s-timeout path (serial p50 15.0 s, max 18.5 s, n=8). `/converse` tools are tens of milliseconds. First useful audio vs 2.5 s: unmet/unmeasured on the voice path.

### Engine health

Same-day live adapter run (not this process; production image does not yet contain `tia_engine_health.py`): `docs/tia_measurements/2026-10-30_engine_health_real/real_engine_health_after_fix.json`. Wazuh API 4.14.6, administrator role, application daemons running, telemetry degraded (`agents_disconnected`). TheHive 4.1.24-1 reachable/authenticated. Idle optional daemons are not labelled unhealthy. Simulated outages: `simulated_outages.json`. Voice/dashboard on the e2e rig use the module; production UI still needs a deploy.

### Operational ticket

Authoritative ticket for analysts today: MSSP `incidents` + `incident_timeline` (TheHive listCase was 0). INC-E2E-002 timeline row `TIA investigation note` at 2026-10-30 15:44:50Z is visible on `/incidents/90631fba-33b1-4c33-9400-fd51b3d89c1b`. TheHive ID reconciliation: **pending** (no TheHive cases, integration not writing).

### Closure

`authorized_scanner` close-matches locally demonstrated (out of scope, expired approval, unavailable correlation, sibling malicious on the incident, closing an alert does not close the incident). Disposition remains `authorized_benign`, not `false_positive`. Genuine detection-specific FP playbook: **explicitly incomplete** (no reviewed misfire corpus). Held-out set: `held_out_closure_eval.md` — 8 synthetic rows, 0 independent reviews. Production enablement remains off.

### Remaining smallest asks

1. Physical microphone session on the SOC console (barge-in + first-audio timing).
2. Root on an authorised **disposable** VM for `scripts/tia_isolation_canary.sh` (not VM 117).
3. Independent SOC labels on the held-out closure set.
4. Control-plane deploy when you want production UI to use `/converse` + engine health (not done this round).


## What was traced

Alert path that exists today: engines post into the control plane, `soc_sync_service` writes `security_alerts`, and the SOC agent on VM 117 can draft a verdict through `soc_agent_expert`. That draft is stored on the alert. It does not close the ticket by itself. Containment (isolate / disable user) is marked proposed and is not executed.

Voice path that exists today: the console microphone uses browser speech recognition, `POST /admin/soc-console/chat` answers from PostgreSQL for status questions, and `POST /admin/soc-console/speak` returns an Aria audio file. Playback is in the SOC console page.

Model path that exists today: VM 117 runs the Cursor CLI (`agent -p --mode ask`) with `CURSOR_API_KEY`. The control plane calls that VM over HTTP with `SOC_AGENT_TOKEN`. That is a subscription CLI, not a documented unattended inference API with a reviewed data-processing agreement. Customer alert text can be sent there when expert triage or a deep voice question runs.

## Observed defects fixed in this change

- A model `TIA_ACTIONS` block could set an alert to `false_positive` or `closed` when auto-approve was on, with no playbook. File: `backend-api/app/services/soc_console_chat.py`.
- Those updates matched the alert id only, so a model-supplied id was not checked against the customer on the conversation. File: `backend-api/app/services/soc_console_tia.py`.
- The model label `Benign` was stored as the same verdict as a false positive (`BENIGN_FALSE_POSITIVE`) because the database only allows three verdict strings. The policy vocabulary now keeps them separate. The database column is unchanged.

## Implemented (this revision)

- Versioned policy `tia-closure-1` in `backend-api/app/services/tia_closure_policy.py`.
- Shadow mode: model auto path cannot close or resolve tickets. Confidence is ignored.
- Analyst approval and the explicit analyst action API can still change ticket status.
- Disruptive action types are refused on this ticket interface.
- Model auto writes that are allowed (a comment, or a non-closing status) must match the server tenant on the row.
- Runtime contract text is in the policy module.
- Tests: `backend-api/tests/test_tia_closure_policy.py`.

## Not implemented

- Versioned per-alert-family playbooks and customer-enabled auto-closure. Leave this off.
- Distinct database verdict values for benign authorized activity (needs a schema change).
- A production model provider other than the Cursor CLI.
- Full evidence dossiers, escalation paging, and closure sampling.
- Measured voice latency against the 2.5s / 300ms targets.

## Status labels

| Item | State |
|---|---|
| Closure policy gate | Implemented, tested locally |
| Live API image | Deploy required before the running console uses it |
| Customer auto-closure | Not enabled |
| Cursor CLI as production inference | Integration exists, not accepted as the production provider |

## Repair pass — increment 1: false-benign failure path

Status key: **Implemented** (code in the tree) · **Locally tested** (throwaway containers, synthetic data) · **Staging verified** (a non-production deployment) · **Production enabled** (live).

| Item | Implemented | Locally tested | Staging verified | Production enabled |
|---|---|---|---|---|
| Agent returns an explicit failed result instead of a heuristic verdict | yes | yes (18 tests) | no | no |
| Control plane validates every result (HTTP and callback) | yes | yes | no | no |
| Durable analyst review items + migration `117_tia_review_items.sql` | yes | yes (real Postgres) | no | **migration not applied** |
| Degradation read from `execution_status`, not model-name text | yes | yes | no | no |
| Rule-based fallback can never be low-priority, persisted benign, or auto-closed | yes | yes | no | no |
| Failed deep stage no longer hidden by a successful descriptive stage; dead-letter writes a review item | yes | yes | no | no |
| Review queue API + `needs_attention` line | yes | yes | no | no |

Root cause: `analyst.py` replaced a failed Cursor call with a verdict built from local rules (`Benign` when the heuristic score was low), returned `ok: true`, and the control plane then mapped it to `BENIGN_FALSE_POSITIVE`, which the escalation rules treat as "no human wake" for high and medium alerts. Detection of degradation was `"fallback" in model`, which the Cursor path never matched. `apply_callback_payload` also rewrote `ok: false` to `ok: true`. `agent_result_to_triage` defaulted a missing verdict to Suspicious and a missing confidence to 50.

Behavior now:
- Execution status (`succeeded | degraded | failed | timed_out`), disposition (`malicious | inconclusive | unset`), source severity (never rewritten), assessed priority (P1–P4 from severity and asset tier), review-required, and page are separate fields.
- A model "Benign" is recorded as `inconclusive`. `false_positive` and `authorized_benign` are set only by an analyst or a verified playbook.
- The model can request review. It cannot remove a required review, and unknown keys (for example a notification destination) are dropped during validation. Recipients come only from the server on-call roster.
- Critical severity (or high severity on a critical-tier asset) with no analysis pages immediately. Other failures go to the review queue with a deadline.
- Provider-wide failures (auth, missing binary, not configured, agent unreachable) send one outage notice per category per hour for non-paging cases. Every case still has its own review item.
- If no on-call roster is configured, the page is recorded as `no_recipients_configured` on the review item and counted on the console instead of being silently dropped.
- Transient failures (timeout, agent unreachable, agent HTTP error) are retried through the existing bounded queue; the review item already exists, so a retry cannot lose the case. After the retry limit the job is dead-lettered and a review item is written.

Tests: `soc-agent/tests/test_failure_path.py` (18), `backend-api/tests/test_tia_failure_path.py` (45, includes replay of the audited fixture for critical, high, and medium plus auth failure, timeout, nonzero exit, malformed JSON, missing fields, empty output, and a model trying to suppress escalation). Existing `test_ai_deep_triage.py`, `test_soc_agent_integration.py`, and `test_tia_closure_policy.py` pass after updating them to the explicit-status contract. The full backend suite shows 5 import errors in `test_sovereign_*` that come from a module outside the image and are unrelated.

Limitations still open after this increment:
- The HTTP reply and the callback are validated identically but still persist separately. A callback that arrives after an HTTP timeout stores a draft verdict and does not itself page. Increment 2 replaces this with one transactional acceptance.
- The review queue has an API only; the SOC console UI does not list the items yet (the count and overdue status appear in `needs_attention`).
- The queue still blocks its worker during retry backoff (increment 4).
- Deadlines (`TIA_REVIEW_DUE_MINUTES_*`: 15 / 60 / 240 / 1440 for critical / high / medium / low) are placeholders, not SOC-owner-approved values.
- `SOC_ONCALL_WHATSAPP` is unset in production, so no page can currently be delivered.

Deploy order (nothing below has been run against production):
1. Apply `postgres/init/117_tia_review_items.sql` with `psql` in a change window. It is additive. Until it is applied, failures are logged loudly and paging still works, but no review item is stored.
2. Deploy the new `soc-agent/` files to VM 117 and restart `mssp-soc-agent.service`. Until then the old agent keeps working, and the control plane recognises its heuristic fallback and treats it as a failure.
3. Rebuild and recreate `backend-api`, then `frontend-admin` and `frontend-customer` (stale upstream rule), then run `./scripts/production_deploy_control_plane.sh` and `./scripts/run_post_change_checks.sh`.

Rollback: redeploy the previous agent and backend images. The migration can stay (an unused table is harmless); to remove it, `DROP TABLE tia_review_items;`.

Not touched: automatic closure stays off (`ENABLE_AUTO_CLOSE_LOW_RISK=false`, and the closure policy still refuses `model_auto`), and disruptive actions remain approval-gated. No credentials were rotated, no queued work was discarded, and no production setting was changed.

## Repair pass — increment 2: one acceptance path, late results, outbox, review queue

Status key as above. Everything below is **implemented and locally tested** (throwaway Postgres container plus a separately tagged test image; synthetic data; a recording transport, no network, no real contacts). **Nothing is staging verified (no staging environment exists yet) and nothing is production enabled.** Migration `118_tia_result_acceptance.sql` has not been applied to the live database.

| Item | Implemented | Locally tested | Staging verified | Production enabled |
|---|---|---|---|---|
| One tenant-bound acceptance transaction for HTTP reply, callback and the local fallback (`tia_acceptance.accept_result`) | yes | yes | no | no |
| Immutable result per attempt, duplicate vs conflicting payload detection | yes | yes | no | no |
| HTTP timeout recorded as *outcome uncertain*; late callback accepted through the same logic | yes | yes | no | no |
| Review state machine (create / recur / priority raise / reopen / resolve), deadlines only move earlier | yes | yes | no | no |
| Schema readiness gate; work kept in the queue, never acknowledged, when migrations are missing | yes | yes | no | no |
| Notification outbox with per-recipient idempotency keys, bounded retries, lease recovery after a crash | yes | yes | no | no |
| Delivery states, overdue-acknowledgement escalation, configuration faults | yes | yes (transport faked) | no | no |
| Review list/detail API and SOC console page; audited acknowledge / assign / resolve / reopen | yes | yes (API); page builds | no | no |
| Agent callback spool (disk-backed retry, binding echoed) | yes | yes (11 tests) | no | no |
| Manual-review mode (`TIA_INVESTIGATION_MODE=manual_review`) | yes | yes | no | no |
| Real notification provider integration test | prepared | **not run** (needs a designated destination) | no | no |

### How a result is accepted

Every route (HTTP reply, callback, local rule-based fallback) calls the same function. In one database transaction it:
1. checks the schema, then locks the alert row under the server tenant (a tenant id or job id supplied by the caller that does not match is refused with 409 and logged);
2. validates the attempt, the job id (`alert_id:evidence_version`) and the evidence version;
3. stores one immutable `tia_results` row with a payload hash. The same hash again is a duplicate (no new transition, review item, ticket note or notification). A different payload for the same attempt is rejected (409), never overwritten;
4. decides whether the result may change authoritative state (`applied`, `apply_reason`): stale evidence, an analyst decision, or a newer attempt keep the result as history only. A serious finding in a result that cannot be applied is still surfaced (it raises priority or adds an event) without overwriting state;
5. creates or updates the review item and writes the required notification rows. External sending happens afterwards from the outbox. A crash after commit leaves `queued` rows that the next worker claims.

A notification is a new notification (not a duplicate) when the priority rises, the finding class gets worse, the evidence version changes, or an escalation level is reached; the idempotency key includes all of these.

### Notification states and what they claim

`required → queued → submitted → delivered | failed → acknowledged` (plus `cancelled` when a person resolves the item first).

| State | Meaning | Evidence needed |
|---|---|---|
| required / queued | Work is recorded / a worker holds a lease | none |
| submitted | The provider accepted the request. **This is not human receipt.** | provider message id |
| delivered | The provider reported delivery | `record_delivery_receipt` (no provider webhook is wired yet, so nothing reaches this state today) |
| failed | Retries exhausted or a permanent error | last error is stored |
| acknowledged | A person acknowledged the review item in the console | actor and time |

Unset `SOC_ONCALL_WHATSAPP` is reported by `/api/admin/soc-console/tia-readiness` and on the review page as a configuration fault; page rows are stored with `blocked_reason` instead of disappearing, and are expanded to recipients once a roster is configured. If a page stays unacknowledged past `TIA_PAGE_ACK_MINUTES` (default 15, **provisional**), a level-2 page goes to `SOC_ONCALL_ESCALATION_WHATSAPP`.

### Review deadlines are provisional

`TIA_REVIEW_DUE_MINUTES_*` (15 / 60 / 240 / 1440 for critical / high / medium / low) and `TIA_PAGE_ACK_MINUTES` are placeholders for the SOC owner to approve. The API returns `deadline_basis: "provisional"` and the page labels the column "Deadline (provisional)". They are not customer SLAs. Retries and recurrences never reset `first_seen_at` or move a deadline later.

### Roles (enforced by the server, not the page)

| Action | platform_admin | soc_manager | soc_analyst | customer roles |
|---|---|---|---|---|
| list, detail, counts, readiness | yes | yes | yes | 403 |
| acknowledge | yes | yes | yes | 403 |
| assign | anyone | anyone | self only | 403 |
| resolve (note required) | yes | yes | only items assigned to them | 403 |
| reopen (note required) | yes | yes | no | 403 |

Acknowledge records ownership of the page and never resolves the item or changes the security case.

### Migration validation (local, throwaway databases)

`scripts/tia_migration_validate.sh tia-test-pg` — 21 PASS, 0 FAIL across: fresh install; upgrade from the currently deployed schema (through 116: 118 alone refuses, then 117 and 118 succeed); upgrade from the increment 1 schema with existing review records (records and history preserved, 118 re-runnable, increment 1 writes still succeed). Dropped objects on rollback: none (additive tables stay).

If the schema is absent or a write fails: the callback returns 503 (so the agent spools it), the queue keeps the job, the review API returns 503, and `tia-readiness` shows `schema_not_ready`. There is no logging-only fallback.

### Local test results (reported separately)

| Run | Result |
|---|---|
| `test_tia_acceptance.py` (new) | 58 run, OK, 1 skipped (live provider test, by design) |
| Full backend suite, with `kevantic-appliance` mounted so the sovereign modules import | 309 run, OK, 1 skipped |
| Full backend suite, default setup | 284 run, **5 collection/import errors** (`test_sovereign_*`: `No module named 'sovereign'`), 3 skipped. The same 5 errors occur on the unchanged baseline under the same setup (they need `kevantic-appliance/` outside the backend image). The suite is **not** reported as fully passing in that configuration. |
| `soc-agent` tests | 29 run, OK |
| Migration validation | 21 passed, 0 failed |
| `frontend-soc` `vite build` | OK. `tsc --noEmit` reports 15 pre-existing unused-symbol/type errors in files this change does not touch; none in the changed files. The production image build runs `vite build` only. |
| `scripts/verify_platform_state.py` | 211 passed, 0 failed |

Changes to Increment 1 tests (disclosed): `test_tia_failure_path.py` was moved onto the new seams because `route_non_success`, `finalize_decision`, `supersede_failure_review` and the Redis outage de-duplication were replaced by the transactional path. One expectation changed on purpose: a later successful result no longer auto-resolves a failure review item (a person resolves it). The failure-fixture replay (critical, high, medium; auth failure, timeout, nonzero exit, malformed JSON, missing fields, empty output, model trying to suppress escalation) still passes unchanged in intent.

### Deploy order (not run; production unchanged)

1. Confirm the live schema: `SELECT to_regclass('tia_review_items');` (null means 117 is not applied).
2. In a change window apply `117_tia_review_items.sql` (if null) then `118_tia_result_acceptance.sql` with `psql`. Both are additive.
3. Deploy `soc-agent/` to VM 117 and restart `mssp-soc-agent.service` (the spool needs a writable state directory).
4. Rebuild and recreate `backend-api`, then `frontend-admin`, `frontend-customer` and `frontend-soc`, then `./scripts/production_deploy_control_plane.sh` and `./scripts/run_post_change_checks.sh`.
5. Check `tia-readiness`. Set `SOC_ONCALL_WHATSAPP` and `SOC_ONCALL_ESCALATION_WHATSAPP` only with operator-approved contacts, then run the designated-destination test below.

### Rollback and manual-review mode

- Redeploy the previous backend and agent images. **Do not drop the new tables**; they hold review items, results and notification history. Old code ignores them.
- Set `TIA_INVESTIGATION_MODE=manual_review` to stop calling the model entirely: every alert gets a review item and the normal notification rules. This does not bring back the false-benign behaviour. The old heuristic fallback verdict path is gone, and a failed or absent investigation never produces a verdict in any mode.
- `TIA_OUTBOX_ENABLED=false` stops sending but keeps rows queued; nothing is discarded.

### Real notification test (prepared, not run)

Run only against a number you designate that is not on the on-call roster:
`TIA_LIVE_TEST_DESTINATION=<number> TIA_LIVE_TEST_CONFIRM=<same number>` plus the provider credentials, then run `LiveNotificationIntegration`. It sends one synthetic message and proves provider acceptance only. Delivery and human receipt need the provider webhook (not built) and an acknowledgement in the console.

### Minimal isolated staging plan (synthetic data)

1. A separate VM or network namespace with its own Postgres and Redis, a tagged build of `backend-api`, and the `soc-agent` pointed at that backend. No production tenants, no production tokens, no on-call numbers.
2. Seed two synthetic tenants and a few alerts (critical, high, medium).
3. Exercise the real paths: agent HTTP reply, callback, a forced agent timeout followed by a late callback, a duplicate callback, a stopped Postgres during a callback (agent must spool and later succeed), the outbox worker with a stub provider endpoint, an unset roster, an acknowledgement, and an overdue acknowledgement.
4. Apply 117 then 118 from the 116 schema and check the review rows survive.
5. Record results here before anyone proposes production activation.

### Limitations still open after this increment

- No staging environment; nothing here has run outside local containers.
- Delivered receipts are not wired, so notifications stop at `submitted`.
- (Superseded by increment 3: the queue is now a durable Postgres table with non-blocking backoff and no inline fallback. Redis persistence is no longer the system of record.)
- Audit-log writes are best effort; `tia_review_events` is the authoritative audit trail.
- Deadlines and the 15-minute acknowledgement window are provisional.
- Prerequisites still open: Cursor account/plan eligibility and data-handling terms for customer data, rate and cost ceilings, and the personal-account credential on VM 117.


---

## Increment 3: conversation, durable jobs, engine health, verified closure, research

Status vocabulary used below. **Implemented** = code exists and local tests pass. **Production activated** = running on the live control plane / VM 117. **Production verified** = observed working there. **Nothing in this increment is production activated or production verified.** Everything below was exercised only in throwaway local containers with synthetic data.

### What TIA can demonstrably do (local evidence)

| Capability | Evidence (local) | Not shown |
|---|---|---|
| "What's critical?" -> describe -> "Yes, open it" -> case loads -> TIA confirms | 28 route tests with real JWT auth against Postgres, plus a real-browser typed run on a disposable rig (verified acknowledgement carrying `loaded_alert_id`, transcript persisted across the route change) | A spoken run with a real microphone; production |
| Confirmation only on a matching dashboard acknowledgement; wrong page, failure, expiry, duplicate ack, tenant switch, other session/operator all handled | `test_tia_conversation.py` | Frontend behaviour on a disconnected network beyond the unit-tested bridge |
| Disruptive requests refused in chat/voice (isolate, disable, block, close) | tests; the registry has no write/disruptive tool and `authorize` rejects those classes | - |
| Counts keep critical and high separate | tests (2 critical, 3 high, never "5 critical") | - |
| Layered engine health with honest degraded/unreachable/unauthorised/unknown | 24 tests with simulated engine responses | Any real engine: no probe has run against a real VM |
| Durable investigation queue: crash recovery, backoff, fairness, dead letters, sweeper | 18 tests incl. a real child process killed after claiming a job | Behaviour under production load; Redis/Postgres failover |
| One verified playbook closure (authorised scanner -> `authorized_benign`, status closed) and refusals | 28 tests | Closure quality on real data (no reviewed set exists) |
| Cited public reference lookup with an SSRF guard | 14 tests, no network | A real fetch from the allow-listed sites (off by default) |
| Case-specific ticket summary (facts / not known / hypotheses / next step) | 5 tests | Writing the summary into TheHive (not done) |

### Components changed and why

- `backend-api/app/services/tia_tools.py`, `tia_conversation.py`: one typed tool layer for text and voice; conversation scoped by (operator, session, tenant); pending actions bound to type, target, tenant, session, expiry; UI commands `issued -> acknowledged | failed | expired`. Migration `119`.
- `backend-api/app/services/tia_jobs.py`, migration `120`, `ai_alert_queue.py`: replaces pop-then-process Redis with leased Postgres jobs (priority, per-tenant cap, backoff via `next_run_at`, dead letters with a review item, stuck-lease recovery, sweeper). The inline fallback that reported success for non-durable work is removed; if no durable queue exists enqueue returns False and the readiness fault `jobs_schema_missing` is raised. Delivery is **at least once**; safety on a second delivery comes from the existing per-attempt immutable results, not from the queue.
- `tia_engine_health.py`: layers reachability / API / login / application / telemetry; each observation records source and time; cached results are labelled with age; each engine has a deadline so one hang cannot stall the rest; hosts and error detail only for `platform_admin` / `soc_manager`.
- `tia_playbooks.py`, migration `121`, `tia_closure_policy.py`: see below. `ai_tier1_triage._auto_close_enabled()` now always returns False and the model-confidence closure body is removed (the old `ENABLE_AUTO_CLOSE_LOW_RISK` flag could close alerts on a model verdict at confidence >= 95; that contradicted policy `tia-closure-1`). Setting the variable is logged and ignored.
- `tia_research.py`, `tia_ticket_summary.py`, `soc_agent_client.py` (verified TLS), `tia_trace.py` (latency), `frontend-soc` (bridge, transcript, always-mounted command bridge), `soc-agent/deploy/*` (runner isolation units), `scripts/tia_*`.

### Verified playbook closure (policy `tia-closure-1`, still shadow in production)

- Production ships with **no enablement rows**: migration 121 enables nothing; every evaluation is shadow-only and writes nothing to the alert. A human must insert an enablement naming who enabled it and the customer authorisation reference; there is no environment flag.
- Playbook `authorized_scanner` v1 closes a non-critical scanner-family alert as `authorized_benign` (status `closed`), **not** `false_positive`, because approved activity is real activity. A true false-positive playbook does not exist yet; the policy supports the `false_positive` disposition so one can be added and tested separately.
- Conditions are read from the database: an unrevoked approved-activity record for the same tenant, source and time window; a scanner rule family; severity not critical; required evidence present; no correlated high/critical non-scanner alert on the same host/source in 24 h; no accepted investigation marking it malicious.
- Outcomes: `close`, `refuse` (e.g. same scan from an unapproved source), `review` (missing or contradictory evidence -> durable review item). A closure re-checks the evidence immediately before writing, never overwrites an analyst's decision, runs once, is verified by reading back, and is audited. `reconcile` reopens it if contradicting evidence appears later.
- Shadow evaluation: `tia_playbook_evaluations.reviewer_label` records a human `agree` / `disagree`; `shadow_report()` computes agreement on reviewed rows only. **Gate before enabling for any customer:** a reviewed set that is separate from the examples used to write the rules, zero wrong closures on it, and a recorded customer authorisation. No such set exists today, so no closure quality claim is made.

### Local test results (reported separately)

| Run | Result |
|---|---|
| Backend suite, with `kevantic-appliance` mounted | 446 run, OK, 1 skipped (`test_analytics`: migration 045 absent from the throwaway DB; unrelated to TIA) |
| Backend suite, default setup | 421 run, the same 5 pre-existing `test_sovereign_*` import errors as the unchanged baseline, 3 skipped |
| New in this increment | jobs 18, conversation 28, engine health 24, playbooks 28, research 14, ticket summary 5, transport 6 |
| `soc-agent` tests | 47 run, OK |
| Migration validation (`tia_migration_validate.sh`) | 42 passed, 0 failed (adds 119/120/121 structure, idempotence, refusal constraints) |
| Frontend (`tia_frontend_check.sh`) | no new type errors vs HEAD baseline (13 vs 13 pre-existing); 9 bridge tests pass; production build OK |
| `scripts/verify_platform_state.py` | 231 passed, 0 failed, 0 gap |

Tests fail rather than skip when their dependencies are missing (set `TIA_ALLOW_SKIP_TESTS=1` to opt out).

### Latency: before and after

Measured locally with `scripts/tia_latency_probe.py` against a disposable backend (typed turns, no model, no speech, no browser, loopback network, 20 samples per cell, serial then 4 concurrent):

| Path | p50 / p95 serial | p50 / p95 x4 concurrent |
|---|---|---|
| tool turn (what's critical) | 25 / 31 ms | 48 / 59 ms |
| tool turn (counts) | 21 / 30 ms | 44 / 54 ms |
| engine health, live probes (hosts unreachable from the rig) | 31 / 39 ms | 74 / 81 ms |
| engine health, cached | 14 / 15 ms | 32 / 34 ms |
| model fallback (agent port closed: failure path only) | 81 / 86 ms | 163 / 174 ms |

**Before** (increment 2): there was no per-stage instrumentation and the deterministic tool path did not exist; every question went through `gather_operator_snapshot` plus a model call. A "before" figure was never measured and none is claimed. **These numbers say nothing about the real voice path.** The provisional targets (p95 <= 2.5 s end-of-speech to first useful audio for simple navigation/status; p95 <= 300 ms interruption to playback stop) are **unverified**: they need speech recognition, synthesis, the browser and the real network. Pending: the 18 s chat timeout root cause (needs model-hop timing on VM 117; use `scripts/tia_host_diagnostics.sh` during a test and the `agent_total` / `snapshot` stages from `GET /admin/soc-console/telemetry/latency`).

### Environment variables added (all optional; defaults are the safe state)

`TIA_WORKERS` (2), `TIA_JOB_LEASE_SECONDS` (900), `TIA_TENANT_MAX_RUNNING` (2), `TIA_DEADLETTER_MAX_REQUEUES`, `TIA_PENDING_TTL_SECONDS` (180), `TIA_UI_COMMAND_TTL_SECONDS` (90), `TIA_ENGINE_HEALTH_TTL_SECONDS` (30), `TIA_ENGINE_HEALTH_DEADLINE_SECONDS` (8), `TIA_TELEMETRY_STALE_MINUTES_<ENGINE>`, `TIA_RESEARCH_ALLOWED_DOMAINS` (empty = research off), `SOC_AGENT_CA_BUNDLE`, `SOC_AGENT_CLIENT_CERT`, `SOC_AGENT_CLIENT_KEY`, `SOC_AGENT_REQUIRE_TLS`. There is deliberately **no** variable that enables auto-closure. Research note: the `sha256` lookup sends a file hash to a third party; only add that site to `TIA_RESEARCH_ALLOWED_DOMAINS` after the data-sharing decision is made for each customer.

### Deployment scope (what a real rollout touches)

Control plane VM 100: `backend-api`, `frontend-admin`, `frontend-customer`, `frontend-soc` (rebuild all frontends when `backend-api` is recreated), Postgres (migrations), Redis (legacy queue only until drained). VM 117: `soc-agent` plus the new `tia-cli-runner`. The golden-VM-199 bake rule does **not** apply: nothing here ships in the appliance image.

### Deployment order (not run)

1. **Staging first** with synthetic data (plan above), including a killed worker and a stopped Postgres.
2. Back up the database. Apply `117`, `118`, `119`, `120`, `121` in order (all additive). Old code keeps working with them present. Check `tia-readiness`: `jobs_schema_missing` must be absent.
3. VM 117: run `soc-agent/scripts/install_runner.sh`, then follow the printed manual steps (place the Cursor key for the runner only, move other secrets, rotate the previously exposed credential, create TLS with `scripts/tia_tls_setup.sh`). Run `scripts/tia_isolation_canary.sh` as root; it must print PASS, not PENDING. Switch `SOC_AGENT_URL` to https and set `SOC_AGENT_CA_BUNDLE`, **then** set `SOC_AGENT_REQUIRE_TLS=true`.
4. Recreate `backend-api` then all three frontends; run `./scripts/production_deploy_control_plane.sh` and `./scripts/run_post_change_checks.sh`.
5. Confirm queued work drained from the old Redis list (the worker moves legacy items automatically; check `tia_jobs` stats in readiness).
6. Observe in shadow: playbook evaluations accumulate, nothing closes.

### Rollback per component

- `backend-api`: redeploy the previous image. Migrations 119-121 stay (additive, ignored by old code). Alerts enqueued while the new code ran are rows in `tia_jobs`; the old code does not read them, so before rolling back set `TIA_INVESTIGATION_MODE=manual_review` on the new code, wait for `queued`/`running` to reach 0 in readiness, then roll back. Otherwise the sweeper is absent in old code and those alerts would not be investigated until the new code returns. This ordering is a documented procedure, **not yet exercised**.
- Frontends: redeploy previous builds; the old chat path (`/chat`) is retained and used automatically when `/converse` is absent.
- VM 117: `systemctl stop tia-cli-runner`, restore the previous unit. If the runner is stopped the agent fails closed (no model call, review item), by design.
- Playbooks: delete nothing; set `disabled_at` on the enablement row. Closed alerts remain; `reconcile` can reopen them.

### Still open / unverified (do not treat as done)

- Systemd sandbox enforcement and the Cursor CLI's real permission behaviour: only syntactically verified; the canary reports PENDING without root on a disposable VM.
- No real engine adapter has been exercised; Shuffle's login layer reports `unknown` by design (the integration is webhook-only, so no credential is used to verify). The SOC agent and Wazuh/TheHive login checks are implemented but only against simulated responses. Suricata, Zeek, MISP, Greenbone, Velociraptor, Secure Edge have reachability and telemetry only (`no_adapter` for the rest).
- Deep investigation orchestration beyond the existing agent call: model routing by difficulty, per-investigation budgets and the "started a deep investigation" tool are **not built**. The durable queue they need now exists.
- TheHive: no ID reconciliation and no verified ticket write from TIA. The authoritative ticket record today is the MSSP `security_alerts` / `incidents` rows; TheHive is a downstream mirror and was not touched.
- Voice: visible listening/processing/speaking/interrupted states, interruption stopping obsolete audio, chunked-TTS evaluation and `first_audio` / `interrupt_to_stop` client timings are not implemented in this increment. Stale answers are dropped on tenant change (scope epoch) and duplicate acknowledgements are idempotent, both tested at the bridge level.
- Notification `delivered` receipts still need the provider webhook; unconfigured paging remains a visible fault.
- A manual microphone procedure: say "What's critical?", then "Describe the first one", then "Yes, open it" while watching the browser; the alert page must load and TIA must speak only after the acknowledgement. Interrupt mid-answer by speaking; playback must stop. Not yet run.
- `describe_alert` prints the raw event time string and may repeat the host name (cosmetic).
