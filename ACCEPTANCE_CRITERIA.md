# Acceptance Criteria: kritva-motion

Standard: kritva-program `v2/planning/ACCEPTANCE_STANDARD.md` (proposed; approval pending PD-005, PD-006). Criteria below are for tasks KOS-MOTION-001 (Motion command and state contract, section 3) and KOS-MOTION-002 (Command validation, limit enforcement and fault-path tests, section 3A) and are proposed until the owner approves each task's acceptance. KOS-MOTION-001 (AC-001 to AC-005) was accepted by the owner on 2026-11-05; the record is `tasks/KOS-MOTION-001/REVIEW.md`. Section 3A (KOS-MOTION-002) is still proposed. Acceptance here is not weighting or credit, which the program decides centrally.

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

## 4. Interface and API compatibility

The contract defines inputs, outputs, error handling, versioning and lifecycle, with time and units stated. Contracts are versioned independently of program phases. Motion owns motion-command semantics; physical claims stay gated on v2-m6 (hold).

## 5. Test gates

| Gate | Command | Required result | State |
|---|---|---|---|
| Unit | `make test-unit` | all pass | NOT_IMPLEMENTED until KOS-MOTION-002 (Command validation, limit enforcement and fault-path tests) |
| Integration | `make test-integration` | all pass, real dependency boundaries | NOT_IMPLEMENTED |
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
