# AGENTS.md: kritva-motion

Guidance for AI coding agents and contributors. The program rules live in kritva-program (`AGENTS.md`, `v2/planning/ACCEPTANCE_STANDARD.md`); this file adds the rules for this repository.

## 1. Scope

Kritva Motion owns: the motion command and state contract: command lifecycle, units, limits, feedback, timeout, cancellation, fault behaviour and the safety boundary of the contract. It does not own: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation. Respect these boundaries: Motion owns motion-command semantics; physical claims stay gated on V2-M6 (HOLD).

## 2. Program rules that apply here

1. This repository reports facts; the program repository decides baseline, weights, approvals and gates. A commit here never creates credit.
2. Software acceptance (tests, simulation, mocks, versioned interfaces) is never described as hardware or safety validation.
3. No empty folders, no placeholder tasks, no invented owners or dates. Add `src/` and other folders only when a real task needs them.
4. Interfaces are contract-first and versioned. A breaking change needs a new MAJOR version, a changelog entry and an approved decision.

## 3. Commits and pull requests

- Commit header: `type(scope): summary` (feat, fix, docs, refactor, test, build, ci, chore, perf, revert, security), at most 90 characters; an optional `[KOS-MOTION-NNN]` suffix must match the footer.
- Exactly one footer line, `Task: KOS-MOTION-NNN` or `Tasks: KOS-MOTION-NNN, KOS-MOTION-NNN`; a docs or chore commit that implements no task uses `Tasks: None (reason)`. Check with `python3 scripts/security/check_commit_format.py --range origin/main..HEAD`.
- Merge method is a merge commit (kritva-program D-053). PRs use `.github/PULL_REQUEST_TEMPLATE.md`.
- Never add a `Claude-Session:` trailer or a claude.ai session link to a commit. `commit-message-check` blocks them.
- Open a PR; do not push to `main`. Required checks: secret-scan, commit-message-check and pr-acceptance-gate (D-061).

## 4. Secrets

Never commit credentials, tokens, keys or production data. If one is committed by mistake, tell the Security Owner at once; removing it later does not make it safe.

## 5. Tests

`make check`, `make test-unit`, `make test-integration`, `make test-regression`, `make docs-check`. An unimplemented target exits 3 (NOT_IMPLEMENTED); do not edit a target to exit 0 to make a gate pass. A fixed defect adds a regression test.

## 6. Tags and milestones

Release tags are annotated SemVer (`vMAJOR.MINOR.PATCH`), created only after the approved merge. A milestone closes only through an approved `COMPLETION_RECORD.md`; a tag or a merge does not close it.

## 7. README changes

Run `make check-readme` after editing README.md. It is a structural check only (metadata fields, topic headings, relative links, placeholders); it does not show that the content is accurate, so review the content against the repository as well.
