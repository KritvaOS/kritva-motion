# KOS-MOTION-003: Motion lifecycle, termination and fault state machine

Status (revision 1): IN_PROGRESS since 2026-11-07. PR-01 (design) is awaiting owner review; no implementation pull request starts before the owner approves it. Owner approval: program decision D-107 (Dinesh, chat, 2026-11-06). Baseline: v10 (D-108), weight 8, milestone V2-M2-MOTION-002. KOS-MOTION-002 is accepted, so the dependency is met; the baseline has no dependency field, so it is enforced here.
Task owner: Dinesh (repository owner). Architecture and safety reviewer roles: Dinesh, interim (D-047); the review is not independent and every acceptance record says so.
The task earns credit only through a central approval with passing evidence. Motion reports facts only.

## 1. Scope

A pure, in-memory, deterministic reference implementation of the Motion lifecycle, termination and fault semantics of contract v0.1.0-draft, in the Python standard library, driven by supplied inputs and an injected monotonic clock. The design is [LIFECYCLE.md](LIFECYCLE.md); the IDs it targets are in [ID_MATRIX.md](ID_MATRIX.md).

| Deliverable | Contract |
|---|---|
| Command lifecycle, phases and transition table | 7.5, 7.6, 7.8 |
| Arbitration of the movement slot, `STOP`, `HOLD`, `CANCEL`, `CLEAR_FAULT` behaviour | 6, 9 |
| Deadline, execution timeout, termination record and bound | 10 |
| Completion from supplied feedback | 11, 12 |
| Joint control and health state, fault records, recovery | 13 |
| The abstract execution port (a protocol, no implementation) and the input vocabulary | 17.4, 17.5 |
| A generated transition matrix compared with LIFECYCLE.md, one dedicated test per target ID, negative sequences and a fixed-seed property test | AC-306 |

The engine reuses the KOS-MOTION-002 validator for admission (interpretation I-2).

## 2. Out of scope

Stores and publishers (idempotency, configuration activation, history, events and their delivery), the Execution Backend Interface implementation, simulators, hardware, ROS 2, the integration and regression gates, the Core security interface, and any physical or safety validation (gate V2-M6, HOLD). Candidate follow-on tasks are KOS-MOTION-004 (backend interface, simulator, integration and regression gates) and KOS-MOTION-005 (stores and publishers); neither is registered.

## 3. Acceptance mapping

Criteria AC-301 to AC-307 are in [ACCEPTANCE_CRITERIA.md](../../ACCEPTANCE_CRITERIA.md) section 3B and are proposed until accepted. The tests show that the engine follows the contract for a supplied, ordered input stream. They do not show that a backend behaves as supplied, that anything stopped physically, that real time behaves like the injected clock or that concurrent callers cannot race.

## 4. Governing rules

1. The contract is the baseline. The engine adds no state, phase, reason code or event name. Open semantics are recorded in LIFECYCLE.md section 10 as interpretations or contract findings and never added silently.
2. Approval of PR-01 authorizes implementation and does not authorize any change to the contract. A needed change is a separate contract clarification.
3. No backend or simulator import and no backend-specific state in the engine. A later backend task implements the port without changing the lifecycle semantics; a needed change requires a contract revision and a regression run.
4. DEFERRED IDs are never reported as passed. The existing manifest gate and the 39 earlier IN_SCOPE tests stay intact.

## 5. Delivery plan

| PR | Deliverable | Target IDs (see ID_MATRIX.md) |
|---|---|---|
| PR-01 | This design record: TASK.md, LIFECYCLE.md, ID_MATRIX.md, criteria AC-301..AC-307, TASKS.md row. Protected path (criteria): owner merge. Hard owner review stop | none |
| PR-02 | Normal lifecycle, completion, injected clock, recording | 14 |
| PR-03 | Cancellation, deadline, execution timeout, termination and unconfirmed termination | 8 |
| PR-04 | `STOP`, `HOLD`, `CANCEL`, arbitration | 10 |
| PR-05 | Faults, joint state, degradation, recovery, `CLEAR_FAULT` | 21 |
| PR-06 | Fault-injection scenario set, determinism, manifest update, matrix test, property test, documentation, review record | 2 |

Each implementation PR ships its own tests and updates the manifest for the IDs it covers, so the gate stays green at every step. Targets add up to 55; the owner confirms them in PR-01.

## 6. Review plan

Interim owner review (D-047), declared not independent. Compensating evidence: one dedicated test per target ID checked by the existing gate, the generated transition matrix compared with LIFECYCLE.md, negative sequences (invalid, duplicate, stale, conflicting inputs), a fixed-seed property test with seed, iteration count and command recorded in the CI evidence (it does not replace the mapped tests), all 39 earlier tests still passing, CI evidence bound to the exact commit. The checklist is `REVIEW.md`, written at closure. A read-only review by a second person is welcome and optional.

## 7. Dependencies

| Dependency | State |
|---|---|
| KOS-MOTION-002 accepted | met (D-103) |
| Baseline v10 with this task | frozen (D-108) |
| `unit-tests` and `readme-check` required checks | in place (D-104, D-106) |
| kritva-core security interface | not pinned; authorization stays a supplied input |

## 8. Honest limits

Software evidence only. 30 IDs outside the targets stay DEFERRED or OUT_OF_SCOPE. Contract section 16 stays PROVISIONAL, the contract stays a draft and no tag is created by this task. The integration and regression gates still exit 3.
