# KOS-MOTION-004: owner review record

Date: 2026-11-15. Reviewer and approver: Dinesh (repository owner), interim architecture and safety reviewer (D-047). This review is not independent.
Reviewed commit: `6824bc853dd974f292ddba5e1c813d44b46d70de` (main after the merge of the KOS-MOTION-004 PR-06 pull request; the source and test files are unchanged since).
Decision: the owner accepts task KOS-MOTION-004 against AC-401 to AC-407 (`ACCEPTANCE_CRITERIA.md` section 3D, text unchanged since it was proposed). Acceptance instruction: Dinesh, chat, after the merge of PR-06 (request to write the review record). Central credit is a separate approval in kritva-program.

## Result per criterion

AC-401 to AC-407 are accepted, each on the basis below.

| Criterion | Basis | Where |
|---|---|---|
| AC-401 interface and capability declaration | an abstract, transport-independent pull port (`describe_capabilities`, `dispatch`, `request_termination`, `request_hold`, `release_hold`, `health`, `poll`) over an injected monotonic clock; the validator reports each missing or malformed capability item with its path and fills no default (CT-BE-01, interpretation I-40) | `src/kritva_motion/backend/`, `tests/backend/` |
| AC-402 capability check before dispatch | every outgoing operation is checked against the current declaration; an undeclared operation is never sent and the command ends `FAILED(BACKEND_REJECTED_DISPATCH)` with the capability named in the record `detail` (CT-BE-02, I-41); a drifted declaration is rechecked at each dispatch | `tests/runtime/test_driver.py` (`TestCapabilityCheckBeforeDispatch`), `src/kritva_motion/runtime/driver.py` |
| AC-403 reports drive the lifecycle | start, rejection, termination accepted, confirmation bound to the backend reference and the target, partial or unknown outcome treated as unconfirmed, hold, feedback, health and faults; accepted is never confirmation (CT-BE-04, CT-BE-07, I-44); each report applied once; a late, duplicate, unknown or mismatched report is ignored and logged; a port exception or a wrong-shape answer becomes `BACKEND_COMMUNICATION_LOSS` | `tests/runtime/test_driver.py`, `tests/runtime/test_engine_hooks.py` |
| AC-404 scripted deterministic simulator | the S1 simulator validates its script at construction, declares every 17.2 item, models no dynamics, is byte-for-byte repeatable, and marks every output `simulated` (CT-BE-01; contract 17.7) | `tests/backend/`, `src/kritva_motion/backend/simulator.py` |
| AC-405 backend swap and no leaked identifier | a second conforming loopback backend with vendor-flavoured diagnostics, run through 13 scenarios, leaves every public output unchanged against the simulator (CT-BE-06); a scan of all public output finds no backend identifier or vendor text; a backend's free-text refusal stays in the driver log and the record says `BACKEND_REFUSED` (CT-BE-03, I-45) | `tests/integration/test_integration.py` |
| AC-406 gates, CI, property test | `make test-integration` (`scripts/integration_gate.py`), `make test-regression` (`scripts/regression_gate.py`: 13 committed golden traces compared byte for byte; they change only through `scripts/regression_update.py`) and `make test` (unit, integration, regression) exit 0 only when all pass; the `integration-tests` and `regression-tests` workflows run them; a fixed-seed property test of the driver (seed 20261116, 150 streams of 40 steps, command recorded on every run) checks seven invariants | `Makefile`, `.github/workflows/`, `tests/regression/`, `tests/runtime/test_driver_property.py` |
| AC-407 targets, negative cases, no I/O, import direction | all 6 target IDs (CT-BE-01, 02, 03, 04, 06, 07) have one dedicated test, mapped in the manifest and checked by the gate (119 IN_SCOPE, 5 DEFERRED, 0 OUT_OF_SCOPE); a test compares `ID_MATRIX.md` with the manifest; negative cases cover refused dispatch, late and duplicate reports, partial termination, unsynchronized clock and backend loss; the 113 earlier IN_SCOPE tests pass unchanged; the source performs no I/O, thread or system-clock read and the engine, stores and admission code never import the backend package, simulator or driver (checked by test) | `scripts/test_gate.py` (`make test-unit`), `tests/gate/test_id_matrix_004.py` |

The property test found one defect in the PR-04 driver: a stop that the engine asks for with no command (interpretation I-29) was taken for a command's and reported as a backend loss. It is fixed in PR-06 (interpretation I-46, `Driver.joint_fault`), with a regression test; restoring the old behaviour in a trial made the tests fail. This shows the test can fail; it is not a coverage claim.

## Interpretations and open points carried by this acceptance

- Interpretations I-40 to I-46 in `BACKEND.md` are the backend layer's reading where the contract is silent, not contract text: I-40 (declaration shape), I-41 (capability failure record), I-42 (S1 scripted), I-43 (pull model), I-44 (a termination request names its target), I-45 (backend free text stays in the driver log), I-46 (an advisory stop carries a reference of its own).
- F-8 is closed: the engine now emits `BACKEND_HEALTH_CHANGED` and `FEEDBACK_STATUS_CHANGED`.
- Engine hooks added by PR-04 and listed in `BACKEND.md` section 8 (`execution_rejected`, `update_backend_description`, `joint_type`, the record `detail`): no lifecycle semantics changed. Two tests were adapted (`test_lifecycle_faults_behaviour.py` ignores the new feedback-status event in one assertion; the matrix tests list the IDs this task delivered).
- Still open and not settled here: I-27, I-32, I-34 and I-35 of KOS-MOTION-003; contract findings Q-2, Q-9, Q-10 (KOS-MOTION-005) and C-1; the five CT-AUTH IDs are DEFERRED to the Core security interface.

## What this review does not mean

- It is software evidence only: a scripted simulator and a loopback test backend behind an abstract port, a driver run on supplied inputs and an injected clock. No actuator, no firmware, no transport, no real time, latency or concurrency is tested, and a simulated stop is never a physical stop. 5 conformance IDs are DEFERRED and are not counted as passed.
- No physical or safety validation. Gate V2-M6 stays on HOLD. This is not a safety case.
- The review is not independent (D-047, D-065). No independent safety reviewer has been assigned.
- The contract stays a draft and is untagged; section 16 is PROVISIONAL.
- `status/status.json` has no KOS-MOTION-004 entry until the owning workstream reports it (`REPORTED_TASKS`); that is a separate change.
- This repository reports facts only. Credit is decided by the kritva-program central approval with verified CI evidence.

## Evidence record

Machine-readable record: `tasks/KOS-MOTION-004/EVIDENCE.json`: the passing runs on the reviewed commit, listed there by name. `commit-message-check` and `pr-acceptance-gate` run on pull requests only; their results are on the merged pull requests of the task (PR-01 to PR-06). `unit-tests` runs `make test-unit` (571 tests, 119 IN_SCOPE conformance tests plus behaviour, matrix and property tests, and the manifest gate); `integration-tests` runs `make test-integration` (11 tests); `regression-tests` runs `make test-regression` (5 tests, 13 golden traces). These show the repository checks passed; they are not tests of runtime or physical behaviour.
