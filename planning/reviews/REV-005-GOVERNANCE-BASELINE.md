# REV-005: kritva-motion governance baseline (V2-M0-MOTION-001)

Status: PREPARED, OWNER DECISION PENDING.
Reviewed commit: ____ (record the `main` commit current when the owner reviews; this package was prepared from the working tree of `main` on 2026-11-07).
Program record: REV-005 in kritva-program `v2/planning/PENDING_REVIEWS.md`.
Related plan: kritva-program `v2/planning/M0_CLOSURE_PLAN.md` and `v2/planning/M0_TASK_DEFINITIONS.md`.

This record is evidence for the owner's review. It does not accept a task, award progress, or close V2-M0-MOTION-001. Closure needs the owner's decision below and an approved completion record for the milestone.

## 1. Proposed M0 task (planning only)

Title: Motion governance baseline accepted. Weight: 3. Registered as a `KOS-MOTION` task only after baseline v11 and owner approval; no placeholder row is added to `TASKS.md` before then.

| Criterion | Statement | Evidence in the working tree | Result |
|---|---|---|---|
| AC-M0-1 | Governance files exist: `AGENTS.md`, `ACCEPTANCE_CRITERIA.md`, `SECURITY.md`, `.github/CODEOWNERS`, `.github/kritva-gate.json` | All present | PRESENT |
| AC-M0-2 | Required checks are defined and named the same in workflows and `.github/kritva-gate.json`: `secret-scan`, `commit-message-check`, `pr-acceptance-gate`, `unit-tests`, `readme-check` | Workflow files exist for all five; job names match for the first four. `readme-check` job name not yet compared | VERIFY readme-check job name |
| AC-M0-3 | The branch ruleset on `main` requires those checks, a pull request, and the approvals `REPO_CODE_OWNER` and `ARCHITECTURE_REVIEWER` | GitHub settings, not visible from the repository | OWNER TO ATTEST |
| AC-M0-4 | Commit policy is enforced by an automated check | `commit-message-check` workflow | PRESENT |
| AC-M0-5 | Task registry `planning/TASKS.md` matches the task folders and `status/` | KOS-MOTION-001 and 002 ACCEPTED, each with a `tasks/` record | CONSISTENT (re-check after KOS-MOTION-003 is added) |
| AC-M0-6 | Planning records are consistent and no unimplemented gate is reported as passing | `planning/MILESTONE_STATUS.md` marks M2 closed with software evidence only (D-104, D-105) and M5, M8 PROPOSED | CONSISTENT |

Note: V2-M2-MOTION-001 is already closed while M0 is open. This is one of the grandfathered sequence pairs in kritva-program `v2/planning/sequence_waivers.json`; closing M0 removes the exception.

## 2. CI evidence

Record a `unit-tests` run on the reviewed commit:

- unit-tests run id: ____
- commit: ____
- result: ____

## 3. Owner attestations

- [ ] Ruleset on `main` requires pull request, the five checks above, and both approval roles (AC-M0-3).
- [ ] CODEOWNERS entries are the intended approvers.

## 4. Decision

Decision: PENDING
Decided by: ____
Date: ____
Notes: ____
