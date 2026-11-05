# Changelog: kritva-motion

## Unreleased

- Schema tests for the five contract schemas (`tests/schema/test_schemas.py`, 42 example documents, conformance IDs CT-SCH-01 to 09 all covered) and the pinned test-only dependency list `requirements-test.txt` (Task: KOS-MOTION-002, AC-205). Run with `python3 -m unittest discover -s tests/schema`; `make test-unit` stays NOT_IMPLEMENTED until step 7. Software evidence only.

- Started KOS-MOTION-002 (status IN_PROGRESS; delivery plan in its task record). Records only: no source code, no gate change, `make test-unit` stays NOT_IMPLEMENTED (Task: KOS-MOTION-002).

- KOS-MOTION-001 accepted by the owner (2026-11-05): `tasks/KOS-MOTION-001/REVIEW.md`, `EVIDENCE.json` (three passing checks on 3b9e12b7), TASKS.md status ACCEPTED, and the generator now reports evidence for an ACCEPTED task and fails closed without it (Task: KOS-MOTION-001). The review is not independent (D-047), the contract stays draft and untagged (section 16 PROVISIONAL), and nothing is physical or safety validation. Credit is a central program decision.

- Status report now lists KOS-MOTION-001 and KOS-MOTION-002, which the program baseline v9 contains (Tasks: None; program decision D-100). Execution only; no evidence of acceptance, no credit.
- Status reporting for the program: `scripts/status/gen_status.py` (generator and checker), `tests/status_gen/`, the vendored `status/status.schema.json` with its recorded SHA-256, and a generated `status/status.json` with no task reported yet (Tasks: None; program decision D-100). No credit, no gate change; `make test-unit` stays NOT_IMPLEMENTED.
- Registered task KOS-MOTION-002 (Command validation, limit enforcement and fault-path tests) as NOT_STARTED, with proposed acceptance criteria AC-201 to AC-207 and a task record (Task: KOS-MOTION-002; program decision D-100). No implementation, no gate change: `make test-unit` stays NOT_IMPLEMENTED.
- Contract revision 5 (proposed): acceleration is a declared maximum constraint only and `LIMIT_ACCELERATION` is reserved, because no v0.1.0 command requests an acceleration value (MOTION-AD-045, PROPOSED; contract 8.3, `ERROR_CODES.md`). Schemas and test plan unchanged (Tasks: None, contract clarification).
- Proposed architecture, decision register (MOTION-AD-001 to 044, all PROPOSED), normative Motion contract v0.1.0-draft, JSON schemas, error codes and conformance test plan (Task: KOS-MOTION-001). Software contract only: no runtime, no simulator, no physical or safety validation. Acceptance criteria AC-001 to AC-005 are unchanged; proposed amendments are in `tasks/KOS-MOTION-001/AC_AMENDMENT_PROPOSALS.md`.
- Governance baseline: acceptance criteria, planning files, CI checks, CODEOWNERS, AGENTS.md, SECURITY.md (Task: KOS-MOTION-001 planning; program milestone V2-M0-MOTION-001).
