# KOS-MOTION-003: Lifecycle design (PR-01)

Status: PROPOSED for owner review (2026-11-07). No implementation exists. Implementation pull requests (PR-02 to PR-06) start only after the owner approves this document.

This document is derived from [contract/MOTION_CONTRACT.md](../../contract/MOTION_CONTRACT.md) (v0.1.0-draft, normative), [contract/ERROR_CODES.md](../../contract/ERROR_CODES.md) and [contract/CONFORMANCE_TEST_PLAN.md](../../contract/CONFORMANCE_TEST_PLAN.md). It adds no state, phase, reason code or event name. Where the contract is silent or ambiguous the point is listed in section 9 as an interpretation to confirm, not decided silently. Where this document and the contract differ, the contract wins and this document is wrong.

Approval of this document authorizes implementation. It does not authorize any change to the contract.

## 1. What the engine is

A pure, in-memory, deterministic reference implementation of the Motion lifecycle, termination and fault semantics (contract 6, 7, 9, 10, 11.5, 12, 13) in the Python standard library. It decides what the contract says should happen when it is given ordered inputs. It does not talk to a backend, store anything, publish anything or read the system clock.

Software evidence only (contract 2.2): passing tests never show that anything stopped, held or recovered physically. The engine reports a condition as confirmed only when a supplied backend input says so (contract 2.4).

## 2. Ownership boundary

| Owned by | What |
|---|---|
| The engine | Command lifecycle states and phases, the termination record, arbitration of the movement slot, STOP, HOLD, CANCEL and CLEAR_FAULT behaviour, joint control and health state, fault records, deadline, execution-timeout and termination-bound decisions, completion decisions from supplied feedback, the ordered output records |
| The caller (a test, later a backend adapter) | Backend inputs, feedback samples, the monotonic clock reading, the admitted command and its context |
| The abstract execution port (a protocol with no implementation here) | `dispatch`, `request_termination`, `request_hold` and `release_hold` as outputs of the engine (contract 17.4). A later task implements it |
| The backend (a later task) | Starting execution, confirming termination, reporting health and feedback |
| Not built here | Stores, publishers and subscriptions, history, configuration activation, idempotency, authentication and authorization, the backend interface implementation, simulators, hardware |

The engine never imports a backend or simulator module and holds no backend-specific state (no motor, power or torque state). A backend-specific fact reaches the engine only as one of the inputs in section 5.

## 3. Command lifecycle (contract 7.5)

States: `ACCEPTED`, `RUNNING`, `COMPLETED`, `CANCELLED`, `FAILED`. Terminal: `COMPLETED`, `CANCELLED`, `FAILED`. A terminal state never changes. Every accepted command, including `STOP`, `HOLD`, `CANCEL` and `CLEAR_FAULT` (7.8), reaches exactly one terminal state.

| # | From | To | Trigger (contract) |
|---|---|---|---|
| T1 | (admission) | `ACCEPTED` | admission passed (7.1) |
| T2 | `ACCEPTED` | `RUNNING` | backend start confirmation `execution_started` (7.5) |
| T3 | `ACCEPTED`, phase `NONE`, not dispatched | `CANCELLED` | cancellation or `STOP`, and Motion confirms no dispatch occurred (7.6) |
| T4 | `ACCEPTED` | `FAILED` | `DEADLINE_EXPIRED` after any dispatched start attempt is terminated, backend rejected dispatch, joint or backend fault, or unconfirmed termination (7.5, 10.3, 10.6) |
| T5 | `RUNNING` | `COMPLETED` | completion condition met (12.2) |
| T6 | `RUNNING` | `CANCELLED` | cancellation or `STOP` requested and termination confirmed (10.6) |
| T7 | `RUNNING` | `FAILED` | `EXECUTION_TIMEOUT` with termination confirmed, `TERMINATION_UNCONFIRMED`, joint or backend fault (7.5, 10.4, 10.6) |

Any other pair is invalid and is refused (CT-LC-02 covers all 25 ordered pairs). Each transition is recorded once with a UTC audit timestamp and a `reason_code` from `ERROR_CODES.md` section 2. A rejected submission is not an accepted command and has no lifecycle (7.3).

## 4. Phases (contract 7.6)

A phase is not a state. Only non-terminal commands have a phase; a terminal command has phase `NONE`.

| Phase | Applies to | Meaning |
|---|---|---|
| `NONE` | `ACCEPTED` (not dispatched), `RUNNING` (no termination outstanding) | |
| `DISPATCH_PENDING` | `ACCEPTED` | dispatched, start or rejection not yet confirmed |
| `TERMINATING` | `ACCEPTED`, `RUNNING` | a termination request is outstanding |

| Situation | Rule |
|---|---|
| Cancel or `STOP` before dispatch | completes without backend termination once Motion confirms no dispatch occurred (T3) |
| Cancel or `STOP` while `DISPATCH_PENDING` | moves to `TERMINATING`, needs backend termination confirmation |
| `execution_started` arrives for a command that is `TERMINATING` or terminal | ignored and recorded; it never revives the command and does not change the phase (7.6, 17.5) |
| A late backend input for a terminal command | ignored and recorded (CT-LC-03) |

## 5. Inputs and outputs (vocabulary)

Names are the contract's. The engine's own function signatures are implementation names, not contract names (interpretation I-1).

Inputs the engine accepts, each carrying the caller's monotonic clock reading:

| Input | Source in the contract |
|---|---|
| An admitted command (`SET_POSITION`, `SET_VELOCITY`, `HOLD`, `STOP`, `CANCEL`, `CLEAR_FAULT`) with the effective deadline, execution timeout and configuration reference | 7.1, 8.4 |
| `execution_started(backend_reference)`, `execution_rejected(backend_reference, reason)` | 17.4, 17.5 |
| `termination_request_accepted`, `termination_confirmed(backend_reference)` | 17.5 |
| Backend health report (`AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `FAULTED`) and backend faults | 13.1, 17.2 |
| A feedback record (position, velocity, backend timestamp with clock domain, monotonic receipt time, validity) | 11.1 |
| An authoritative backend status report for a joint | 13.9 |
| A clock reading with no other input (time passing) | 10.1 |

Outputs, in order, as plain data (nothing is delivered anywhere):

| Output | Source |
|---|---|
| Backend requests: `dispatch`, `request_termination(backend_reference, cause)`, `request_hold`, `release_hold` | 17.4 |
| Command records: state, phase, termination record, `reason_code`, effective timeouts, timestamps | 7.5, 10.6, 14.1 |
| Joint records: `control_state`, `health_state`, `fault_ids`, feedback status, last valid values, `is_current` | 13.2, 13.5 |
| Event records of the types in 14.3, without `event_id` or sequence number | 14.3 |
| Ignored-input records (late or duplicate input) | 7.6, CT-LC-03 |
| `termination_unconfirmed` decided by the engine when the bound expires (the engine, not the backend, determines it) | 17.5 |

Event identifiers, sequence numbers, delivery, history and idempotency belong to later tasks.

## 6. Termination record (contract 10.5, 10.6)

Causes: `CANCEL_REQUESTED`, `STOP_REQUESTED`, `EXECUTION_TIMEOUT`, `DEADLINE_EXPIRED`, `FAULT`. Outcome: `PENDING`, `CONFIRMED`, `UNCONFIRMED`.

1. The first request starts the bounded wait of `termination_confirm_timeout_ms` (finite). Later causes, including faults, are appended and never restart or extend the bound. No second backend termination request is sent.
2. On confirmation: a `FAULT` cause gives `FAILED` with the first fault code; otherwise `EXECUTION_TIMEOUT` or `DEADLINE_EXPIRED` gives `FAILED` with the one recorded first; only when every cause is `CANCEL_REQUESTED` or `STOP_REQUESTED` the command ends `CANCELLED`, reason `STOPPED` if any `STOP_REQUESTED` is present, else `CANCEL_REQUESTED`. Causes are ordered by the time the engine appended them.
3. On expiry of the bound: `FAILED(TERMINATION_UNCONFIRMED)`, the joint health becomes `FAULTED` with that fault, control state `UNKNOWN`, and the engine never reports the joint as stopped.
4. A `STOP` arriving while an attempt is outstanding on the same joint joins it (6.2); after the attempt reached `CONFIRMED` or `UNCONFIRMED`, a later `STOP` starts a new attempt and never changes the earlier record.
5. `STOP` and `CANCEL` own no execution. They have their own lifecycle and derive their outcomes from the referenced attempt (13.4): `STOP` ends `COMPLETED(STOP_CONFIRMED)` on a confirmed shared attempt even if the joint is or becomes `FAULTED`; `CANCEL` ends `COMPLETED(CANCEL_EFFECTIVE)` when its target reaches `CANCELLED`, otherwise `FAILED` with its target's reason.

## 7. Joint state and faults (contract 13)

Two independent dimensions (13.2): `control_state` is `IDLE`, `ACTIVE`, `HOLDING` or `UNKNOWN`; `health_state` is `READY`, `DEGRADED` or `FAULTED`. `FAILED` is a command outcome and `FAULTED` a joint health; they are separate models and are never merged (13.1). Fault classes: command errors (admission), joint faults (`FEEDBACK_LOST`, `TRACKING_ERROR`, `JOINT_LIMIT_VIOLATION`, `TERMINATION_UNCONFIRMED`), backend faults (`BACKEND_UNAVAILABLE`, `BACKEND_COMMUNICATION_LOSS`, `BACKEND_EXECUTION_FAILURE`).

| Rule | Contract |
|---|---|
| Initial state: control `UNKNOWN`, health `READY`, no fault record; a stale, partial or ambiguous report leaves `UNKNOWN`; the backend becoming available alone does not leave it | 13.9 (1 to 3) |
| Control transitions: `IDLE` to `ACTIVE` on start; `ACTIVE` to `IDLE` on confirmed stop or completion with no hold; `IDLE` to `HOLDING` on confirmed hold; `HOLDING` to `ACTIVE` on a movement start or to `IDLE` after a confirmed stop; any to `UNKNOWN` when the condition cannot be established; `UNKNOWN` to `IDLE` only on a confirmed stop or a fresh authoritative report that meets 13.9(2) | 13.3 |
| Health transitions: `READY` to `DEGRADED` and back preserves control state; any to `FAULTED` on a joint or backend fault; `FAULTED` to `READY` only by `CLEAR_FAULT`, or to `DEGRADED` if a degradation condition remains | 13.3 |
| On a joint or backend fault: request a stop if supported and not confirmed, append `FAULT` to the termination record of every non-terminal movement command and pending `HOLD` on each affected joint (starting an attempt if none is outstanding), set health `FAULTED`, emit the fault event, and let admission reject ordinary motion `TARGET_FAULTED` | 13.4 |
| Interrupted commands never resume after recovery. A backend fault creates a joint fault record on each affected joint; the backend becoming healthy ends the backend fault but does not clear joint fault records | 13.4 |
| State after a fault reports `fault_ids`, last valid values with `last_valid_feedback_at` and `is_current` (true only when the feedback is valid and fresh) | 13.5 |
| `CLEAR_FAULT` clears one identified fault; preconditions evaluated at admission and again atomically at application; a new fault or termination in the window ends it `FAILED` with the new fault code and clears neither; health returns to `READY` only when no other fault or degradation remains | 13.6 |
| Recovery of an `UNKNOWN` joint with a fault: backend available, authorized `STOP` confirmed to `IDLE`, then `CLEAR_FAULT`. If a stop cannot be confirmed the joint stays `FAULTED` and `UNKNOWN`. A status report alone never clears a fault | 13.9 (4 to 6) |
| Degradation: `DEGRADED` while a command runs preserves `control_state`; live preconditions still apply to every operation a policy permits | 13.8 |
| Loss of required feedback during execution raises `FEEDBACK_LOST` and requests a controlled stop; loss of non-required feedback gives `DEGRADED` (`FEEDBACK_OPTIONAL_UNAVAILABLE`) | 11.5 |

## 8. Arbitration, STOP, HOLD, completion

| Topic | Rule |
|---|---|
| Movement slot | exclusive per joint; held by `SET_POSITION`/`SET_VELOCITY` from acceptance to terminal and by a pending `HOLD`; not held by `STOP`, `CANCEL`, `CLEAR_FAULT`, queries or a confirmed `HOLDING` (9.1). A busy joint rejects with `TARGET_BUSY` (admission, already built in KOS-MOTION-002); no silent replacement, preemption or queuing |
| Independent joints | may run concurrently up to backend capacity (9.2) |
| `STOP` | never `TARGET_BUSY`; terminates an active command with cause `STOP_REQUESTED` and ends it `CANCELLED(STOPPED)` after confirmation (9.3); on `HOLDING` releases the hold; on an idle joint completes only on backend confirmation; on a `FAULTED` joint is best effort and never clears or hides the fault (6.2). Receipt is never success |
| `CANCEL` | only for `SET_POSITION`, `SET_VELOCITY` and a `HOLD` pending engagement; not for a confirmed hold, `STOP`, `CLEAR_FAULT` or `CANCEL` (6.1) |
| `HOLD` | completes on engagement, joint becomes `HOLDING`; a repeated `HOLD` on `HOLDING` completes on confirmation that the hold remains; a second `HOLD` while engagement is pending is `TARGET_BUSY` (6.3). A movement command on a `HOLDING` joint releases the hold at start; a failed release ends it `FAILED(BACKEND_REJECTED_DISPATCH)` (9.5) |
| Completion | only from supplied evidence, never from commanded values (12.1): `SET_POSITION` after valid fresh position stays within tolerance for the settling duration; `SET_VELOCITY` with `duration_ms` at expiry on the monotonic clock, without duration never; `STOP`, `HOLD` on backend confirmation; `CANCEL` when the target is `CANCELLED`; `CLEAR_FAULT` when cleared |
| Time | durations use the injected monotonic reading only; audit timestamps are separate inputs; a wall-clock step cannot change a timeout (10.1) |

## 9. Invariants (tested, including by a fixed-seed property test in PR-06)

| ID | Invariant |
|---|---|
| INV-01 | A terminal state never changes; a late input is ignored and recorded |
| INV-02 | Every accepted command reaches exactly one terminal state in every scenario of the test set |
| INV-03 | Only transitions of table T1 to T7 occur; each is recorded once with a timestamp and reason code |
| INV-04 | A phase exists only on a non-terminal command and a terminal command has phase `NONE` |
| INV-05 | A late `execution_started` never revives a `TERMINATING` or terminal command |
| INV-06 | The termination bound is started once and never restarted, extended or duplicated by a later cause |
| INV-07 | At most one backend termination request per attempt |
| INV-08 | A condition is never reported stopped, completed, engaged or recovered without the confirming input (2.4) |
| INV-09 | `control_state` is `UNKNOWN` until confirmed; `UNKNOWN` leaves only by a confirmed stop or a qualifying status report |
| INV-10 | A fault is never cleared except by a successful `CLEAR_FAULT` of that fault |
| INV-11 | `FAILED` and `FAULTED` are independent: neither implies the other |
| INV-12 | The same ordered inputs and clock readings give the same outputs, records and order |
| INV-13 | The engine reads no system clock and has no I/O and no backend-specific state |

## 10. Interpretations and open points (to confirm in this review)

The contract does not settle these. Each is recorded, and the owner confirms or changes it in PR-01. None changes the contract. A point that needs a contract change becomes a separate clarification.

| ID | Point | Proposal |
|---|---|---|
| I-1 | Names of the engine's functions and inputs | implementation names; semantics use only contract names and codes |
| I-2 | Does the engine run admission? | it builds the `AdmissionContext` from its own state and calls the KOS-MOTION-002 `admit()` (no second copy of the rules); an accepted result creates the command |
| I-3 | What `RUNNING` means for `STOP`, `CANCEL`, `CLEAR_FAULT` (7.8 says they have the same public lifecycle) | `RUNNING` when the engine has issued the request that carries out the operation (termination request accepted, hold released, clearance applying) and `COMPLETED` on the confirmation of 12.2; `CLEAR_FAULT` applies atomically so it passes through `RUNNING` at the instant of application |
| I-4 | Order at one clock reading | supplied backend inputs are applied first, then timer expiries (deadline, execution timeout, termination bound, duration, settling), then completion checks; an `execution_started` and a deadline at the same reading therefore starts the command |
| I-5 | Settling for `SET_POSITION` (12.2) | the window runs over consecutive valid fresh samples within `position_tolerance`; a sample outside tolerance, an invalid or stale sample, or a gap larger than `max_feedback_age_ms` restarts it; tolerance and duration come from supplied configuration |
| I-6 | `STOP` with nothing active | the engine opens its own attempt with cause `STOP_REQUESTED` and the same bound, and completes on confirmation (6.2) |
| I-7 | A fault when the backend cannot accept a termination request | the command ends `FAILED(TERMINATION_UNCONFIRMED)` at the bound; the contract says request "if supported" (13.4) and is not explicit about the unsupported case |
| I-8 | CT-LC-05 | stays DEFERRED: "appears in history" needs a store; only the no-`command_id` and no-lifecycle half could be tested, and a half is not reported as the ID |
| I-9 | CT-TMO-07 "every fault-injection scenario" | means the scenario set defined and listed in PR-06, not every possible fault |
| I-10 | CT-FLT-18, CT-FB-06, CT-VAL-11, CT-DET-01 (manifest: DEFERRED for other reasons) | proposed as targets: FLT-18 only the runtime half (`SET_VELOCITY` never complete without evidence), FB-06 `is_current` computed by the engine, VAL-11 the dispatch request carries absolute position and signed velocity unchanged and a zero velocity is a `SET_VELOCITY`, DET-01 determinism under the injected clock. If the owner rejects one it stays DEFERRED with its current reason |
| I-11 | Events | returned as ordered data without `event_id` or sequence number; publishing, numbering and delivery (14.3, 14.4) are KOS-MOTION-005 |
| I-12 | Feedback clock | freshness and settling use the engine's own monotonic receipt time only; the backend timestamp is recorded and never compared with it; `clock_unsynchronized` is true unless the backend declared its clock synchronized (an undeclared status fails closed) (PR-02) |
| I-13 | Samples before the confirmed start | a feedback sample received before `RUNNING` is not evidence for `SET_POSITION`; the settling window starts only from samples received while the command is `RUNNING` (PR-02) |
| I-14 | Reason codes on transitions | a transition into a terminal state needs a reason code of that state (ERROR_CODES section 2); a transition into a non-terminal state carries none; anything else raises `IllegalTransition` (PR-02) |
| I-15 | When is a command "not dispatched" (7.6)? | `submit` issues the dispatch request and sets phase `DISPATCH_PENDING`, as in PR-02. `submit(..., defer_dispatch=True)` accepts the command without issuing it (phase `NONE`), and `dispatch(command_id)` issues it later. Only the engine's own record of "no dispatch issued" lets a cancellation complete without a backend termination (PR-03) |
| I-16 | Cancellation before the CANCEL and STOP commands exist | `terminate(command_id, cause)` with cause `CANCEL_REQUESTED` or `STOP_REQUESTED` is the engine-level entry for one `SET_POSITION` or `SET_VELOCITY` command; the `CANCEL` and `STOP` commands of PR-04 will call it. Not dispatched: `CANCELLED` at once, no backend request. Dispatched: phase `TERMINATING`, one request, the bound starts. Later causes only append to the record (PR-03) |
| I-17 | Timers at one reading | a limit is reached when the elapsed monotonic time is at least the limit; the passes run deadline, execution timeout, termination bound, duration, over commands in acceptance order; backend inputs for the same reading must be applied by the caller before `tick` (so an `execution_started` or `termination_confirmed` at the limit wins). The deadline applies only until the start is confirmed and the execution timeout only from it (PR-03) |
| I-18 | A command with an outstanding termination | is not completed by `duration_ms` or by settling feedback: the attempt decides its end (the contract is silent; this keeps one cause of end per command) (PR-03) |
| I-19 | Unconfirmed termination fault | the joint gets a fault record with an engine-assigned `fault_id` (`fault-N`), health `FAULTED`, control `UNKNOWN`, a `JOINT_FAULT_RAISED` event, and keeps it until `CLEAR_FAULT` exists (PR-05); `termination_request_accepted` is recorded and never confirms; a timeout or deadline cause is appended once to an attempt already outstanding. A deadline and an execution timeout cannot both occur on one command in this version (the deadline stops at the start), so "the one recorded first" is tested on the cause-selection function |

Possible contract findings (not changed by this task): the I-3 gap in 7.8, the I-7 gap in 13.4, and the three findings already recorded in the task record of KOS-MOTION-002.

## 11. Planned structure (built in PR-02 to PR-04 for the lifecycle, timers, termination, STOP, HOLD and CANCEL; the joint fault model follows in PR-05; the matrix generator, matrix test and property test in PR-06)

`src/kritva_motion/lifecycle/`: a state and transition model (tables as data), the termination record, the joint model, the engine (single-threaded, no globals, injected clock), and the execution port as a `typing.Protocol`. `scripts/` gets a generator that prints the transition matrix from the code. A test compares the generated matrix with the table in this document and fails on a missing, extra or duplicated transition, not only on a count. `tests/lifecycle/` holds the dedicated per-ID tests, the negative sequences (invalid, duplicate, stale and conflicting inputs) and the fixed-seed property test, which records the seed, the iteration count and the command and does not replace the mapped tests.
