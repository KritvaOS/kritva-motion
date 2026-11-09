# KOS-MOTION-003: owner review record (prepared for the review, not yet decided)

Date prepared: 2026-11-09. Reviewer and approver: Dinesh (repository owner), interim architecture and safety reviewer (D-047). This review is not independent.
Reviewed commit: to be filled in by the owner at the review (main after the PR-06 merge). No commit hash is stated here because none exists yet.
Decision: **pending**. This file records what is offered for the review; it is not an acceptance. The owner's decision is added by the owner, and `planning/TASKS.md` changes status only then.

## Evidence offered per criterion

| Criterion | What is offered | Where |
|---|---|---|
| AC-301 lifecycle and transition table | T1 to T7 each reached and recorded once with a reason code (CT-LC-01); all 25 ordered pairs tested (CT-LC-02); terminal states never change (CT-LC-03); the transition matrix is printed from the code and compared with `LIFECYCLE.md` row by row, with broken copies of the document (missing, extra, duplicated, replaced row) required to fail | `tests/lifecycle/test_lifecycle_conformance.py`, `test_lifecycle_final.py`, `test_lifecycle_matrix.py`; `scripts/lifecycle_matrix.py` |
| AC-302 phases | CT-LC-04 and CT-LC-06, deadline and cancellation before and after dispatch, a late start never revives a terminating or terminal command | `test_lifecycle_conformance.py`, `test_lifecycle_timers.py`, `test_lifecycle_termination.py` |
| AC-303 `STOP`, `HOLD`, `CANCEL`, `CLEAR_FAULT` | own identity and lifecycle, outcomes from the referenced attempt, joining without restarting the bound, receipt never reported as effect | `test_lifecycle_control.py`, `test_lifecycle_control_behaviour.py`, `test_lifecycle_faults.py` |
| AC-304 time and termination | injected monotonic clock, no system clock (AST test), bound started once, cause selection of 10.6, `TERMINATION_UNCONFIRMED` faults the joint and sets `UNKNOWN` | `test_lifecycle_timers.py`, `test_lifecycle_termination.py`, `test_lifecycle_engine.py` |
| AC-305 joint state, faults, recovery | 22 PR-05 target IDs plus 24 behaviour tests; control and health transitions checked against the 13.3 tables; a fault is cleared only by `CLEAR_FAULT` of that fault; a status report never clears one | `test_lifecycle_faults.py`, `test_lifecycle_faults_behaviour.py` |
| AC-306 targets, property test, negative cases | 55 target IDs, one dedicated test each, mapped in the manifest and checked by the gate (94 IN_SCOPE, 25 DEFERRED, 5 OUT_OF_SCOPE); a test compares `ID_MATRIX.md` with the manifest; a fixed-seed property test (seed 20261103, 400 streams of 45 inputs, command and counts printed on every run) checks INV-01 to INV-04, INV-07, INV-10 and INV-12; negative sequences cover invalid, duplicate, stale and conflicting inputs; the 39 earlier tests pass | `scripts/test_gate.py` (`make test-unit`), `test_lifecycle_property.py`, `test_lifecycle_matrix.py` |
| AC-307 no I/O, evidence limit stated | the engine imports no clock, randomness, I/O or backend module (AST test); the documents state the software-evidence limit and that the review is not independent | `test_lifecycle_engine.py`, `README.md`, `LIFECYCLE.md` |

Mutation check (not part of the gate): a defect injected into a copy of the engine, such as a terminal state that does not reset its phase or a terminal transition that drops its reason code, made the property test and the scenario tests fail. This shows the tests can fail; it is not a coverage claim.

## What the owner is asked to decide or confirm

- Interpretations I-1 to I-36 in `LIFECYCLE.md` section 10 are the engine's reading where the contract is silent. I-1 to I-11 were signed off in PR-01; I-12 to I-36 were added during the implementation pull requests and have not had a separate owner sign-off.
- Open points that the engine does not settle (none changes the contract):
  - I-35: loss of required feedback on a confirmed `HOLDING` joint with no running command is not modelled; contract 9.5 says it follows section 13, but 13.4 names no trigger.
  - I-27 and I-32: `CLEAR_FAULT` for stop-related faults requires a confirmed stop, not only a status report. This is conservative.
  - I-34: a deferred `CLEAR_FAULT` whose preconditions lapse stays pending until `dispatch` is called again; the caller drives the application point.
  - Possible contract findings recorded earlier (the I-3 gap in 7.8, the I-7 gap in 13.4, and the three findings of KOS-MOTION-002).
- Seven tests of PR-02 to PR-04 were adapted in PR-05 because loss of required feedback is now a fault; their assertions were otherwise kept.

## What this review does not mean

- It is software evidence only: a pure in-memory engine driven by supplied inputs. No Motion runtime process, backend, simulator, activation path, idempotency store, event publisher or history store exists. 25 conformance IDs are DEFERRED and 5 are out of scope; they are not counted as passed.
- No physical or safety validation. Gate V2-M6 stays on HOLD. This is not a safety case (AC-307).
- The review is not independent (D-047, D-065). No independent safety reviewer has been assigned.
- The contract stays a draft and is untagged; section 16 is PROVISIONAL.
- `unit-tests` is not a required check in `kritva-gate.json` or the `main` ruleset; that is a central decision.
- `status/status.json` has no KOS-MOTION-003 entry, so the program snapshot shows the task as not reported. That is an owner and program matter and is not changed here.
- This repository reports facts only. Credit is decided by the kritva-program central approval with verified CI evidence.

## Evidence record

`tasks/KOS-MOTION-003/EVIDENCE.json` is not written yet. It lists passing CI runs on the reviewed `main` commit and can only be written after the PR-06 merge and the owner's decision, from the real run URLs.
