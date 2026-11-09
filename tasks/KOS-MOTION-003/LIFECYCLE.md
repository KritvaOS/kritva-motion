# KOS-MOTION-003: Lifecycle design (PR-01)

Status: signed off by the owner on 2026-11-08; all six pull requests are merged and the task was accepted by the owner on 2026-11-09 (`REVIEW.md`; interim review, D-047, not independent; software evidence only).

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

Joint transition tables (contract 13.3), as the code defines them. `python3 scripts/lifecycle_matrix.py` prints them and `--check` compares them with this document row by row; a test does the same and fails on a missing, extra or duplicated row. The command table is T1 to T7 in section 3.

| # | From (control) | To (control) | Trigger (13.3) |
|---|---|---|---|
| C1 | `IDLE` | `ACTIVE` | a movement command starts |
| C2 | `ACTIVE` | `IDLE` | completion or a confirmed stop, no hold engaged |
| C3 | `IDLE` | `HOLDING` | a confirmed hold |
| C4 | `HOLDING` | `ACTIVE` | a movement command starts |
| C5 | `HOLDING` | `IDLE` | a confirmed stop |
| C6 | `IDLE` | `UNKNOWN` | motion status can no longer be confirmed |
| C7 | `ACTIVE` | `UNKNOWN` | motion status can no longer be confirmed |
| C8 | `HOLDING` | `UNKNOWN` | motion status can no longer be confirmed |
| C9 | `UNKNOWN` | `IDLE` | a confirmed stop, or a fresh authoritative report (13.9) |
| C10 | `UNKNOWN` | `ACTIVE` | a fresh authoritative report (13.9 item 2) |
| C11 | `UNKNOWN` | `HOLDING` | a fresh authoritative report or a confirmed hold (13.9 item 2) |

| # | From (health) | To (health) | Trigger (13.3) |
|---|---|---|---|
| H1 | `READY` | `DEGRADED` | a declared limitation |
| H2 | `DEGRADED` | `READY` | the limitation clears, control state preserved |
| H3 | `READY` | `FAULTED` | a joint or backend fault |
| H4 | `DEGRADED` | `FAULTED` | a joint or backend fault |
| H5 | `FAULTED` | `READY` | CLEAR_FAULT with no other fault or degradation remaining |
| H6 | `FAULTED` | `DEGRADED` | CLEAR_FAULT while a degradation condition remains |

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

## 9. Invariants (tested, including by a fixed-seed property test)

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

Coverage: INV-01 to INV-04, INV-07, INV-10 and INV-12 are checked on every stream of `tests/lifecycle/test_lifecycle_property.py` (seed 20261103, 400 streams of 45 inputs, command and counts printed on every run); INV-01, INV-02, INV-03 and INV-12 are also checked on the listed scenarios of section 12 by CT-TMO-07, CT-LC-01 and CT-DET-01. INV-05, INV-06, INV-08 and INV-09 are covered by the dedicated tests of PR-03 to PR-05 and INV-13 by the no-I/O tests. The property test never replaces a mapped test.

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
| I-20 | What a STOP follows | exactly one attempt on its joint: (1) an outstanding attempt (any command with a `PENDING` termination record): the STOP joins it, `STOP_REQUESTED` is appended, no second request, the bound is not restarted; (2) a dispatched movement or pending `HOLD` in the slot: the STOP starts the attempt with cause `STOP_REQUESTED`; a command never dispatched ends `CANCELLED(STOPPED)` at once and the STOP falls to (3); (3) nothing active: the STOP opens its own attempt in its own termination record (I-6), preceded by a `release_hold` request on a `HOLDING` joint. A STOP after a terminal outcome is a new attempt and never changes the earlier record (PR-04) |
| I-21 | `RUNNING` for STOP and CANCEL (refines I-3) | they become `RUNNING` when the backend has accepted the attempt they follow (`termination_request_accepted`), and are `ACCEPTED` before; a STOP that owns its attempt has phase `TERMINATING`, one that follows another command's attempt and a CANCEL have phase `NONE`. CANCEL: `COMPLETED(CANCEL_EFFECTIVE)` when the target is `CANCELLED`, else `FAILED` with the target's reason. STOP: `COMPLETED(STOP_CONFIRMED)` when the attempt is `CONFIRMED` even if the target FAILED or the joint is `FAULTED`, `FAILED(TERMINATION_UNCONFIRMED)` when `UNCONFIRMED`. A confirmed STOP establishes `IDLE` from `ACTIVE`, `HOLDING` or `UNKNOWN` and never changes the health state or the fault records (6.2, 13.9) (PR-04) |
| I-22 | `HOLD` | accepted like a movement command (slot, deadline, timeout, `defer_dispatch`), dispatched as a `request_hold` request; `execution_started` makes it `RUNNING` and leaves the joint control state alone; the backend input `hold_confirmed` completes it `COMPLETED(HOLD_ENGAGED)` and sets `HOLDING`, also for a repeated `HOLD` on a `HOLDING` joint. An engagement report while a termination is outstanding is ignored; the attempt decides (PR-04) |
| I-23 | Releasing the hold at the start of a movement (9.5) | `execution_started` for a movement on a `HOLDING` joint emits a `release_hold` request and sets `ACTIVE`; `hold_released` ends the wait; `hold_release_failed` ends the command `FAILED(BACKEND_REJECTED_DISPATCH)`, sets the joint control state `UNKNOWN` (not `HOLDING`, not `IDLE`) and changes no health state (PR-04) |
| I-24 | Backend refusal of a STOP | the input `termination_refused` is valid only for a STOP-owned attempt before the backend accepted it: the STOP and every STOP that joined it end `FAILED(BACKEND_REJECTED_DISPATCH)`, the control state is unchanged, no fault is created, and the attempt record shows outcome `REFUSED`. A refusal of another command's termination is not modelled; the bound decides (ERROR_CODES section 2, contract 2.4 a) (PR-04) |
| I-25 | Backend health | `backend_health` updates what admission sees. `UNAVAILABLE` or `FAULTED` sets control state `UNKNOWN` on a joint that was `ACTIVE`, `HOLDING` or terminating (2.4 c); a backend that becomes available never leaves `UNKNOWN` by itself (13.9). Failing the commands in flight and raising backend and joint faults is PR-05 (PR-04) |
| I-26 | Fault record | every joint fault, whether reported by the backend or decided by the engine, is one record `{fault_id (fault-N, engine-assigned), code, fault_class JOINT or BACKEND, joint_id, command_id, raised_at, state ACTIVE or CLEARED}` on its joint, with a `JOINT_FAULT_RAISED` event; the joint is `FAULTED` while any record is `ACTIVE` (13.3, 13.6). Records are kept after clearing (PR-05) |
| I-27 | When the cause of a fault is resolved (13.6) | `FEEDBACK_LOST`: valid feedback is being received again. A backend code (`BACKEND_UNAVAILABLE`, `BACKEND_COMMUNICATION_LOSS`, `BACKEND_EXECUTION_FAILURE`): the backend condition was ended by `backend_fault_cleared`. Every other code (`TRACKING_ERROR`, `JOINT_LIMIT_VIOLATION`, `TERMINATION_UNCONFIRMED`): a termination on that joint was confirmed after the fault. A status report alone never resolves a stop-related cause; this is conservative and can be relaxed by a contract clarification (PR-05) |
| I-28 | Fault inputs | `joint_fault` accepts only `TRACKING_ERROR` and `JOINT_LIMIT_VIOLATION`; `FEEDBACK_LOST` and `TERMINATION_UNCONFIRMED` are decided by the engine. `backend_fault` takes the three backend codes and an optional joint list (default every joint) and raises one record per affected joint. A report of a code still `ACTIVE` on a joint is ignored and recorded (`duplicate_fault`). `backend_health` stays a separate input, so a backend fault does not change what admission sees (PR-05) |
| I-29 | Stop on a fault (13.4) | a fault appends cause `FAULT` to the termination record of every non-terminal movement command and pending `HOLD` on the joint, starting an attempt where none is outstanding; a command never dispatched ends `FAILED` with the fault code at once; an attempt a `STOP` owns is joined. When nothing carries the request (no command on the joint, joint not `IDLE`, backend able to stop) the engine emits one advisory `request_termination` with `command_id` null and the `fault_id`; no confirmation is bound to it (PR-05) |
| I-30 | Feedback loss and degradation (11.5, 13.8) | evaluated at every input and `tick` for a joint with a `RUNNING` command not terminating: feedback `INVALID`, `STALE` (older than `max_feedback_age_ms`) or `MISSING` (that long after the start) raises `FEEDBACK_LOST` and a controlled stop when `feedback_required` is true; otherwise the degradation reason `FEEDBACK_OPTIONAL_UNAVAILABLE` is set and the command continues. Valid feedback ends that reason. A termination at the same reading wins over the loss. `BACKEND_DEGRADED` follows the supplied backend health (PR-05) |
| I-31 | Health from faults and degradation | health is recomputed from the records: `FAULTED` while any fault is `ACTIVE`, else `DEGRADED` while a degradation reason remains, else `READY`. Control and health are separate dimensions, each checked against the 13.3 transition tables; a change the tables do not allow raises instead of being applied (PR-05) |
| I-32 | What never clears a fault (13.9 item 5) | a `status_report`, `backend_fault_cleared`, valid feedback and the end of a degradation reason never clear a fault record and never change `FAULTED`; only an applied `CLEAR_FAULT` does. A report can establish the control state of an `UNKNOWN` joint only (PR-05) |
| I-33 | `CLEAR_FAULT` (13.6) | admitted by the KOS-MOTION-002 `admit()` with the engine's fault, health and termination view as inputs. It names one fault and clears exactly that one atomically, passing `RUNNING` at that instant (I-3) and ending `COMPLETED(FAULT_CLEARED)`; health returns to `READY` or `DEGRADED` only when no other fault is `ACTIVE`. Every precondition is evaluated again at application; if one no longer holds, nothing is cleared and the input is ignored and recorded. A fault raised after acceptance fails every accepted `CLEAR_FAULT` of the joint (`NEW_FAULT`, with the code of that fault) (PR-05) |
| I-34 | Applying a deferred `CLEAR_FAULT` | with `defer_dispatch`, acceptance and application are separate points. A deferred `CLEAR_FAULT` whose preconditions have lapsed stays pending until `dispatch(command_id, ...)` is called again; the caller drives the application point, the engine has no clock of its own (PR-05) |
| I-35 | Open: required feedback lost on a confirmed `HOLDING` joint with no running command | contract 9.5 says it follows section 13, but 13.4 names no trigger for it. It is not modelled in PR-05: no fault is raised for it. Proposed for a contract clarification or for PR-06 if the owner decides |
| I-36 | Reading of CT-LC-01, CT-TMO-07 and CT-DET-01 | CT-LC-01: one stream reaches each of T2 to T7 (T1 starts every stream); each command record is a continuous chain from admission, no pair is recorded twice, every terminal transition carries a reason code of its state and the others none, and each transition is published once as `COMMAND_STATE_CHANGED`. CT-TMO-07: "every fault-injection scenario" is the set listed in section 12 (I-9); each scenario injects at least one fault; after every limit has passed, each accepted command has exactly one terminal transition, which is the last, and a late input changes nothing. CT-DET-01: each scenario run three times on fresh engines gives equal results, events, command records, joint state, fault records and joint transitions; the clock is the supplied readings (PR-06) |

Possible contract findings (not changed by this task): the I-3 gap in 7.8, the I-7 gap in 13.4, and the three findings already recorded in the task record of KOS-MOTION-002.

## 11. Structure (built in PR-02 to PR-06)

`src/kritva_motion/lifecycle/`: a state and transition model (tables as data), the termination record, the joint model, the engine (single-threaded, no globals, injected clock), and the execution port as a `typing.Protocol`. `scripts/lifecycle_matrix.py` prints the transition matrix from the code (`--check` compares it with this document). A test compares the generated matrix with the table in this document and fails on a missing, extra or duplicated transition, not only on a count. `tests/lifecycle/` holds the dedicated per-ID tests, the negative sequences (invalid, duplicate, stale and conflicting inputs) and the fixed-seed property test, which records the seed, the iteration count and the command and does not replace the mapped tests.

## 12. Fault-injection scenario set (CT-TMO-07, I-9, I-36)

The scripted streams in `tests/lifecycle/scenario_support.py`; a test compares this list with the code. Each one starts with both test joints ready and injects at least one fault. CT-TMO-07 and CT-DET-01 run all of them.

| # | Name | Fault injected |
|---|---|---|
| S1 | `feedback-lost-then-stop-confirmed` | required feedback goes silent on a running movement; the stop is confirmed |
| S2 | `feedback-lost-stop-never-confirmed` | as above, but the backend never confirms: the bound ends it |
| S3 | `tracking-error-while-running` | a reported tracking error on a running position command |
| S4 | `joint-limit-violation-after-dispatch` | a fault after dispatch and before the backend confirmed the start |
| S5 | `fault-before-dispatch` | a fault while the command is accepted and was never dispatched |
| S6 | `late-start-after-fault` | the backend confirms a start after the fault began the termination |
| S7 | `backend-unavailable-two-joints` | a backend fault on every joint while two commands run |
| S8 | `backend-fault-one-joint-then-cleared` | a communication loss on one joint that later ends; no fault record clears |
| S9 | `backend-execution-failure-no-confirmation` | an execution failure; the termination is refused by silence |
| S10 | `pending-hold-then-fault` | a HOLD waiting for engagement meets a fault |
| S11 | `fault-during-stop` | a fault reaches a joint while its STOP is waiting for confirmation |
| S12 | `fault-during-cancel` | a fault reaches a joint while a CANCEL of its command is outstanding |
| S13 | `stop-refused-then-fault` | the backend refuses a STOP on an idle joint, then a movement meets a fault |
| S14 | `deadline-passes-during-fault` | a command never started; its deadline and a fault both apply |
| S15 | `execution-timeout-unconfirmed-then-fault` | a timeout begins the termination, a fault joins it, nothing is confirmed |
| S16 | `duplicate-fault-and-confirmation` | the same fault and the same confirmation reported twice |
| S17 | `clear-fault-then-new-fault` | an accepted CLEAR_FAULT is overtaken by a new fault before it is applied |
| S18 | `clear-fault-applied` | recovery: fault, confirmed stop, CLEAR_FAULT applied; later motion is accepted |
| S19 | `hold-engaged-then-fault` | a confirmed hold is faulted; the hold's own command is already terminal |
| S20 | `movement-releases-hold-then-fault` | a movement releases a hold and a fault arrives before the release is confirmed |
