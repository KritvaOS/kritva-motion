# kritva-motion

> Planning and governance repository for the Motion command and state contract of the Kritva OS V2 plan. There is no implementation yet: the repository holds acceptance criteria, planning records, pull-request checks and rules, and no source code. The visibility class of this repository is not yet decided (D-039 recommends private).

| Property | Value |
|---|---|
| Project | KritvaOS (Kritva OS V2) |
| Repository | `KritvaOS/kritva-motion` |
| Repository Type | Capability (contract only; planning baseline, no implementation) |
| Visibility Class | Not yet decided (D-039 in kritva-program recommends PRIVATE; the Apache-2.0 licence file would permit a public release, so a public release needs an owner exception and a release review) |
| GitHub Setting | PUBLIC, temporary (D-028 and D-037 in kritva-program own the temporary exposure and its return plan); OWNER-ATTESTED: no independent check of the setting and no verification date is recorded here |
| Lifecycle Status | PLANNING (governance baseline only) |
| Repository Owner | Project owner (role; see section 15) |
| Security Owner | Security Owner role ([SECURITY.md](SECURITY.md)) |
| Architecture | Not yet defined: the architecture task KOS-MOTION-001 is proposed and not approved (see [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)) |
| Milestones | [planning/MILESTONE.md](planning/MILESTONE.md) and [planning/MILESTONE_STATUS.md](planning/MILESTONE_STATUS.md) |
| Tasks | [planning/TASKS.md](planning/TASKS.md) |
| Acceptance Criteria | [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) |
| Status Reporting | Not yet implemented: this repository has no `status/` directory and no generated status report (see section 10) |
| License | [LICENSE](LICENSE) (Apache License 2.0; see section 17 for an open question) |

This README follows the Kritva README standard (`v2/planning/standards/README_STANDARD.md` in [kritva-program](https://github.com/KritvaOS/kritva-program)). It is a navigation map; the documents it links own the detail.

## 1. Purpose and Scope

Kritva Motion is the part of Kritva OS V2 that will own the Motion command and state contract. Today this repository only plans that work.

**This repository owns** (as planned): the motion command and state contract: command lifecycle, units, limits, feedback, timeout, cancellation, fault behaviour and the safety boundary of the contract.

**This repository does not own**: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation.

**Implementation state.** IMPLEMENTED: the governance baseline only: the planning records under [planning/](planning/), the acceptance criteria, the pull-request workflows and their scripts, the commit-message checker with its tests, and the `Makefile` structure check. NOT YET IMPLEMENTED: the contract, any source code, tests of the contract, a `src/` folder, unit, integration and regression gates, status reporting and any release. PROPOSED: the first task KOS-MOTION-001 (Motion command and state contract), which is "NOT_STARTED (proposed, awaiting owner approval)" in [planning/TASKS.md](planning/TASKS.md). Source folders are added only when a real task needs them, so their absence is intended and is not a defect.

## 2. Position in the KritvaOS Ecosystem

Kritva Motion is one of the capability repositories planned for Kritva OS V2, next to the other capability repositories and above the platform foundation (kritva-core). It is planned and tracked from [kritva-program](https://github.com/KritvaOS/kritva-program). The roster, order and dependencies of repositories are owned by kritva-program (`v2/planning/repo-pipeline.json`), not by this README. Boundaries: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation.

## 3. Architecture

Not yet defined. The architecture and contract are the subject of task KOS-MOTION-001, which is proposed and not approved; its criteria are in [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) section 3. Until that task is approved and accepted there is no architecture document in this repository, and nothing in the planning files is an interface that other repositories may rely on. Interfaces are intended to be contract-first and versioned independently of program phases ([AGENTS.md](AGENTS.md)). Motion describes commands and limits for devices that move. The actuator hardware family is on HOLD in the program plan, no actuator is connected to anything in this repository, and nothing here validates physical behaviour: any claim about a physical limit, stop or fault response stays blocked by the program's physical-safety gate (V2-M6) and the human safety reviews recorded in kritva-program.

## 4. Documents to Read First

Role first, then the status the document declares. A label is a role, not an approval; where a document does not declare a status in its header, none is shown here.

| # | Document | Label, status | What it answers |
|---|---|---|---|
| 1 | [AGENTS.md](AGENTS.md) | AUTHORITATIVE for the rules for agents and contributors in this repository; in force | Scope, boundaries, commits, tests, tags |
| 2 | [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | AUTHORITATIVE for the acceptance criteria of KOS-MOTION-001; PROPOSED (not accepted, weighted or credited) | What the first task must satisfy |
| 3 | [planning/TASKS.md](planning/TASKS.md) | AUTHORITATIVE for this repository's task inventory (proposed registry, PD-004) | Which tasks exist and their status |
| 4 | [planning/MILESTONE.md](planning/MILESTONE.md) | REFERENCE: generated from kritva-program; dates are proposed targets, not approved | Proposed milestones |
| 5 | [planning/MILESTONE_STATUS.md](planning/MILESTONE_STATUS.md) | REFERENCE: the repository's own record, as of the governance baseline commit | Milestone status and evidence |
| 6 | [planning/REVIEW_CHECKLIST.md](planning/REVIEW_CHECKLIST.md) | AUTHORITATIVE for the pull-request review list | What a reviewer checks |
| 7 | [planning/GIT_COMMIT_STEP.md](planning/GIT_COMMIT_STEP.md) | REFERENCE | How to branch, commit, check, merge and tag |
| 8 | [planning/CHANGELOG.md](planning/CHANGELOG.md) | REFERENCE | What changed |
| 9 | [CONTRIBUTING.md](CONTRIBUTING.md) | AUTHORITATIVE for contribution steps | How to contribute |
| 10 | [SECURITY.md](SECURITY.md) | AUTHORITATIVE for vulnerability reporting (route not yet verified) | How to report a vulnerability |

## 5. Repository Structure and File Responsibilities

Labels: INPUT is edited by hand and read by a tool or review; GENERATED is written by a tool and never edited; EVIDENCE supports a claim; AUTHORITATIVE owns a rule; REFERENCE governs nothing. A label is a role, not an approval.

| Path | Content | Label, status | Notes |
|---|---|---|---|
| [planning/](planning/) | Tasks, milestones, milestone status, review checklist, commit step, changelog | MIXED: planning records | Governs execution and acceptance |
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | Criteria and test gates for KOS-MOTION-001 | AUTHORITATIVE; PROPOSED | Accepted criteria are never edited; a change is a new version |
| [scripts/](scripts/) | `docs_check.py` (link check), `pipeline/pr_gate.py` (PR gate), `security/` (commit checkers), `check_readme.py` (README check) | INPUT; IMPLEMENTED | `pipeline/` and `security/` are protected paths of the gate |
| [tests/](tests/) | `commit_message_check/` (commit checker tests) and `readme_check/` (README checker tests) | EVIDENCE; IMPLEMENTED | Tests of the checkers only; no test of the contract exists |
| [.github/](.github/) | CODEOWNERS, pull request template, `kritva-gate.json` and three workflows | AUTHORITATIVE | `kritva-gate.json` configures the PR gate |
| [Makefile](Makefile) | Check targets; unimplemented gates exit 3 | INPUT; IMPLEMENTED | See section 11 |
| [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [LICENSE](LICENSE) | Rules, contribution steps, security policy, licence | AUTHORITATIVE | |
| `src/`, `include/`, `docs/`, `status/`, `examples/` | Source, interfaces, documentation, status report, examples | NOT YET IMPLEMENTED (absent) | Added only when a real task needs them |

## 6. Toolchain and Development Workflow

| Tool | Purpose | Version | Check |
|---|---|---|---|
| Python 3 | Check scripts, PR gate, tests (standard library only) | 3.12 in CI; the scripts use only the standard library | `python3 --version` |
| GNU make | Convenience wrapper | any | `make --version` |
| Git | Branching and the commit checker | any | `git --version` |

There is no build, compiler or package toolchain because there is no implementation. Work follows [planning/GIT_COMMIT_STEP.md](planning/GIT_COMMIT_STEP.md): branch from an up-to-date `main`, commit with the format in section 12, run the checks, open a pull request.

```bash
make check          # check: required planning files exist; commit-message checker tests pass
make docs-check     # check: every relative Markdown link points to an existing file
make check-readme   # check: structural check of this README only
```

## 7. Dependencies and Interfaces

| Dependency | Direction | Kind | Contract | State |
|---|---|---|---|---|
| kritva-core | upstream | planned contract use; no Git submodule, build or runtime link | approved platform contract (planned) | PLANNED: no contract version is pinned and no source link exists |
| kritvaos-community | upstream | planned contract use; no Git submodule, build or runtime link | public architecture description | PLANNED: no pinned commit |
| kritva-actuator family | downstream or peer | planned contract use; no Git submodule, build or runtime link | none yet; the family is on HOLD | PLANNED: no interface exists |
| kritva-skill | downstream consumer | planned contract use; no Git submodule, build or runtime link | uses the versioned Motion contract | PLANNED: no consumer exists |

No dependency is established. The planned dependencies come from the repository's plan (kritva-core (approved contract), kritvaos-community (public architecture description)); exact versions or commit SHAs are to be recorded in [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) when the contracts they refer to are approved, and none is pinned yet. Five kinds of relationship are kept apart: program ordering, Git submodule, source or build dependency, runtime integration, and governance or status reporting. A PLANNED dependency is not an integration that exists.

## 8. Milestones and Implementation Plan

Proposed milestones, from [planning/MILESTONE.md](planning/MILESTONE.md) (generated from kritva-program `v2/planning/milestones.json`; edit them there) and the status recorded in [planning/MILESTONE_STATUS.md](planning/MILESTONE_STATUS.md):

| ID | Program milestone | Status recorded here | Outcome (proposed) |
|---|---|---|---|
| V2-M0-MOTION-001 | V2-M0 FOUNDATION | IN_REVIEW (this change) | Repository governance baseline merged: acceptance criteria, CI checks, CODEOWNERS, AGENTS.md. |
| V2-M1-MOTION-001 | V2-M1 STUDIO | PROPOSED | Motion command and state contract (task 001) reviewed and tagged v0.1.0. |
| V2-M2-MOTION-001 | V2-M2 BUILD & ARTIFACT | PROPOSED | Command validation, limit enforcement and fault-path tests pass; gates implemented. |
| V2-M5-MOTION-001 | V2-M5 EXECUTION | PROPOSED | Motion commands validated against a simulated actuator interface. |
| V2-M8-MOTION-001 | V2-M8 PRODUCTION | PROPOSED | Release and security review complete. |

The target dates are in [planning/MILESTONE.md](planning/MILESTONE.md); they are proposed targets, not approved dates and not delivery commitments (program decision PD-001). The status table is "as of the governance baseline commit" and may lag the repository (it shows the governance baseline as IN_REVIEW although the baseline change has since been merged). A milestone closes only through an approved `COMPLETION_RECORD.md`; a tag or a merge does not close it, and no completion record exists.

## 9. Tasks and Acceptance Criteria

- **Where tasks live.** [planning/TASKS.md](planning/TASKS.md) lists the tasks (registry type `repo-tasks-md`, prefix `KOS-MOTION`); the proposed task registry is program decision PD-004. Tasks are planning inventory with no weight and no credit until a separately approved baseline amendment.
- **Acceptance.** [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) holds the criteria and test gates; they are proposed until the owner approves the task. Unimplemented gates are reported as NOT_IMPLEMENTED and are never counted as a pass. [planning/REVIEW_CHECKLIST.md](planning/REVIEW_CHECKLIST.md) is the review list.
- Work is not accepted because a commit or merged pull request exists, a check is green or a milestone says it is proposed. Interface and boundary changes, safety and security behaviour and dependency changes need human review ([AGENTS.md](AGENTS.md)).

## 10. Status Reporting and Program Integration

Not yet implemented. This repository has no `status/` directory and generates no `status.json`. The program tracks its tasks through the registry named in `.github/kritva-gate.json` (`planning/TASKS.md`, type `repo-tasks-md`). This repository reports facts only and earns no program credit; nothing in it adds baseline weight (kritva-program decides baseline, weights, approvals and gates).

| Dimension | Source record | Authority |
|---|---|---|
| Execution | the task status in [planning/TASKS.md](planning/TASKS.md); KOS-MOTION-001 is NOT_STARTED | The task owner records it |
| Evidence | none recorded: no CI run, test result or review record is cited as task evidence | Evidence is recorded at acceptance, by the author, and checked by another reviewer |
| Acceptance | [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md), the review record and the central approvals in kritva-program | The independent reviewer and the owner, never a status report |
| Release readiness | not defined: no release, tag or completion record exists | The owner, through the central gates |

## 11. Build, Test, Regression and Validation

CI runs three workflows. `make check` is a local command and is not the same as CI.

| Workflow | Trigger | What it runs |
|---|---|---|
| `commit-message-check` | pull requests | the commit checker's unit tests, and the checker on the pull request's commits (rejects AI-session trailers and links only) |
| `pr-acceptance-gate` | pull requests | `scripts/pipeline/pr_gate.py static` against `.github/kritva-gate.json`: report-only rules R01 commit format, R02 task exists and is open, R03 acceptance criteria changed, R04 protected paths, R05 completion record, R06 required workflows, R07 required approvals, R08 dependencies. REJECT fails the check; NEEDS_HUMAN and APPROVE pass it; it posts or updates a report comment and approves and merges nothing |
| `secret-scan` | push to `main`; pull requests; manual dispatch | gitleaks over the git history |

| Command | Effect | Notes |
|---|---|---|
| `make check` | check | required planning files exist; the commit-message checker's unit tests run; it does not run `docs-check`, the PR gate or any contract test |
| `make docs-check` | check | every relative Markdown link points to an existing file (not an anchor check) |
| `make check-readme` | check | structural check of this README only (metadata, topics, relative links, placeholders); a PASS does not show the content is accurate; not part of `make check` or CI |
| `make lint`, `make test-unit`, `make test-integration`, `make test-regression`, `make test`, `make acceptance` | placeholder | print NOT_IMPLEMENTED and exit 3: they check nothing and are never a pass |
| `python3 scripts/security/check_commit_format.py --range origin/main..HEAD` | check | the commit format of the commits on a branch (the PR gate runs the same check as rule R01) |

There is nothing to build and no test of the contract, because there is no contract yet. A passing `make check` shows only that the listed files exist and that the commit checker's own tests pass. It does not show that a design is right, that a gate is closed or that anything is safe. `.github/kritva-gate.json` declares three required checks (`secret-scan`, `commit-message-check` and `pr-acceptance-gate`); that list is the gate's own declaration, not the branch ruleset. [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md) name only the first two as required. Which checks the `main` ruleset actually requires has not been verified from this README, and the three documents are not aligned; the owner decides and records it.

## 12. Git Workflow and Review

Controlling statement ([AGENTS.md](AGENTS.md) section 3, the D-053 form): header `type(scope): summary` (types feat, fix, docs, refactor, test, build, ci, chore, perf, revert, security; at most 90 characters; an optional `[KOS-MOTION-NNN]` suffix must match the footer), exactly one `Task:` or `Tasks:` footer line, and `Tasks: None (reason)` only on a docs or chore commit that implements no task; merge by merge commit; pull requests use `.github/PULL_REQUEST_TEMPLATE.md`. [CONTRIBUTING.md](CONTRIBUTING.md) repeats the same rule. Enforcement: `commit-message-check` rejects only AI-session trailers and links; the format (rule R01) is checked by the `pr-acceptance-gate` report, whose `.github/kritva-gate.json` records the commit standard as adopted (the PR gate treats a missing footer as a failure). Work on a branch and open a pull request; do not push to `main`. Required checks and approvals are in section 11; the Code Owner reviews ([.github/CODEOWNERS](.github/CODEOWNERS)); with one owner the PR author cannot self-approve, so use the owner bypass or a second reviewer.

## 13. Safety and Security

No implementation and no safety case exist at this planning stage: the repository contains no software that runs and no hardware, and it makes no safety claim. The planned contract can still influence what other software does, so its safety implications need human review when it is designed. The planning records state that any hardware-in-loop or physical validation claim stays gated on program milestone V2-M6 (HOLD) and that no architecture or safety reviewer was assigned when the criteria were written (program decision PD-007, since resolved on an interim basis by D-047: both roles are assigned to the owner). Software acceptance, tests, simulation and mocks are never described as hardware or safety validation. Motion describes commands and limits for devices that move. The actuator hardware family is on HOLD in the program plan, no actuator is connected to anything in this repository, and nothing here validates physical behaviour: any claim about a physical limit, stop or fault response stays blocked by the program's physical-safety gate (V2-M6) and the human safety reviews recorded in kritva-program.

**Reporting a vulnerability:** follow [SECURITY.md](SECURITY.md). It asks you to tell the Security Owner through an existing Kritva channel and to ask for a private place for details, and it mentions GitHub private vulnerability reporting if enabled. The Security Owner has not yet verified whether private vulnerability reporting is enabled or that the channel is monitored (an owner action pending). Never put details of an unfixed vulnerability in a public issue, pull request or commit message.

- Never commit secrets, private keys, tokens, passwords or production data. The `secret-scan` workflow runs on pull requests and on pushes to `main`.
- If a secret is committed by mistake, tell the Security Owner at once; removing it in a later commit does not make it safe.

## 14. Release and Versioning

No release exists and no version is defined. The plan is annotated SemVer tags (`vMAJOR.MINOR.PATCH`) created only after the approved merge, with contracts versioned independently of program phases and a MAJOR version for a breaking contract change ([AGENTS.md](AGENTS.md) sections 2 and 6). A milestone closes only through an approved completion record. This README records no release state.

## 15. Ownership and Escalation

| Role | Responsibility |
|---|---|
| Repository owner (Dinesh; `.github/CODEOWNERS`) | Directs the work, decides, approves and merges |
| Security Owner | Handles vulnerability reports and committed secrets |
| Architecture reviewer and safety reviewer | Both roles are assigned to the owner on an interim basis (D-047); that is not independent review, and the independence requirement remains unmet; the CODEOWNERS comments still say no reviewer is assigned |
| Implementers (people and agents) | Implement approved scope, record evidence and follow `AGENTS.md` |

## 16. Related Repositories and References

| Repository | Relationship |
|---|---|
| [kritva-program](https://github.com/KritvaOS/kritva-program) | Program plan, baseline, decisions, repository pipeline, README standard |
| [kritva-core](https://github.com/KritvaOS/kritva-core) | Platform foundation (planned dependency) |
| [kritvaos-community](https://github.com/KritvaOS/kritvaos-community) | Public architecture description (planned dependency) |

## 17. License

The [LICENSE](LICENSE) file is the Apache License 2.0. Copyright (c) 2026 KritvaOS. [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) section 9 says that the licence for this repository is undecided (program decision PD-013); the two statements are not reconciled, and the owner decides which stands.
