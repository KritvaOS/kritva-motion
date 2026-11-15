# KOS-MOTION-004: backend interface, simulator and driver design

Design record of PR-01 (revision 1, 2026-11-15). Proposed until the owner approves PR-01 by merging it. It adds no state, phase, reason code, event name or contract field. Where the contract is silent it records an interpretation (I-40 onward, after I-39 of `tasks/KOS-MOTION-005/STORES.md`) or a contract finding, and the owner confirms each by reviewing this file. Software evidence only.

## 1. What exists and what is missing

The KOS-MOTION-003 engine is a pure state machine. It does not call a backend: every call returns a `Result` whose `requests` list holds backend requests as data (`dispatch`, `request_hold`, `release_hold`, `request_termination`), and the backend's answers come back as method calls (`execution_started`, `termination_request_accepted`, `termination_confirmed`, `termination_refused`, `hold_confirmed`, `hold_released`, `hold_release_failed`, `feedback`, `backend_health`, `backend_fault`, `backend_fault_cleared`). `lifecycle/port.py` holds a four-method `Protocol` that nothing implements. The engine reads a plain `backend` description (health, capabilities, joint limits) for admission.

Missing, and delivered by this task: a complete interface with the 17.2 declaration, something that executes the engine's requests against a backend and turns the backend's reports into engine calls, a backend to run against, and the gates that exercise them together.

## 2. Packages and import direction (Q-1)

| Package | Content | May import |
|---|---|---|
| `kritva_motion.backend` | `interface.py` (the port), `capabilities.py` (declaration and validator), `reports.py` (report records), `simulator.py` (S1) | the standard library only |
| `kritva_motion.runtime` | `driver.py` | `lifecycle`, `stores`, `backend` |
| `lifecycle`, `stores`, `admission`, `config_validation` | unchanged except the hooks of section 8 | never `backend` or `runtime` |

A test walks the import graph of the source and fails on any other edge. This keeps the engine free of backend-specific state (KOS-MOTION-003 governing rule 3) and keeps the simulator from importing engine code.

## 3. Capability declaration (Q-3, I-40)

Contract 17.2 lists the items; it defines no format. The declaration is plain data (dicts, lists, strings, numbers, booleans) that extends the `backend` description admission already reads:

| Item (17.2) | Field | Type and rule |
|---|---|---|
| supported target types | `supported_target_types` | non-empty list; in v0.1.0 only `joint` is usable (18) |
| supported joint types | `capabilities.supported_joint_types` | non-empty list of the contract's joint types |
| supported modes | `capabilities.supported_modes` | non-empty list of `position`, `velocity` |
| controlled stop | `capabilities.controlled_stop` | boolean, explicit |
| position hold | `capabilities.position_hold` | boolean, explicit |
| feedback availability | `capabilities.feedback` | `position` and `velocity`, each boolean |
| feedback rate or range | `capabilities.feedback_rate_hz` | `{min, max}` numbers, or `null` with `feedback_rate_declared_absent` true |
| execution cancellation | `capabilities.execution_cancellation` | boolean, explicit |
| maximum concurrent executions | `capabilities.max_concurrent_executions` | integer, at least 1 |
| backend health | `health` | one of `AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `FAULTED` |
| per-joint numerical limits | `joint_limits` | per joint: position range, maximum velocity, maximum acceleration where supported, or `no_narrower_limit: true` |
| clock domain and synchronization | `clock` | `{domain: string, synchronized: boolean}` |

The validator returns every missing or malformed item with its path, never stops at the first, and never fills a default. A boolean item that is absent is a failure, not `false` (CT-BE-01 needs an explicit declaration). Contract finding C-1: 17.2 defines no declaration format and `contract/` has no schema for it; this shape is an interpretation and a later contract clarification may replace it. The existing admission and configuration code keeps reading only the fields it reads today; the new fields are additive.

## 3A. Port (Q-2)

The port is pull-based and transport-independent. All time is the caller's monotonic reading `now_ms`.

| Operation (17.4) | Python form | Answer |
|---|---|---|
| `describe_capabilities()` | `describe_capabilities() -> dict` | the declaration of section 3, current at the call |
| `dispatch(execution_request)` | `dispatch(request, now_ms) -> DispatchAnswer` | `accepted` with a `backend_reference`, or `rejected` with a backend reason; the start itself arrives later as a report |
| `request_termination(backend_reference, cause)` | `request_termination(ref, cause, now_ms, target=None) -> TerminationAnswer` (I-44: `target` names the joint the confirmation is bound to) | `termination_request_accepted` or `refused`; never a confirmation |
| `confirm_termination` | a report from `poll` | `termination_confirmed`, bound to a `backend_reference` and a target |
| `request_hold(joint_id)` / `release_hold` | `request_hold(ref, joint_id, now_ms)`, `release_hold(ref, joint_id, now_ms)` | answer as for dispatch; confirmation arrives as `hold_confirmed` or `hold_released` |
| `feedback` | a report from `poll` | feedback records (11.1) with the backend timestamp |
| `health()` | `health() -> {health, faults}` and a report on change | backend health and faults |
| (reports) | `poll(now_ms) -> list` | the reports the backend has ready, in the order it produced them, each once |

Reports are records with a `kind` that is one of `execution_started`, `execution_rejected`, `termination_confirmed`, `hold_confirmed`, `hold_released`, `hold_release_failed`, `feedback`, `health`, `fault`, `fault_cleared`. Every execution report carries the `backend_reference` it belongs to. `termination_unconfirmed` is not a backend report: Motion decides it when the bound passes (17.5), which the engine already does. A backend that never reports leaves the command to the engine's timers.

The port is the existing `ExecutionPort` extended; the four methods already in `lifecycle/port.py` keep their names. `backend_reference` stays an opaque string chosen by Motion (the engine already generates it per command); the backend echoes it.

## 4. Driver (Q-4, I-41)

`runtime.driver.Driver(engine, coordinator, backend, sink)` is the only place where the three meet. It has no clock of its own and no thread.

1. `submit(command, now_ms, ...)` passes the command through the KOS-MOTION-005 coordinator and the engine, then executes the engine's `requests`.
2. Before each outgoing `dispatch` or `request_hold` it calls `describe_capabilities()` and checks the operation against the current declaration: target type, joint type, mode, controlled stop for a STOP, position hold for a HOLD, cancellation for a cancel, concurrency against `max_concurrent_executions`. A failure sends nothing and ends the command `FAILED(BACKEND_REJECTED_DISPATCH)` through the engine hook of section 8, with the undeclared capability named in the record detail (I-41). This is the check CT-BE-02 names; admission keeps its own earlier check, and the two never disagree about the same declaration.
3. `poll(now_ms)` pulls the backend's reports in order and calls the matching engine method for each, then runs the engine `tick`. Each report is applied once. A report for an unknown, terminal, mismatched or duplicate execution is ignored by the engine and recorded, as today (CT-LC-03).
4. The engine's `events` and the coordinator's history and status are published as in KOS-MOTION-005. The driver adds no event of its own.
5. A backend error (an exception from the port, an answer that is not one of the allowed shapes) is treated as backend communication loss: `backend_fault(BACKEND_COMMUNICATION_LOSS)` and the engine's existing consequences. The driver never invents a lifecycle change.

## 5. Termination semantics (CT-BE-07)

The driver and the engine keep three things apart, as 17.5 requires: `termination_request_accepted` (the backend accepted the request), `termination_confirmed` (the backend confirms the identified execution reached its declared termination condition) and `termination_unconfirmed` (Motion decides: no confirmation within the bound). Confirmation is bound to the `backend_reference` and the target; a confirmation with another reference or target is ignored and recorded. A partial or unknown outcome from the backend is not a confirmation and leaves the bound running. A start report after a termination was requested does not change the phase (the engine already ignores it). The tests for CT-BE-07 drive these cases through the simulator and check the engine record, the events and the history, not only a return value. Backend confirmation is software-interface evidence and is not proof of physical stopping.

## 6. Simulator S1 (I-42)

`backend.simulator.Simulator(script, capabilities)` is a level S1 contract simulation (17.7): no joint dynamics, no kinematics, no randomness, no system clock. It declares its capabilities through the same validator as any backend and every output carries `simulated: true`.

A script is plain data. Per joint and per operation it states what the simulator does and after how many milliseconds of the injected clock: accept or reject a dispatch, report `execution_started` after a delay or never, produce feedback records from a list of `(at_ms, position, velocity, validity)` samples, accept, refuse or ignore a termination request, confirm after a delay, confirm partially (a report that names a different reference, or no report), report a health change or a fault at a time. Anything the script does not mention happens never. The same script and the same calls give the same reports byte for byte. The simulator checks its own script at construction and refuses an inconsistent one.

Nothing in the simulator models a physical joint. A completed simulated move shows that the driver and engine reacted to the scripted reports as the contract says; it is not evidence about any actuator.

## 7. Gates and the second backend (Q-7, Q-8)

- Integration (`make test-integration`, `tests/integration/`): scenarios that run submission, dispatch, start, feedback, completion, STOP and CANCEL, termination refusal and non-confirmation, backend degradation, fault and loss, and idempotent replay through the driver, the stores, the engine and a backend, and check the command record, history, events and status together. No mock of the repository's own code; the backend is the simulator or the second backend.
- Second backend (`tests/integration/loopback_backend.py`): a different implementation of the port (different internal bookkeeping, different delays expressed differently, same declaration shape) used for CT-BE-06. The same scenario set runs on both backends with equivalent scripts; the public outputs (command records, histories, events without backend timing detail, status) must be identical.
- Regression (`make test-regression`, `tests/regression/`): a fixed set of named scenarios whose canonical-JSON traces are committed under `tests/regression/golden/`. The gate runs them and compares byte for byte. A change in output fails the gate; the traces change only through `python3 scripts/regression_update.py`, whose diff is reviewed in the PR. A fixed-seed property test of the driver invariants (every report applied once, no lifecycle change without a report or a timer, a refused dispatch never reaches the backend, a terminal command never changes) records its seed, iteration count and command.
- `make test` runs unit, integration and regression and exits 0 only when all pass. `acceptance` and `lint` stay NOT_IMPLEMENTED (exit 3).
- CI: workflows `integration-tests` and `regression-tests`, in the style of `unit-tests`. They run on pull requests and on `main`. Making them required checks is an owner action on the `main` ruleset; until then they report but do not block.

## 8. Changes to existing code (hooks, listed so they are reviewed)

| Hook | Why | Regression run |
|---|---|---|
| `LifecycleEngine.execution_rejected(command_id, backend_reference, reason, now_ms, utc=None)` (Q-5): a backend rejection of a dispatch ends the command `FAILED(BACKEND_REJECTED_DISPATCH)` from `ACCEPTED` with phase `DISPATCH_PENDING`; guards as `execution_started` | 17.4 and 17.5 name `execution_rejected`; the engine has no input for it, and the driver also uses it for the failed capability check of section 4 | the 113 IN_SCOPE tests; new tests for the guards |
| Engine emits `BACKEND_HEALTH_CHANGED` and `FEEDBACK_STATUS_CHANGED` (Q-6, finding F-8) | 14.3 lists them; the `backend` stream has no health producer without it | the 113 tests; an event-order test |
| `LifecycleEngine.update_backend_description(description)` | the declaration can change after admission; admission and the engine must read the same current one | the 113 tests; a test that a changed declaration affects later admissions only |
| `LifecycleEngine.joint_type(joint_id)`: a read-only view of the configured joint type, added during PR-04 because the capability check of section 4 needs it and the driver must not read engine internals | the driver's own check | tests in `tests/runtime/test_engine_hooks.py` |
| `RecordingEngine` journals the two new input methods (`execution_rejected`, `update_backend_description`) | replay stays complete (CT-DET-02) | the journal tests |
| Adapted earlier matrix tests: `test_id_matrix_005.py` and the lifecycle matrix test pin the earlier classification of the six backend IDs, so they record the IDs this task delivers (as KOS-MOTION-005 did with `DELIVERED_BY_005`) | their assertions otherwise fail when the manifest status changes | the same tests, assertions kept |

No lifecycle semantics change: no new transition, state, phase or reason code. If a hook proves larger than described, the PR stops and returns to the owner.

## 9. Invariants checked by the tests and the property test

1. Every report from a backend is applied at most once; a repeated report is ignored and recorded.
2. No command changes state without a report, a command or a timer: the driver never advances a lifecycle by itself.
3. A dispatch refused by the capability check never reaches the backend.
4. A terminal command never changes; a late report after terminal is ignored and logged (CT-LC-03).
5. `termination_request_accepted` never completes a termination; only a bound `termination_confirmed` does (17.5).
6. The public output (records, history, events, status) contains no backend-specific identifier: the `backend_reference` is Motion's opaque string and a scan over every public message and error finds no vendor, device or bus identifier supplied by the backend (CT-BE-03; the scan lists what it looks for).
7. Swapping the backend for another conforming one with an equivalent script leaves every public output unchanged (CT-BE-06).
8. The same script, calls and clock readings always give the same trace.

## 10. Interpretations and findings

| ID | Statement |
|---|---|
| I-40 | The capability declaration shape of section 3, an additive extension of the `backend` description. Contract finding C-1: 17.2 defines no format |
| I-41 | A dispatch refused by the capability check ends the command `FAILED(BACKEND_REJECTED_DISPATCH)` with the capability named in the record detail; `BACKEND_CAPABILITY_UNSUPPORTED` stays an admission code |
| I-42 | The simulator is S1 only and scripted; "simulated" appears in every output |
| I-43 | Pull model: the backend produces reports, the driver collects them with `poll`; 17.4 allows event or poll |
| I-44 | A termination request names its target (`request_termination(..., target=)`), because a STOP with nothing running opens an attempt of its own whose reference no dispatch created; a simulator then stops the named joint. Additive: a backend that has the reference ignores the target. `release_hold` echoes the reference of the movement that asks for the release (the engine's request), so a backend does not look it up |
| I-45 | A backend rejection reason is free text and may name a device, a bus or a vendor; it is kept in the driver log (a diagnostic, not public output) and the record detail says only `BACKEND_REFUSED`, so CT-BE-03 can hold (found while writing the identifier scan). The integration directory runs inside the manifest gate (`make test-unit`) as well as under `make test-integration`, because the manifest gate needs every IN_SCOPE test to be discovered and run in one place |
| F-8 (closed in PR-04) | The engine now emits `BACKEND_HEALTH_CHANGED` (after the joint events of the same call, only on a change) and `FEEDBACK_STATUS_CHANGED` (when a joint's feedback status changes; data `{joint_id, from, to}`); the one earlier test that counted all events of a tick was adapted to ignore the new event, its assertion otherwise kept |

Open points of KOS-MOTION-003 (I-27, I-32, I-34, I-35) and the contract findings Q-2, Q-9 and Q-10 of KOS-MOTION-005 are reviewed in PR-01 for any effect on this task: none is expected to change here.

## 11. Honest limits

Software evidence only. A scripted backend and a deterministic simulator show that the interface can be implemented and that the driver follows contract 17; nothing here shows that a real actuator, firmware or transport conforms, that real time, latency or concurrency behave like the injected clock, or that a simulated stop is a physical stop. No authentication or authorization is implemented. The review is not independent (D-047).
