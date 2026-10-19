# Acceptance Criteria: kritva-motion

Standard: kritva-program `v2/planning/ACCEPTANCE_STANDARD.md` (proposed; approval pending PD-005, PD-006). Criteria below are for task KOS-MOTION-001 (Motion command and state contract) and are proposed until the owner approves the task. Nothing here is accepted, weighted or credited.

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

- No implementation exists; criteria are not yet testable by automated gates (gates listed NOT_IMPLEMENTED).
- The architecture and safety reviewer roles are held by the owner on an interim basis (program decision D-047, resolving PD-007); independent review is not yet in place.
- Licence: Apache-2.0, confirmed by the owner (program decision D-064, closing PD-013).

## 10. Change control

Accepted criteria are never edited. A change is a new criteria version with its own review; accepted evidence keeps the version it was produced under.
