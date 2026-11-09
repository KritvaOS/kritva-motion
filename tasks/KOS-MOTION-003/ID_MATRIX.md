# KOS-MOTION-003: ID dependency matrix

Derived from `tests/manifest/conformance_manifest.json` and `contract/CONFORMANCE_TEST_PLAN.md` on main (2026-11-07). It covers every ID that is not IN_SCOPE: 85 IDs (80 DEFERRED and 5 OUT_OF_SCOPE). The 39 IN_SCOPE IDs of KOS-MOTION-002 are unchanged and must keep passing. The classification below was confirmed by the owner in PR-01. The column "Status now" is the status when this file was written; the manifest is the current truth, and a test (`tests/lifecycle/test_lifecycle_matrix.py`, PR-06) compares the Decision column with the manifest for every ID.

Targets: 55 IDs. Of the 52 IDs the manifest marks as needing the lifecycle state machine, 51 stay targets and CT-LC-05 stays DEFERRED because its history half needs a store; four IDs the manifest marks differently are proposed as targets (CT-FLT-18, CT-FB-06, CT-VAL-11, CT-DET-01), each with a reason in LIFECYCLE.md section 10. The owner confirms or removes them in PR-01.

| ID | Status now | Contract | Plan text (shortened) | Class | Decision | Delivery |
|---|---|---|---|---|---|---|
| CT-LC-01 | DEFERRED | 7.5 | Every transition in 7.5 is reachable and recorded once with a reason code | Lifecycle engine | Target of KOS-MOTION-003 | PR-06 |
| CT-LC-02 | DEFERRED | 7.5 | Every pair of states not in 7.5 is refused (table-driven over all 25 pairs) | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-LC-03 | DEFERRED | 7.5 | A terminal state never changes; a late backend event after terminal is ignored and logged | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-LC-04 | DEFERRED | 7.2 | Acceptance does not imply `RUNNING`; `RUNNING` only on backend start confirmation | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-LC-05 | DEFERRED | 7.3, 15 | Rejected submissions have no `command_id` and no lifecycle, and appear in history | Lifecycle plus history | Stays DEFERRED: the history half needs a store (candidate KOS-MOTION-005) | - |
| CT-LC-06 | DEFERRED | 7.6 | Phases `NONE`, `DISPATCH_PENDING` and `TERMINATING` appear only on non-terminal commands and never as states; a terminal command always has phase `NON | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-VAL-11 | DEFERRED | 5.4, 5.5 | Position and velocity semantics: absolute position, signed velocity, zero velocity is not STOP or HOLD | Lifecycle engine | Target of KOS-MOTION-003 (reclassified in PR-01, owner to confirm) | PR-02 |
| CT-CFG-01 | DEFERRED | 3.2 | Submissions are rejected `CONFIG_NOT_ACTIVE` until a configuration validates | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-CFG-03 | DEFERRED | 3.3 | Accepted commands record the configuration version and digest | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-CFG-04 | DEFERRED | 3.3, 3.4 | A configuration update during execution leaves the active command bound to the old version | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-CFG-05 | DEFERRED | 3.4 | An incompatible update is refused while affected commands are active | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-CFG-06 | DEFERRED | 3.4 | Rollback is explicit, authorized and traceable | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-ID-01 | DEFERRED | 7.4 | Identical resubmission returns the original result with `idempotent_replay = true` and creates no second command | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-ID-02 | DEFERRED | 7.4 | Same ID, different content: `REQUEST_ID_CONFLICT` | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-ID-03 | DEFERRED | 7.4 | Same `client_request_id` from a different client is an independent request | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-ID-04 | DEFERRED | 7.3 | A replayed rejection returns the same rejection | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-ID-05 | DEFERRED | 7.4 | After retention expiry a reused ID is a new request | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-ARB-02 | DEFERRED | 9.2 | Commands on independent joints run concurrently up to backend capacity | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-ARB-03 | DEFERRED | 9.3 | `STOP` is accepted on a busy joint; the active command ends `CANCELLED(STOPPED)` after confirmation | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-ARB-04 | DEFERRED | 6.2 | `STOP` is not reported `COMPLETED` on receipt, only on backend confirmation | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-ARB-07 | DEFERRED | 9.5 | `HOLD` completes on engagement, joint enters `HOLDING`; a later movement ends the hold; `STOP` ends it | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-TMO-01 | DEFERRED | 10.3 | Deadline expiry before start gives `FAILED(DEADLINE_EXPIRED)` | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-TMO-02 | DEFERRED | 10.4, 10.6 | Execution timeout starts termination; confirmed termination gives `FAILED(EXECUTION_TIMEOUT)` | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-TMO-03 | DEFERRED | 10.6 | Unconfirmed termination within the bound gives `FAILED(TERMINATION_UNCONFIRMED)` and a faulted joint, never a "stopped" report | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-TMO-04 | DEFERRED | 10.5, 10.6 | Cancel with unconfirmed termination follows the same path | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-TMO-05 | DEFERRED | 10.3, 10.4 | Effective default deadline and timeout come from configuration and are recorded in the command record | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-TMO-06 | DEFERRED | 10.1 | Durations use the monotonic clock: wall-clock steps do not alter timeouts | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-TMO-07 | DEFERRED | 7.2 | Every accepted command reaches exactly one terminal state in every fault-injection scenario | Lifecycle engine | Target of KOS-MOTION-003 | PR-06 |
| CT-FB-02 | DEFERRED | 10.2, 17.2 | Both timestamps are recorded; an unsynchronized backend clock is flagged | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-FB-03 | DEFERRED | 11.2, 11.3 | Stale, invalid and missing feedback are reported distinctly and never as valid | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-FB-04 | DEFERRED | 11.5 | Required feedback lost during execution raises `FEEDBACK_LOST` and requests controlled stop; `HOLD` is not assumed | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FB-05 | DEFERRED | 11.5 | Non-required feedback loss gives `DEGRADED` and non-feedback commands continue | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-CMP-01 | DEFERRED | 12.2 | `SET_POSITION` completes only after tolerance and settling with valid fresh feedback | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-CMP-02 | DEFERRED | 12.1 | A command whose condition cannot be established is never `COMPLETED` | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-CMP-03 | DEFERRED | 12.2 | `SET_VELOCITY` with duration completes at expiry; without duration remains active | Lifecycle engine | Target of KOS-MOTION-003 | PR-02 |
| CT-FLT-01 | DEFERRED | 13.4 | A joint fault fails every non-terminal command on the joint with the fault code and faults the joint | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-02 | DEFERRED | 13.4 | A backend fault propagates to every affected joint and command record | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-03 | DEFERRED | 13.5 | The state after a fault is reported with `fault_ids`, last-known values and `is_current = false` as applicable | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-05 | DEFERRED | 13.4 | Interrupted commands do not resume after recovery | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-07 | DEFERRED | 13.3 | The joint state machine transitions exactly as in 13.3 (table-driven) | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-08 | DEFERRED | 13.1 | `FAILED` and `FAULTED` are independent: a command can fail with the joint `READY`, and a joint fault can occur with no active command | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-EV-01 | DEFERRED | 14.4 | Sequence numbers increase by one per stream; gaps are detectable | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-EV-02 | DEFERRED | 14.4 | Duplicate delivery is tolerated; status query is authoritative after loss | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-EV-03 | DEFERRED | 14.2 | Execution continues when no subscriber is attached or notification delivery fails | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-EV-04 | DEFERRED | 14.3 | Joint and backend changes appear in their own streams, not in command streams | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-HIS-01 | DEFERRED | 15 | History retains every field in 15.1, distinguishes rejected from accepted, and never overwrites | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-AUTH-01 | DEFERRED | 16.2 | Missing, invalid and expired assertions are rejected `UNAUTHENTICATED` | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-02 | DEFERRED | 16.3, 16.4 | Operation and target scope are both checked before acceptance; denials are audited | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-03 | DEFERRED | 16.4 | Internal components receive no implicit authorization | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-04 | DEFERRED | 16.3 | Authorization is evaluated by permission, not by component identity | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-BE-01 | OUT_OF_SCOPE | 17.2 | A conforming backend declares every capability in 17.2 | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-02 | DEFERRED | 17.3 | Motion refuses to dispatch operations the backend does not declare | Backend interface or simulator | Stays DEFERRED (candidate KOS-MOTION-004) | - |
| CT-BE-03 | OUT_OF_SCOPE | 4.1, 17 | No actuator-specific identifier appears in any public message or error | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-04 | OUT_OF_SCOPE | 17.4 | Backend start, feedback, termination confirmation and fault reports drive the lifecycle as specified | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-06 | OUT_OF_SCOPE | 17.1 | Swapping the simulator for another conforming backend changes no public behaviour | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-DET-01 | DEFERRED | 7, 10, 14 | The same ordered inputs under a simulated monotonic clock produce identical state, events and history | Lifecycle engine | Target of KOS-MOTION-003 (reclassified in PR-01, owner to confirm) | PR-06 |
| CT-DET-02 | DEFERRED | 3.3, 15 | Replay from history and configuration reproduces command outcomes | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-LC-07 | DEFERRED | 7.6 | Cancel or `STOP` of a `DISPATCH_PENDING` command enters `TERMINATING` and needs backend confirmation; a late start confirmation does not revive it | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-LC-08 | DEFERRED | 7.5, 7.6 | Cancel before dispatch completes without backend termination only when Motion confirms no dispatch occurred | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-ARB-09 | DEFERRED | 6.2, 8.6 | `STOP` on a `FAULTED` joint is accepted best effort; completion does not clear or hide the fault | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-ARB-10 | DEFERRED | 6.2 | `STOP` on an idle joint completes only on backend confirmation; no confirmation within the bound gives `FAILED(TERMINATION_UNCONFIRMED)` and control s | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-ARB-11 | DEFERRED | 6.2, 9.5 | `STOP` on a `HOLDING` joint releases the hold and completes on confirmation | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-ARB-13 | DEFERRED | 6.3 | Repeated `HOLD` on a `HOLDING` joint is accepted and completes on confirmation; a second `HOLD` while engagement is pending gives `TARGET_BUSY` | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-ARB-15 | DEFERRED | 9.5 | A movement command on a `HOLDING` joint releases the hold at start; a failed release ends the command `FAILED(BACKEND_REJECTED_DISPATCH)` | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-TMO-08 | DEFERRED | 10.6 | A fault during `TERMINATING`: the bound is not restarted, all causes are recorded, confirmed termination gives `FAILED` with the fault code, unconfirm | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-TMO-09 | DEFERRED | 10.3 | Deadline expiry on a `DISPATCH_PENDING` command terminates it first, then `FAILED(DEADLINE_EXPIRED)` | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-AUTH-06 | DEFERRED | 7.4, 8.4 | A stored result is returned only to the same authenticated client; other clients cannot learn that a request ID exists | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-FLT-09 | DEFERRED | 13.2, 13.3 | `DEGRADED` while a command is running preserves `control_state = ACTIVE`; clearing the degradation never reports `IDLE` | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-10 | DEFERRED | 13.3, 13.6 | After an unconfirmed termination `control_state` is `UNKNOWN`; `CLEAR_FAULT` is refused until a confirmed stop | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-11 | DEFERRED | 13.6 | `CLEAR_FAULT` clears exactly one fault; health returns to `READY` only when no other fault or degradation remains; a `fault_id` not on the target give | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-BE-07 | OUT_OF_SCOPE | 17.5 | Termination request accepted is not confirmation; a partial or unknown outcome is treated as unconfirmed; confirmation is bound to the backend referen | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-EV-05 | DEFERRED | 14.4 | Clients tolerate transports that are best effort: gaps are detected only where sequence continuity is provided, and state queries recover | Store, publisher, activation or status reporting | Stays DEFERRED (candidate KOS-MOTION-005) | - |
| CT-FLT-14 | DEFERRED | 7.8, 13.4 | A fault during a pending `CANCEL`: target `FAILED` with the first fault code, the `CANCEL` command `FAILED` with the same reason, joint `FAULTED`, con | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-15 | DEFERRED | 6.2, 10.6 | A confirmed `STOP` stays `COMPLETED(STOP_CONFIRMED)` when a fault is appended to its attempt; the fault stays recorded | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-16 | DEFERRED | 13.9 | Initial control state is `UNKNOWN`; a stale or ambiguous backend report does not establish a state; the backend becoming available alone does not leav | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-17 | DEFERRED | 13.6, 13.9 | Recovery path: confirmed `STOP` gives `IDLE`, then `CLEAR_FAULT`; without stop confirmation the joint stays `FAULTED` and `UNKNOWN` and `CLEAR_FAULT`  | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-18 | DEFERRED | 13.8 | Degradation permission does not make `SET_POSITION` or `HOLD` admissible without valid fresh feedback; `SET_VELOCITY` is accepted only with its comple | Lifecycle engine | Target of KOS-MOTION-003 (reclassified in PR-01, owner to confirm) | PR-05 |
| CT-TMO-10 | DEFERRED | 6.2, 10.6 | `STOP` during an outstanding termination joins it: cause appended, bound not restarted, no second backend request, own command ID; a `STOP` after a te | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-TMO-11 | DEFERRED | 10.6 | Reason selection: any `STOP_REQUESTED` gives `STOPPED`, otherwise `CANCEL_REQUESTED`; first recorded of timeout and deadline wins | Lifecycle engine | Target of KOS-MOTION-003 | PR-03 |
| CT-ARB-16 | DEFERRED | 2.4, 6.2 | Backend refusal of `STOP` before any attempt gives `FAILED(BACKEND_REJECTED_DISPATCH)` and not `TERMINATION_UNCONFIRMED`; backend loss on an active jo | Lifecycle engine | Target of KOS-MOTION-003 | PR-04 |
| CT-FB-06 | DEFERRED | 13.5 | `is_current` is true only when feedback is valid and fresh | Lifecycle engine | Target of KOS-MOTION-003 (reclassified in PR-01, owner to confirm) | PR-05 |
| CT-FLT-19 | DEFERRED | 13.9 | A newly connected joint is `UNKNOWN` and `READY` with no fault record; no fault is created and `CLEAR_FAULT` is not needed | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-20 | DEFERRED | 13.9 | Recovery of an `UNKNOWN` joint without a fault record by a fresh authoritative status report, and separately by a confirmed `STOP`; a stale, partial o | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-21 | DEFERRED | 13.9, 13.6 | A status report on a `FAULTED` and `UNKNOWN` joint can establish control state but never clears the fault; only `CLEAR_FAULT` does | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |
| CT-FLT-22 | DEFERRED | 13.4, 13.6 | `CLEAR_FAULT` race: accepted, then a new fault or termination begins before application; it ends `FAILED` with the new fault code and neither fault is | Lifecycle engine | Target of KOS-MOTION-003 | PR-05 |

## Totals by class

| Class | IDs |
|---|---|
| Lifecycle engine | 55 |
| Lifecycle plus history | 1 |
| Store, publisher, activation or status reporting | 18 |
| Core security interface | 5 |
| Backend interface or simulator | 6 |
| Sum | 85 |
