# KOS-MOTION-005: owner review record

Date: 2026-11-15. Reviewer and approver: Dinesh (repository owner), interim architecture and safety reviewer (D-047). This review is not independent.
Reviewed commit: `1d4f433fa83ef05db6c14e92bd23903a5bac7dfd` (main after the merge of pull request 53, KOS-MOTION-005 PR-06; the source and test files are unchanged since).
Decision: the owner accepts task KOS-MOTION-005 against AC-501 to AC-507 (`ACCEPTANCE_CRITERIA.md` section 3C, text unchanged since it was proposed). Acceptance instruction: Dinesh, chat, 2026-11-15, after the merge of PR-06 ("Accept it now"). Central credit is a separate approval in kritva-program.

## Result per criterion

AC-501 to AC-507 are accepted, each on the basis below.

| Criterion | Basis | Where |
|---|---|---|
| AC-501 configuration activation | `CONFIG_NOT_ACTIVE` until a validated configuration is active (CT-CFG-01); version and SHA-256 digest bound at admission (CT-CFG-03); an activation applies only to later commands and an earlier command keeps its own version and parameters (CT-CFG-04, with a test of the termination bound); an update incompatible with an open command is refused with the reason named (CT-CFG-05); rollback needs a supplied authorization and is traceable in an append-only activation record (CT-CFG-06) | `tests/stores/test_config_registry.py`, `src/kritva_motion/stores/config_registry.py`, per-command binding in `src/kritva_motion/lifecycle/engine.py` |
| AC-502 idempotency | identical resubmission returns the stored original with the replay flag and creates no second command (CT-ID-01); same ID with different content is `REQUEST_ID_CONFLICT` (CT-ID-02); identity scoped to the client (CT-ID-03); a replayed rejection returns the same rejection (CT-ID-04); after the retention a reused ID is a new request, on a fake clock (CT-ID-05); the retention minimum of 7.4 is checked at activation | `tests/stores/test_idempotency.py`, `src/kritva_motion/stores/idempotency.py`, `coordinator.py` |
| AC-503 command history | one record per submission with the 15.1 fields this layer can fill (CT-HIS-01); accepted and rejected kept apart, a rejection with no command_id and no lifecycle (CT-LC-05); append-only with no overwrite or delete operation; derived fields cannot be overwritten; retention is a parameter | `tests/stores/test_history.py`, `src/kritva_motion/stores/history.py` |
| AC-504 feedback status | `VALID`, `STALE`, `INVALID`, `MISSING` reported distinctly and never as valid, an invalid value never shown as measured state, backend health independent (CT-FB-03, closed by mapping onto the existing engine behaviour, question Q-8) | `tests/stores/test_feedback_status.py` |
| AC-505 event streams | unique `event_id`, sequence numbers 1, 2, 3 per stream whatever the sinks do (CT-EV-01); duplicates tolerated and the status query authoritative after loss (CT-EV-02); no subscriber or a failing sink changes nothing (CT-EV-03); joint and backend events only in their own streams (CT-EV-04); best-effort loss visible as a gap, tail loss found by `last_sequence_number` (CT-EV-05); every published event validates against `contract/motion-event.schema.json`; the reference consumer lives in the tests | `tests/stores/test_events.py`, `src/kritva_motion/stores/events.py` |
| AC-506 targets, property test, negative cases | all 19 target IDs have one dedicated test, mapped in the manifest and checked by the gate (113 IN_SCOPE, 6 DEFERRED, 5 OUT_OF_SCOPE); CT-DET-02 by an input journal and replay (question Q-4, owner decision 2026-11-15); a test compares `ID_MATRIX.md` with the manifest; a fixed-seed property test (seed 20261115, 150 streams of 40 steps, command and counts printed on every run) checks the invariants of `STORES.md` section 4 against a model written in the test; negative cases cover duplicate, conflicting, stale, expired and out-of-order inputs; the 94 earlier IN_SCOPE tests pass unchanged | `scripts/test_gate.py` (`make test-unit`), `tests/stores/test_stores_property.py`, `tests/stores/test_journal.py`, `tests/gate/test_id_matrix_005.py` |
| AC-507 no I/O, evidence limit stated | a test scans the source for transport, network, file, clock and subprocess use and finds none; the only `deliver` is the abstract port; no authentication or authorization is implemented (they are supplied inputs); the documents state the software-evidence limit and that the review is not independent | `tests/stores/test_events.py`, `README.md`, `STORES.md` |

Mutation check (not part of the gate): four defects injected into copies of the stores (client scope removed from the idempotency key, a skipped sequence number, a wrong digest handed to the engine, rejections not recorded in history) each made the property test fail. This shows the test can fail; it is not a coverage claim.

## Interpretations and open points carried by this acceptance

- Interpretations I-36 to I-39 in `STORES.md` are the stores' reading where the contract is silent, not contract text: I-36 (joint-level feedback monitoring reads the active configuration), I-37 (content identity also covers `constraints` and `priority`), I-38 (an idempotent replay is a marker on the original history record, not a new record), I-39 (event id form, sink failure record, client identity on command events). The answers to Q-1 to Q-10 recorded in `STORES.md` are accepted as the owner decisions they are.
- Open points that the stores do not settle (none changes the contract):
  - Contract findings: 3.1 does not list the idempotency retention that 7.4 says the configuration states (Q-2); 3.3 defines no digest algorithm (Q-10, SHA-256 over canonical JSON is an interpretation); 3.4 does not say what makes an update incompatible (Q-9, a minimum rule is used).
  - F-8: contract 14.3 lists `BACKEND_HEALTH_CHANGED` and `FEEDBACK_STATUS_CHANGED`, but the KOS-MOTION-003 engine emits neither; emitting them would be an engine change and is not made here.
  - I-27, I-32, I-34 and I-35 of KOS-MOTION-003 stay open; none was found to affect this task.
- Two small engine changes were made, as listed in `STORES.md` section 7 and covered by the 94 earlier tests: per-command configuration binding with an engine that can start with no configuration (PR-02), and the optional `idempotency` keyword on `submit` (PR-03). No lifecycle semantics changed. One test of KOS-MOTION-003 (`test_lifecycle_matrix.py`) was adapted to record the IDs that this task delivered; its assertions were otherwise kept.

## What this review does not mean

- It is software evidence only: pure, in-memory stores around a deterministic engine, driven by supplied inputs and an injected clock. Nothing is durable across a restart, no event transport exists, authentication and authorization are not implemented, no backend or simulator exists, real time is not tested and concurrent callers are not modelled. 6 conformance IDs are DEFERRED (the five CT-AUTH IDs and CT-BE-02) and 5 are out of scope; they are not counted as passed.
- No physical or safety validation. Gate V2-M6 stays on HOLD. This is not a safety case (AC-507).
- The review is not independent (D-047, D-065). No independent safety reviewer has been assigned.
- The contract stays a draft and is untagged; section 16 is PROVISIONAL. The integration and regression gates still exit 3 (NOT_IMPLEMENTED).
- `status/status.json` has no KOS-MOTION-005 entry, so the program snapshot shows the task as not reported until the owning workstream reports it. That is an owner and program matter and is not changed here.
- This repository reports facts only. Credit is decided by the kritva-program central approval with verified CI evidence.

## Evidence record

Machine-readable record: `tasks/KOS-MOTION-005/EVIDENCE.json`: four passing runs on the reviewed commit (unit-tests, secret-scan, readme-check, progress-check). `commit-message-check` and `pr-acceptance-gate` run on pull requests only, so they have no run on a `main` commit; their results are on the merged pull requests 48 to 53. `unit-tests` runs `make test-unit`: the unit tests (440 tests: 113 IN_SCOPE conformance tests plus behaviour, matrix and property tests) and the conformance manifest gate. These show the repository checks passed; they are not tests of runtime or physical behaviour.
