# REV-005: kritva-motion governance baseline (V2-M0-MOTION-001)

Status: APPROVED by the owner (D-114, 2026-11-07); ruleset and CODEOWNERS verified against GitHub on 2026-11-07 (D-115).
Reviewed commit: `44b733d5284d36895b1fff7e1cecedb69ca1720c` (kritva-motion `main`, recorded in the program review record)..
Program record: REV-005 in kritva-program `v2/planning/PENDING_REVIEWS.md`.
Related plan: kritva-program `v2/planning/M0_CLOSURE_PLAN.md` and `v2/planning/M0_TASK_DEFINITIONS.md`.

This record is evidence for the owner's review. It does not accept a task, award progress, or close V2-M0-MOTION-001. Closure needs the owner's decision below and an approved completion record for the milestone.

## 1. Proposed M0 task (planning only)

Title: Motion governance baseline accepted. Weight: 3. Registered as a `KOS-MOTION` task only after baseline v11 and owner approval; no placeholder row is added to `TASKS.md` before then.

| Criterion | Statement | Evidence in the working tree | Result |
|---|---|---|---|
| AC-M0-1 | Governance files exist: `AGENTS.md`, `ACCEPTANCE_CRITERIA.md`, `SECURITY.md`, `.github/CODEOWNERS`, `.github/kritva-gate.json` | All present | PRESENT |
| AC-M0-2 | Required checks are defined and named the same in workflows, `.github/kritva-gate.json` and the ruleset: `secret-scan`, `commit-message-check`, `pr-acceptance-gate`, `unit-tests`, `readme-check` | Gate file and ruleset list the same five. Check runs named `readme-check`, `secret-scan`, `commit-message-check`, `pr-acceptance-gate` and `unit-tests` appear on pull requests, so the job names match | MATCH |
| AC-M0-3 | The branch ruleset on `main` requires a pull request and the required checks. The approval roles `REPO_CODE_OWNER` and `ARCHITECTURE_REVIEWER` are held by the owner on an interim basis (D-047) and are not enforced by the ruleset (D-115) | Checked 2026-11-07 through the GitHub rulesets API: ruleset `protect-main` is active on the default branch, blocks deletion and force-push, requires a pull request with 0 approving reviews and no code-owner review, and requires secret-scan, commit-message-check, readme-check, pr-acceptance-gate, unit-tests. Bypass actors are not visible without admin access | PARTIAL: pull request and checks verified; approvals not enforced |
| AC-M0-4 | Commit policy is enforced by an automated check | `commit-message-check` workflow | PRESENT |
| AC-M0-5 | Task registry `planning/TASKS.md` matches the task folders and `status/` | KOS-MOTION-001 and 002 ACCEPTED, each with a `tasks/` record | CONSISTENT (re-check after KOS-MOTION-003 is added) |
| AC-M0-6 | Planning records are consistent and no unimplemented gate is reported as passing | `planning/MILESTONE_STATUS.md` marks M2 closed with software evidence only (D-104, D-105) and M5, M8 PROPOSED | CONSISTENT |

Note: V2-M2-MOTION-001 is already closed while M0 is open. This is one of the grandfathered sequence pairs in kritva-program `v2/planning/sequence_waivers.json`; closing M0 removes the exception.

## 2. CI evidence

Recorded 2026-11-07 from the GitHub check runs on the reviewed commit:

- unit-tests run id: 42385668725
- commit: `44b733d5284d36895b1fff7e1cecedb69ca1720c`
- result: success (push run on `main`; `secret-scan` run 42385668763 and `readme-check` run 42385668726 also succeeded). `commit-message-check` and `pr-acceptance-gate` run on pull requests, so they have no run on this commit.

## 3. Verification of ruleset and CODEOWNERS (2026-11-07)

- Ruleset: verified as stated in AC-M0-3. The approval requirement is not enforced; the owner merges under the interim reviewer roles of D-047.
- CODEOWNERS: verified. `*` and the protected files (`.github/`, `SECURITY.md`, `LICENSE`, `ACCEPTANCE_CRITERIA.md`) are owned by `@dineshannayya`. GitHub does not enforce code-owner review because the ruleset does not require it.
- Not verified: bypass actors (admin access needed).

## 4. Decision

Decision: APPROVED (owner, interim reviewer roles of D-047; recorded in D-114 on 2026-11-07; verification in D-115)
Decided by: Dinesh
Date: 2026-11-07
Notes: This is not independent review.
