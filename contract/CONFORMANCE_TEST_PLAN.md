# Motion Contract Conformance Test Plan v0.1.0-draft

Task: KOS-MOTION-001. Status: DRAFT revision 4. This is a verification plan, not an implementation. No test in this plan exists as code, `make test-unit`, `make test-integration` and `make test-regression` stay NOT_IMPLEMENTED (exit 3) and are never counted as a pass. The runtime, simulator and test code belong to later tasks proposed through kritva-program.

Evidence from these tests is software evidence. It is never physical or safety validation (contract section 2.2).

## 0. Evidence classes

| Class | What it shows | Status now |
|---|---|---|
| Schema evidence | JSON Schema validation with positive and negative example documents (the CT-SCH group) | Executable now against the schemas in this directory |
| Static contract review | Consistency, completeness and traceability of the contract, error codes and schemas | Done by review and cross-check; not a test run |
| Runtime conformance | Behaviour of a runtime and backend: lifecycle, races, authorization order, termination, faults | Specification only; deferred until an implementation exists |
| Physical validation | Behaviour of real hardware and safety functions | Outside software acceptance; gated by V2-M6 and human safety review |

Passing schema validation does not show that any lifecycle, race or authorization test passes. Every test below other than CT-SCH is a specification for a future implementation and must never be reported as passed.

Test IDs are stable. "Contract" gives the section under test; "AC" the acceptance criterion it supports. Schema tests (CT-SCH) can be run against the schemas in this directory without any runtime.

## 1. Schema conformance (can run now)

| ID | Test | Contract | AC |
|---|---|---|---|
| CT-SCH-01 | Valid `SET_POSITION`, `SET_VELOCITY`, `STOP`, `HOLD`, `CANCEL`, `CLEAR_FAULT` envelopes validate | 5 | AC-002 |
| CT-SCH-02 | Missing `unit`, unknown `command_type`, unknown target type, extra fields fail | 4, 5 | AC-002 |
| CT-SCH-03 | `CANCEL` with a `target`, or `STOP` with parameters, fails | 5, 6 | AC-003 |
| CT-SCH-04 | Command status with a terminal state and a non-`NONE` phase fails; `TIMED_OUT` is not a state; five public states only | 7 | AC-001 |
| CT-SCH-05 | Joint state: `health_state = FAULTED` without `fault_ids` fails; `DEGRADED` without reasons fails; `ACTIVE` without `active_command_id` fails; stale feedback with `is_current = true` fails | 11, 13 | AC-003 |
| CT-SCH-06 | Event with a mismatched stream kind and event type fails | 14 | AC-003 |
| CT-SCH-07 | Accepted submission result without `command_id` fails; rejected one with `command_id` fails | 7 | AC-002 |
| CT-SCH-08 | `DISPATCH_PENDING` is valid only with state `ACCEPTED`; `TERMINATING` requires a termination record with outcome `PENDING` | 7.6, 10.6 | AC-003 |
| CT-SCH-09 | `CLEAR_FAULT` requires `target` and `fault_id`; `CANCEL` still forbids `target` | 5, 13.6 | AC-003 |

## 2. Lifecycle (AC-001)

| ID | Test | Contract |
|---|---|---|
| CT-LC-01 | Every transition in 7.5 is reachable and recorded once with a reason code | 7.5 |
| CT-LC-02 | Every pair of states not in 7.5 is refused (table-driven over all 25 pairs) | 7.5 |
| CT-LC-03 | A terminal state never changes; a late backend event after terminal is ignored and logged | 7.5 |
| CT-LC-04 | Acceptance does not imply `RUNNING`; `RUNNING` only on backend start confirmation | 7.2 |
| CT-LC-05 | Rejected submissions have no `command_id` and no lifecycle, and appear in history | 7.3, 15 |
| CT-LC-06 | Phases `NONE`, `DISPATCH_PENDING` and `TERMINATING` appear only on non-terminal commands and never as states; a terminal command always has phase `NONE` | 7.6 |

## 3. Admission, units and limits (AC-002)

| ID | Test | Contract |
|---|---|---|
| CT-VAL-01 | Each admission error code is produced by its defined cause | 8.4, ERROR_CODES |
| CT-VAL-02 | With several simultaneous faults in a request, the first failing step in 8.4 is reported (order test) | 8.4 |
| CT-VAL-03 | Position, velocity and acceleration at the limit are accepted; just beyond are rejected | 8.3 |
| CT-VAL-04 | Command constraints that widen a configured limit are rejected `INVALID_CONSTRAINT`; narrower ones are accepted and enforced | 8.2 |
| CT-VAL-05 | Backend capability limits narrower than configuration narrow the envelope; wider ones do not widen it | 3.5, 8.1 |
| CT-VAL-06 | No clamping: an out-of-limit command is never accepted with a modified value | 8.2 |
| CT-VAL-07 | NaN and infinities rejected `NON_FINITE_VALUE` | 1.3 |
| CT-VAL-08 | Unit mismatch rejected for each joint type | 5.3 |
| CT-VAL-09 | Reserved target types, `EXECUTE_TRAJECTORY` and non-default priority return `UNSUPPORTED_*` | 4.2, 5.6, 18 |
| CT-VAL-10 | Torque, current and PWM command types are unknown (`INVALID_SCHEMA`) | 5.7 |
| CT-VAL-11 | Position and velocity semantics: absolute position, signed velocity, zero velocity is not STOP or HOLD | 5.4, 5.5 |

## 4. Configuration (AD-022, AD-023)

| ID | Test | Contract |
|---|---|---|
| CT-CFG-01 | Submissions are rejected `CONFIG_NOT_ACTIVE` until a configuration validates | 3.2 |
| CT-CFG-02 | An incomplete or inconsistent configuration is not activated | 3.2 |
| CT-CFG-03 | Accepted commands record the configuration version and digest | 3.3 |
| CT-CFG-04 | A configuration update during execution leaves the active command bound to the old version | 3.3, 3.4 |
| CT-CFG-05 | An incompatible update is refused while affected commands are active | 3.4 |
| CT-CFG-06 | Rollback is explicit, authorized and traceable | 3.4 |

## 5. Idempotency (AD-015)

| ID | Test | Contract |
|---|---|---|
| CT-ID-01 | Identical resubmission returns the original result with `idempotent_replay = true` and creates no second command | 7.4 |
| CT-ID-02 | Same ID, different content: `REQUEST_ID_CONFLICT` | 7.4 |
| CT-ID-03 | Same `client_request_id` from a different client is an independent request | 7.4 |
| CT-ID-04 | A replayed rejection returns the same rejection | 7.3 |
| CT-ID-05 | After retention expiry a reused ID is a new request | 7.4 |

## 6. Arbitration and control operations (AC-003)

| ID | Test | Contract |
|---|---|---|
| CT-ARB-01 | A second movement command on a busy joint is rejected `TARGET_BUSY` with the conflicting `command_id`; no silent replacement | 9.1 |
| CT-ARB-02 | Commands on independent joints run concurrently up to backend capacity | 9.2 |
| CT-ARB-03 | `STOP` is accepted on a busy joint; the active command ends `CANCELLED(STOPPED)` after confirmation | 9.3 |
| CT-ARB-04 | `STOP` is not reported `COMPLETED` on receipt, only on backend confirmation | 6.2 |
| CT-ARB-05 | `CANCEL` of a terminal command is `COMMAND_ALREADY_TERMINAL`; of an unknown command `COMMAND_NOT_FOUND` | 6.1 |
| CT-ARB-06 | `HOLD` without valid fresh feedback is rejected; without backend support `BACKEND_CAPABILITY_UNSUPPORTED` | 6.3 |
| CT-ARB-07 | `HOLD` completes on engagement, joint enters `HOLDING`; a later movement ends the hold; `STOP` ends it | 9.5 |
| CT-ARB-08 | Priority never bypasses arbitration, limits or capability checks | 5.6 |

## 7. Timeouts and termination (AC-003)

| ID | Test | Contract |
|---|---|---|
| CT-TMO-01 | Deadline expiry before start gives `FAILED(DEADLINE_EXPIRED)` | 10.3 |
| CT-TMO-02 | Execution timeout starts termination; confirmed termination gives `FAILED(EXECUTION_TIMEOUT)` | 10.4, 10.6 |
| CT-TMO-03 | Unconfirmed termination within the bound gives `FAILED(TERMINATION_UNCONFIRMED)` and a faulted joint, never a "stopped" report | 10.6 |
| CT-TMO-04 | Cancel with unconfirmed termination follows the same path | 10.5, 10.6 |
| CT-TMO-05 | Effective default deadline and timeout come from configuration and are recorded in the command record | 10.3, 10.4 |
| CT-TMO-06 | Durations use the monotonic clock: wall-clock steps do not alter timeouts | 10.1 |
| CT-TMO-07 | Every accepted command reaches exactly one terminal state in every fault-injection scenario | 7.2 |

## 8. Feedback and completion

| ID | Test | Contract |
|---|---|---|
| CT-FB-01 | Freshness is evaluated on Motion receipt time, not on backend timestamps | 10.1, 10.2 |
| CT-FB-02 | Both timestamps are recorded; an unsynchronized backend clock is flagged | 10.2, 17.2 |
| CT-FB-03 | Stale, invalid and missing feedback are reported distinctly and never as valid | 11.2, 11.3 |
| CT-FB-04 | Required feedback lost during execution raises `FEEDBACK_LOST` and requests controlled stop; `HOLD` is not assumed | 11.5 |
| CT-FB-05 | Non-required feedback loss gives `DEGRADED` and non-feedback commands continue | 11.5 |
| CT-CMP-01 | `SET_POSITION` completes only after tolerance and settling with valid fresh feedback | 12.2 |
| CT-CMP-02 | A command whose condition cannot be established is never `COMPLETED` | 12.1 |
| CT-CMP-03 | `SET_VELOCITY` with duration completes at expiry; without duration remains active | 12.2 |

## 9. Faults and joint state (AC-003)

| ID | Test | Contract |
|---|---|---|
| CT-FLT-01 | A joint fault fails every non-terminal command on the joint with the fault code and faults the joint | 13.4 |
| CT-FLT-02 | A backend fault propagates to every affected joint and command record | 13.4 |
| CT-FLT-03 | The state after a fault is reported with `fault_ids`, last-known values and `is_current = false` as applicable | 13.5 |
| CT-FLT-04 | New commands on a faulted joint are `TARGET_FAULTED` | 13.4 |
| CT-FLT-05 | Interrupted commands do not resume after recovery | 13.4 |
| CT-FLT-06 | `CLEAR_FAULT` requires permission, a resolved cause and no active command; `HUMAN_REQUIRED` faults need the human attribute | 13.6 |
| CT-FLT-07 | The joint state machine transitions exactly as in 13.3 (table-driven) | 13.3 |
| CT-FLT-08 | `FAILED` and `FAULTED` are independent: a command can fail with the joint `READY`, and a joint fault can occur with no active command | 13.1 |

## 10. Events, history and authorization

| ID | Test | Contract |
|---|---|---|
| CT-EV-01 | Sequence numbers increase by one per stream; gaps are detectable | 14.4 |
| CT-EV-02 | Duplicate delivery is tolerated; status query is authoritative after loss | 14.4 |
| CT-EV-03 | Execution continues when no subscriber is attached or notification delivery fails | 14.2 |
| CT-EV-04 | Joint and backend changes appear in their own streams, not in command streams | 14.3 |
| CT-HIS-01 | History retains every field in 15.1, distinguishes rejected from accepted, and never overwrites | 15 |
| CT-AUTH-01 | Missing, invalid and expired assertions are rejected `UNAUTHENTICATED` | 16.2 |
| CT-AUTH-02 | Operation and target scope are both checked before acceptance; denials are audited | 16.3, 16.4 |
| CT-AUTH-03 | Internal components receive no implicit authorization | 16.4 |
| CT-AUTH-04 | Authorization is evaluated by permission, not by component identity | 16.3 |

## 11. Backend interface (AC-005)

| ID | Test | Contract |
|---|---|---|
| CT-BE-01 | A conforming backend declares every capability in 17.2 | 17.2 |
| CT-BE-02 | Motion refuses to dispatch operations the backend does not declare | 17.3 |
| CT-BE-03 | No actuator-specific identifier appears in any public message or error | 4.1, 17 |
| CT-BE-04 | Backend start, feedback, termination confirmation and fault reports drive the lifecycle as specified | 17.4 |
| CT-BE-05 | A backend cannot widen configured limits | 3.5 |
| CT-BE-06 | Swapping the simulator for another conforming backend changes no public behaviour | 17.1 |

## 12. Determinism

| ID | Test | Contract |
|---|---|---|
| CT-DET-01 | The same ordered inputs under a simulated monotonic clock produce identical state, events and history | 7, 10, 14 |
| CT-DET-02 | Replay from history and configuration reproduces command outcomes | 3.3, 15 |

## 12a. Added in revisions 2 to 4 (from the cross-check reviews)

| ID | Test | Contract | AC |
|---|---|---|---|
| CT-LC-07 | Cancel or `STOP` of a `DISPATCH_PENDING` command enters `TERMINATING` and needs backend confirmation; a late start confirmation does not revive it | 7.6 | AC-003 |
| CT-LC-08 | Cancel before dispatch completes without backend termination only when Motion confirms no dispatch occurred | 7.5, 7.6 | AC-003 |
| CT-ARB-09 | `STOP` on a `FAULTED` joint is accepted best effort; completion does not clear or hide the fault | 6.2, 8.6 | AC-003 |
| CT-ARB-10 | `STOP` on an idle joint completes only on backend confirmation; no confirmation within the bound gives `FAILED(TERMINATION_UNCONFIRMED)` and control state `UNKNOWN` | 6.2 | AC-003 |
| CT-ARB-11 | `STOP` on a `HOLDING` joint releases the hold and completes on confirmation | 6.2, 9.5 | AC-003 |
| CT-ARB-12 | Movement-slot table (9.1) holds for every operation, including that `STOP`, `CANCEL`, `CLEAR_FAULT` and queries never produce `TARGET_BUSY` | 9.1 | AC-003 |
| CT-ARB-13 | Repeated `HOLD` on a `HOLDING` joint is accepted and completes on confirmation; a second `HOLD` while engagement is pending gives `TARGET_BUSY` | 6.3 | AC-003 |
| CT-ARB-14 | `CANCEL` eligibility matrix: allowed for movement and pending `HOLD`; `COMMAND_NOT_CANCELLABLE` for `STOP`, `CLEAR_FAULT`, `CANCEL`, engaged `HOLD` | 6.1 | AC-003 |
| CT-ARB-15 | A movement command on a `HOLDING` joint releases the hold at start; a failed release ends the command `FAILED(BACKEND_REJECTED_DISPATCH)` | 9.5 | AC-003 |
| CT-TMO-08 | A fault during `TERMINATING`: the bound is not restarted, all causes are recorded, confirmed termination gives `FAILED` with the fault code, unconfirmed gives `FAILED(TERMINATION_UNCONFIRMED)` | 10.6 | AC-003 |
| CT-TMO-09 | Deadline expiry on a `DISPATCH_PENDING` command terminates it first, then `FAILED(DEADLINE_EXPIRED)` | 10.3 | AC-003 |
| CT-AUTH-05 | Authorization precedes idempotency replay: a client whose permission was revoked gets `PERMISSION_DENIED`, not the stored result | 8.4 | AC-008 (proposed) |
| CT-AUTH-06 | A stored result is returned only to the same authenticated client; other clients cannot learn that a request ID exists | 7.4, 8.4 | AC-008 (proposed) |
| CT-FLT-09 | `DEGRADED` while a command is running preserves `control_state = ACTIVE`; clearing the degradation never reports `IDLE` | 13.2, 13.3 | AC-003 |
| CT-FLT-10 | After an unconfirmed termination `control_state` is `UNKNOWN`; `CLEAR_FAULT` is refused until a confirmed stop | 13.3, 13.6 | AC-003 |
| CT-FLT-11 | `CLEAR_FAULT` clears exactly one fault; health returns to `READY` only when no other fault or degradation remains; a `fault_id` not on the target gives `FAULT_NOT_FOUND` | 13.6 | AC-003 |
| CT-FLT-12 | The exemption matrix in 8.6 holds for `FAULTED` and `DEGRADED` joints | 8.6 | AC-003 |
| CT-FLT-13 | A degradation reason with no policy permits no movement; queries and `STOP` stay available | 13.8 | AC-003 |
| CT-CFG-07 | Unknown policy values, a policy the backend cannot satisfy (for example `STOP_AND_FAULT` without controlled stop) and a continuous joint with position mode all block activation | 3.6, 3.7 | AC-002 |
| CT-VAL-12 | `SET_POSITION` on a continuous joint is rejected `UNSUPPORTED_MODE` | 3.7, 8.3 | AC-002 |
| CT-VAL-13 | Backend numerical limits take part in the intersection; a backend declares explicitly when it has none | 8.3, 17.2 | AC-002 |
| CT-BE-07 | Termination request accepted is not confirmation; a partial or unknown outcome is treated as unconfirmed; confirmation is bound to the backend reference and target | 17.5 | AC-005 |
| CT-EV-05 | Clients tolerate transports that are best effort: gaps are detected only where sequence continuity is provided, and state queries recover | 14.4 | AC-003 |
| CT-FLT-14 | A fault during a pending `CANCEL`: target `FAILED` with the first fault code, the `CANCEL` command `FAILED` with the same reason, joint `FAULTED`, control state per confirmation | 7.8, 13.4 | AC-003 |
| CT-FLT-15 | A confirmed `STOP` stays `COMPLETED(STOP_CONFIRMED)` when a fault is appended to its attempt; the fault stays recorded | 6.2, 10.6 | AC-003 |
| CT-FLT-16 | Initial control state is `UNKNOWN`; a stale or ambiguous backend report does not establish a state; the backend becoming available alone does not leave `UNKNOWN` | 13.9 | AC-003 |
| CT-FLT-17 | Recovery path: confirmed `STOP` gives `IDLE`, then `CLEAR_FAULT`; without stop confirmation the joint stays `FAULTED` and `UNKNOWN` and `CLEAR_FAULT` is not an override | 13.6, 13.9 | AC-003 |
| CT-FLT-18 | Degradation permission does not make `SET_POSITION` or `HOLD` admissible without valid fresh feedback; `SET_VELOCITY` is accepted only with its completion evidence | 13.8 | AC-003 |
| CT-CFG-08 | Activation fails for a policy listing `SET_POSITION` or `HOLD` under `FEEDBACK_OPTIONAL_UNAVAILABLE` | 3.6, 13.8 | AC-002 |
| CT-TMO-10 | `STOP` during an outstanding termination joins it: cause appended, bound not restarted, no second backend request, own command ID; a `STOP` after a terminal outcome starts a new attempt and leaves the old record unchanged | 6.2, 10.6 | AC-003 |
| CT-TMO-11 | Reason selection: any `STOP_REQUESTED` gives `STOPPED`, otherwise `CANCEL_REQUESTED`; first recorded of timeout and deadline wins | 10.6 | AC-003 |
| CT-ARB-16 | Backend refusal of `STOP` before any attempt gives `FAILED(BACKEND_REJECTED_DISPATCH)` and not `TERMINATION_UNCONFIRMED`; backend loss on an active joint sets `UNKNOWN` | 2.4, 6.2 | AC-003 |
| CT-FB-06 | `is_current` is true only when feedback is valid and fresh | 13.5 | AC-003 |
| CT-VAL-14 | `SET_POSITION`, `SET_VELOCITY` and `HOLD` on a joint with `control_state = UNKNOWN` and `health_state = READY` are rejected `TARGET_STATE_UNKNOWN`; the check precedes the health checks; `STOP`, `CANCEL` and queries are accepted | 8.4, 8.6 | AC-003 |
| CT-FLT-19 | A newly connected joint is `UNKNOWN` and `READY` with no fault record; no fault is created and `CLEAR_FAULT` is not needed | 13.9 | AC-003 |
| CT-FLT-20 | Recovery of an `UNKNOWN` joint without a fault record by a fresh authoritative status report, and separately by a confirmed `STOP`; a stale, partial or ambiguous report leaves it `UNKNOWN` | 13.9 | AC-003 |
| CT-FLT-21 | A status report on a `FAULTED` and `UNKNOWN` joint can establish control state but never clears the fault; only `CLEAR_FAULT` does | 13.9, 13.6 | AC-003 |
| CT-FLT-22 | `CLEAR_FAULT` race: accepted, then a new fault or termination begins before application; it ends `FAILED` with the new fault code and neither fault is cleared | 13.4, 13.6 | AC-003 |
| CT-FLT-23 | `CLEAR_FAULT` referencing a joint with no fault record or an unknown `fault_id` is rejected `FAULT_NOT_FOUND` | 13.6 | AC-003 |

## 13. Traceability

| AC | Tests |
|---|---|
| AC-001 | CT-SCH-04, CT-LC-01 to CT-LC-06 |
| AC-002 | CT-SCH-01, 02, 07, CT-VAL-01 to 14, CT-CFG-01 to 08 |
| AC-003 | CT-SCH-03, 05, 06, 08, 09, CT-LC-07, 08, CT-ARB-01 to 16, CT-TMO-01 to 11, CT-FB-01 to 06, CT-CMP-01 to 03, CT-FLT-01 to 23, CT-EV-01 to 05 |
| AC-004 | Review of contract sections 2.2 and 17.7 by the safety reviewer; no automated test can show safety |
| AC-005 | CT-BE-01 to 07, CT-AUTH-03 (no transport or identity-system details in the contract) |

Tests for idempotency, authorization and history (CT-ID, CT-AUTH, CT-HIS, CT-EV) support requirements proposed as additional acceptance criteria in `tasks/KOS-MOTION-001/AC_AMENDMENT_PROPOSALS.md`.
