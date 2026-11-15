# Acceptance Criteria: kritva-motion

Standard: kritva-program `v2/planning/ACCEPTANCE_STANDARD.md` (proposed; approval pending PD-005, PD-006). Criteria below are for tasks KOS-MOTION-001 (Motion command and state contract, section 3), KOS-MOTION-002 (Command validation, limit enforcement and fault-path tests, section 3A) and KOS-MOTION-003 (Motion lifecycle, termination and fault state machine, section 3B) and are proposed until the owner approves each task's acceptance. KOS-MOTION-001 (AC-001 to AC-005) was accepted by the owner on 2026-11-05; the record is `tasks/KOS-MOTION-001/REVIEW.md`. Section 3A (KOS-MOTION-002) is still proposed. Acceptance here is not weighting or credit, which the program decides centrally.

## 1. Purpose and scope

Owns: the motion command and state contract: command lifecycle, units, limits, feedback, timeout, cancellation, fault behaviour and the safety boundary of the contract.

Does not own: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation.

## 2. Normative dependencies

kritva-core (approved contract), kritvaos-community (public architecture description). Exact versions or commit SHAs are recorded here when the contracts they refer to are approved; none are pinned yet.

## 3. Functional criteria (KOS-MOTION-001)

| ID | Criterion (testable) | Verified by |
|---|---|---|
| AC-001 | Every command has a defined lifecycle (accepted, running, completed, cancelled, failed) with allowed transitions. | contract review, lifecycle tests |
| AC-002 | Units and limits are declared per command and enforced by validation; an out-of-limit command is rejected with a defined error. | validation tests |
| AC-003 | Timeout, cancellation and fault behaviour are specified, including the state reported after a fault. | fault-path tests |
| AC-004 | The contract states its safety boundary: software acceptance of this contract is never physical or safety validation. | review (independent safety reviewer when assigned) |
| AC-005 | Actuator-specific transport and driver details stay below the contract. | contract review |

## 3A. Functional criteria (KOS-MOTION-002)

KOS-MOTION-002 delivers a software-only reference validator for the Motion contract and the tests that run it. It validates a supplied, structurally valid `AdmissionContext` and joint-state snapshot. It does not show that a live snapshot is current, that concurrent commands cannot race, that a backend is authoritative, that termination occurs or that a fault propagates at runtime; those belong to later tasks (candidate KOS-MOTION-003 for the lifecycle, termination and fault state machine). Its acceptance begins after KOS-MOTION-001 is accepted.

| ID | Criterion (testable) | Verified by |
|---|---|---|
| AC-201 | The reference validator rejects configurations that violate contract section 3 before they can be considered valid for activation (no activation runtime is built here): unknown policy values, a continuous joint with position mode, `DEGRADE` with `feedback_required` true, a degradation policy that lists `SET_POSITION` or `HOLD` for `FEEDBACK_OPTIONAL_UNAVAILABLE`, and a policy the declared backend capabilities cannot satisfy. Configuration validation may report several violations. | unit tests with fixtures |
| AC-202 | Command admission runs in the fixed order of contract 8.4 and returns only the first failure. Every admission code of `ERROR_CODES.md` section 1 that a command can reach has at least one fixture, every adjacent pair of steps has a fixture that violates both and reports the earlier one, and several failures inside one step give a deterministic result under a documented sub-order. The result states accepted or rejected, the first error code, the step or field and an optional message, and carries no command ID or state change. | unit tests |
| AC-203 | Effective limits are the intersection of backend, configuration and command constraints. A constraint that widens a limit is rejected `INVALID_CONSTRAINT`; requested position and velocity outside the effective limits are rejected `LIMIT_POSITION` or `LIMIT_VELOCITY`; non-finite numbers are rejected `NON_FINITE_VALUE`; the effective acceleration maximum is the correct intersection. `LIMIT_ACCELERATION` is reserved in contract v0.1.0 (8.3) and is not produced. | unit tests |
| AC-204 | Joint-state preconditions follow the exemption matrix of contract 8.6 for `UNKNOWN`, `FAULTED` and `DEGRADED` snapshots, including `TARGET_STATE_UNKNOWN` with health `READY`, feedback freshness against a supplied monotonic reference time (the validator never reads the system clock), and the `CLEAR_FAULT` preconditions of 13.6. `STOP`, `CANCEL` and queries follow their own rows; query authorization is tested on a path separate from command admission. The snapshot contents are those of the `AdmissionContext`; the claim is limited to a supplied, structurally valid context. | unit tests |
| AC-205 | The five schemas validate their positive example documents and reject their negative ones, with schema validity checked first. Every CT-SCH test ID in the conformance plan has an executable case. The evidence reports separately the number of example documents, the number of schema cases and the number of conformance IDs covered. | `make test-unit` |
| AC-206 | A manifest marks each conformance test ID IN_SCOPE, DEFERRED or OUT_OF_SCOPE. Each IN_SCOPE ID has exactly one mapping to a discovered, non-skipped test and a recorded contract section; the gate fails on a missing, duplicated, unmapped or skipped IN_SCOPE test or a mapping to a nonexistent test. DEFERRED IDs are never reported as implemented or passed. Tests are deterministic: no clock, randomness or network. | `make test-unit` |
| AC-207 | The validator performs no I/O toward a backend or device. The documentation states that passing tests is software evidence only and never physical or safety validation. Review status is recorded as owner-reviewed and not independent (D-047); this criterion is not a safety case. | review |

## 3B. Functional criteria (KOS-MOTION-003)

KOS-MOTION-003 delivers a pure, in-memory, deterministic reference implementation of the Motion lifecycle, termination and fault semantics (design: `tasks/KOS-MOTION-003/LIFECYCLE.md`, targets: `tasks/KOS-MOTION-003/ID_MATRIX.md`), driven by supplied inputs and an injected monotonic clock. It adds no state, phase, reason code or event name to the contract. It shows that the engine follows the contract for a supplied, ordered input stream; it does not show that a backend behaves as supplied, that anything stopped physically, that real time behaves like the injected clock or that concurrent callers cannot race. Its implementation starts only after the owner approves the PR-01 design. Its acceptance begins after KOS-MOTION-002 is accepted (met).

| ID | Criterion (testable) | Verified by |
|---|---|---|
| AC-301 | The engine implements the lifecycle states and the transition table of contract 7.5. Every transition in the table is reached by a test and every pair not in the table is refused by a test. A terminal state never changes and a late input for a terminal command is ignored and recorded. Each transition is recorded once with a timestamp and a reason code. | unit tests; a transition matrix generated from the code and compared with `LIFECYCLE.md` by a test that fails on a missing, extra or duplicated transition |
| AC-302 | The phases of contract 7.6 follow its rules: cancellation before dispatch completes without backend termination only when no dispatch occurred; after dispatch and before start confirmation the command moves to `TERMINATING`; a late start confirmation never revives a terminating or terminal command and is ignored and recorded. A terminal command has phase `NONE`. | unit tests |
| AC-303 | `STOP`, `HOLD`, `CANCEL` and `CLEAR_FAULT` follow contract 6, 7.8 and 9: own command identity and lifecycle, outcomes derived from the referenced termination attempt, joining of an outstanding attempt without restarting the bound, explicit preemption by `STOP`. Receipt of a request is never reported as its effect. | unit tests |
| AC-304 | Deadline, execution timeout and termination follow contract 10 with an injected monotonic clock. The engine never reads the system clock. The termination bound is started once; reason selection follows 10.6; an unconfirmed termination ends `FAILED(TERMINATION_UNCONFIRMED)`, faults the joint and sets the control state `UNKNOWN`. | unit tests with a fake clock |
| AC-305 | Joint control and health state, fault propagation, degradation and recovery follow contract 13. `FAILED` and `FAULTED` stay independent, interrupted commands never resume, a fault is cleared only by `CLEAR_FAULT` of that fault, and a status report alone never clears one. | unit tests |
| AC-306 | Every conformance ID classified as a target in `tasks/KOS-MOTION-003/ID_MATRIX.md` has exactly one dedicated test, mapped in the manifest and checked by the gate; the other IDs stay DEFERRED or OUT_OF_SCOPE with a reason. A fixed-seed property test checks the invariants of `LIFECYCLE.md` section 9 over random input sequences and records the seed, the iteration count and the command; it does not replace the mapped tests. Negative cases cover invalid, duplicate, stale and conflicting inputs. All 39 earlier IN_SCOPE tests still pass. | `make test-unit` |
| AC-307 | The engine performs no I/O toward a backend or device, imports no simulator or hardware module and holds no backend-specific state. The documentation states that passing tests is software evidence only, never physical or safety validation, and that the review is owner-reviewed and not independent (D-047); this criterion is not a safety case. | review |

## 3C. Functional criteria (KOS-MOTION-005)

KOS-MOTION-005 delivers pure, in-memory, deterministic reference implementations of the Motion contract parts that need a store, an activation step or a publisher: configuration activation, the idempotency store, command history with feedback status, and event streams (design: `tasks/KOS-MOTION-005/STORES.md`, targets: `tasks/KOS-MOTION-005/ID_MATRIX.md`), driven by supplied inputs and an injected monotonic clock. It adds no state, phase, reason code, event name or contract field and does not change the lifecycle semantics of KOS-MOTION-003. It shows that the stores, the activation step and the publisher follow the contract for supplied, ordered inputs; it does not show durability across a restart, delivery over a transport, authentication or authorization, that a backend behaves as supplied, that real time behaves like the injected clock or that concurrent callers cannot race. Its implementation starts only after the owner approves the PR-01 design. Its acceptance by the owner is a separate step, and credit needs a central approval.

| ID | Criterion (testable) | Verified by |
|---|---|---|
| AC-501 | Configuration activation follows contract 3.2 to 3.4: every submission is rejected `CONFIG_NOT_ACTIVE` until a configuration is validated and active; every accepted command records the `config_version` and `config_digest` of its admission and keeps them for its life; an update applies only to commands accepted after activation; an incompatible update is refused with an explicit report while an affected command is active; rollback is explicit, traceable and requires a supplied authorization result. | unit tests |
| AC-502 | The idempotency store follows contract 7.3 and 7.4: an identical resubmission from the same client returns the original result with `idempotent_replay` true and creates no second command; the same request ID with different content is `REQUEST_ID_CONFLICT`; the same ID from a different client is an independent request; a replayed rejection returns the same rejection; after the retention period a reused ID is a new request. | unit tests with a fake clock |
| AC-503 | Command history follows contract 15: one record per submission carrying the 15.1 fields this layer can fill (fields that depend on a supplied result are recorded as supplied), accepted and rejected submissions kept apart, a rejected submission has no `command_id` and no lifecycle, an earlier record is never overwritten, and retention is configurable. | unit tests |
| AC-504 | Feedback status per joint follows contract 11.2 and 11.3: `VALID`, `STALE`, `INVALID` and `MISSING` are reported distinctly, and invalid, stale or missing feedback is never reported as valid. | unit tests |
| AC-505 | Event streams follow contract 14: every event has a unique `event_id`, a stream and a sequence number that increases by one within its stream; command, joint and backend events appear only in their own streams; execution continues with no subscriber attached and when delivery fails; a duplicate delivery and a gap are detectable by a reference consumer, and the status query (14.1) stays authoritative after loss. | unit tests; a reference consumer in the tests |
| AC-506 | Every conformance ID classified as a target in `tasks/KOS-MOTION-005/ID_MATRIX.md` has exactly one dedicated test, mapped in the manifest and checked by the gate; the other IDs stay DEFERRED or OUT_OF_SCOPE with a reason. A test compares the ID matrix with the manifest. A fixed-seed property test checks the invariants of `STORES.md` over random interleavings of submission, replay, expiry, update and event delivery, and records the seed, the iteration count and the command; it does not replace the mapped tests. Negative cases cover duplicate, conflicting, stale, expired and out-of-order inputs. All 94 earlier IN_SCOPE tests still pass. | `make test-unit` |
| AC-507 | The code performs no I/O toward a backend, device, file, database, network or transport, imports no simulator or hardware module, reads no system clock and contains no authentication or authorization implementation. The documentation states that passing tests is software evidence only, never physical or safety validation, and that the review is owner-reviewed and not independent (D-047); this criterion is not a safety case. | review |

## 3D. Functional criteria (KOS-MOTION-004)

KOS-MOTION-004 delivers a software-only Execution Backend Interface (contract 17), a deterministic scripted simulator at level S1 behind it, a runtime driver that connects the KOS-MOTION-003 engine and the KOS-MOTION-005 stores to a backend through that interface, and the integration and regression gates (design: `tasks/KOS-MOTION-004/BACKEND.md`, targets: `tasks/KOS-MOTION-004/ID_MATRIX.md`), driven by supplied scripts and an injected monotonic clock. It adds no state, phase, reason code, event name or contract field and does not change the lifecycle semantics of KOS-MOTION-003 or the store semantics of KOS-MOTION-005 beyond the hooks listed in `BACKEND.md` section 8. It shows that the interface, the driver and a scripted simulator follow the contract; it does not show that any real actuator, firmware or transport conforms, that a simulated stop is a physical stop, that real time, latency or concurrency behave like the injected clock, or anything about the Core security interface. Its implementation starts only after the owner approves the PR-01 design. Its acceptance by the owner is a separate step, and credit needs a central approval.

| ID | Criterion (testable) | Verified by |
|---|---|---|
| AC-401 | The backend interface follows contract 17.1 and 17.4 as an abstract, transport-independent port, and every backend declares all capability items of 17.2 explicitly: a validator reports each missing or malformed item with its path and never fills a default. | unit tests |
| AC-402 | Every outgoing operation is checked against the backend's current declared capabilities before dispatch (17.3); an operation the backend does not declare is never sent and the command ends `FAILED(BACKEND_REJECTED_DISPATCH)` with the capability named in its record. | unit and integration tests |
| AC-403 | Backend reports drive the lifecycle as 17.4 and 17.5 specify: start, rejection, termination request accepted, termination confirmed bound to the backend reference and target, a partial or unknown outcome treated as unconfirmed, hold, feedback, health and faults; accepted is never confirmation; every report is applied once; a late, duplicate or mismatched report is ignored and recorded. | unit and integration tests |
| AC-404 | The simulator is scripted and deterministic (same script and calls, same reports byte for byte), declares every 17.2 item, models no joint dynamics or kinematics, and marks every output as simulated; no result is reported as physical validation (17.7). | unit tests |
| AC-405 | Swapping the simulator for a second conforming backend with an equivalent script leaves every public output (command records, history, events, status) unchanged, and no actuator-specific identifier appears in any public message or error. | integration tests |
| AC-406 | `make test-integration` runs scenario tests over the driver, the stores, the engine and a backend with no mock of the repository's own code, and `make test-regression` compares committed golden traces byte for byte; each exits 0 only when every test passes and non-zero otherwise; `make test` runs unit, integration and regression; the gates run in CI workflows. A fixed-seed property test of the driver invariants records its seed, iteration count and command. | `make test-integration`, `make test-regression` |
| AC-407 | Every conformance ID classified as a target in `tasks/KOS-MOTION-004/ID_MATRIX.md` has exactly one dedicated test, mapped in the manifest and checked by the gate; the other IDs stay DEFERRED with a reason; a test compares the ID matrix with the manifest; negative cases cover refused dispatch, late and duplicate reports, partial termination, unsynchronized clock and backend loss; all 113 earlier IN_SCOPE tests still pass. The source performs no I/O, thread or system-clock read; the engine, the stores and the admission code never import the backend package, the simulator or the driver (a test checks the import direction). The documentation states that passing tests is software evidence only, never physical or safety validation, and that the review is owner-reviewed and not independent (D-047); this criterion is not a safety case. | `make test-unit`, review |

## 4. Interface and API compatibility

The contract defines inputs, outputs, error handling, versioning and lifecycle, with time and units stated. Contracts are versioned independently of program phases. Motion owns motion-command semantics; physical claims stay gated on v2-m6 (hold).

## 5. Test gates

| Gate | Command | Required result | State |
|---|---|---|---|
| Unit | `make test-unit` | all pass | implemented by KOS-MOTION-002 (`scripts/test_gate.py`: unit tests and conformance manifest check); software evidence only |
| Integration | `make test-integration` | all pass, real dependency boundaries | implemented by KOS-MOTION-004 PR-05 (`scripts/integration_gate.py`: scenarios through the driver, stores, engine and a backend); software evidence only |
| Regression | `make test-regression` | all pass, suite unchanged by the change | NOT_IMPLEMENTED |
| Structure | `make check` | planning files present, commit checker self-test passes | implemented |

An unimplemented gate is reported as NOT_IMPLEMENTED and is never counted as a pass. No coverage threshold is set; one needs an approved decision.

## 6. Specialised gates

Determinism and error-path behaviour apply to every criterion above. No hardware-in-loop or physical validation applies: any such claim stays gated on program milestone V2-M6 (HOLD).

## 7. Evidence requirements

Immutable commit SHAs, CI run IDs for secret-scan, commit-message-check and the test gates, and the review record against the closing commit.

## 8. Definition of Done

As in the program standard section 1: stable task ID, merged through the approved PR, required checks green on the exact closing commit, reviews recorded, documentation and changelog updated, immutable evidence, no blocker converted into a pass.

## 9. Known limitations and exclusions

- No implementation exists; criteria are not yet testable by automated gates (gates listed NOT_IMPLEMENTED). The `unit-tests` workflow and required check for KOS-MOTION-002 are added in separate changes.
- The architecture and safety reviewer roles are held by the owner on an interim basis (program decision D-047, resolving PD-007); independent review is not yet in place.
- Licence: Apache-2.0, confirmed by the owner (program decision D-064, closing PD-013).

## 10. Change control

Accepted criteria are never edited. A change is a new criteria version with its own review; accepted evidence keeps the version it was produced under.
