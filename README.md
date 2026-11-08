# kritva-motion

> Planning and governance repository for the Motion command and state contract of the Kritva OS V2 plan. There is no implementation yet: the repository holds acceptance criteria, planning records, pull-request checks and rules, and no source code. The visibility class of this repository is PUBLIC (D-063).

| Property | Value |
|---|---|
| Project | KritvaOS (Kritva OS V2) |
| Repository | `KritvaOS/kritva-motion` |
| Repository Type | Capability (contract only; planning baseline, no implementation) |
| Visibility Class | PUBLIC (owner decision D-063 in kritva-program; it is an exception to the D-039 recommendation of PRIVATE, and no release review is recorded) |
| GitHub Setting | PUBLIC, the same as the class (D-063 in kritva-program keeps this repository public and takes it out of the return-to-private plan); OWNER-ATTESTED: no independent check of the setting and no verification date is recorded here |
| Lifecycle Status | PLANNING (governance baseline only) |
| Repository Owner | Project owner (role; see section 15) |
| Security Owner | Security Owner role ([SECURITY.md](SECURITY.md)) |
| Architecture | PROPOSED draft, not approved: [architecture/MOTION_ARCHITECTURE.md](architecture/MOTION_ARCHITECTURE.md) and the contract [contract/MOTION_CONTRACT.md](contract/MOTION_CONTRACT.md), task KOS-MOTION-001 (criteria in [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)) |
| Milestones | [planning/MILESTONE.md](planning/MILESTONE.md) and [planning/MILESTONE_STATUS.md](planning/MILESTONE_STATUS.md) |
| Tasks | [planning/TASKS.md](planning/TASKS.md) |
| Acceptance Criteria | [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) |
| Status Reporting | Generated `status/status.json` (schema 2.0) by `scripts/status/gen_status.py`; the report lists the two baselined Motion tasks and no evidence of acceptance (see section 10) Generated progress view: [status/STATUS.md](status/STATUS.md) (see section 10). |
| License | [LICENSE](LICENSE) (Apache License 2.0; see section 17 for an open question) |

This README follows the Kritva README standard (`v2/planning/standards/README_STANDARD.md` in [kritva-program](https://github.com/KritvaOS/kritva-program)). It is a navigation map; the documents it links own the detail.

## 1. Purpose and Scope

Kritva Motion is the part of Kritva OS V2 that will own the Motion command and state contract. Today this repository only plans that work.

**This repository owns** (as planned): the motion command and state contract: command lifecycle, units, limits, feedback, timeout, cancellation, fault behaviour and the safety boundary of the contract.

**This repository does not own**: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation.

**Implementation state.** IMPLEMENTED: the governance baseline (planning records, acceptance criteria, pull-request workflows and scripts, the commit-message checker, the `Makefile` structure check), status reporting, and for task KOS-MOTION-002 a software-only reference validator of the Motion contract under [src/kritva_motion/](src/kritva_motion/) (configuration validation and command admission, standard library only, no I/O toward a backend or device), the schema, validator, gate and conformance tests under [tests/](tests/), a conformance manifest and `make test-unit` with its `unit-tests` workflow. Milestone V2-M2-MOTION-001 is closed by [COMPLETION_RECORD.md](COMPLETION_RECORD.md) (program decisions D-104 and D-105). NOT YET IMPLEMENTED: a Motion runtime, an activation path, an idempotency store, events and history, a backend interface or simulator, integration and regression gates (deferred by D-105), and any release. 50 of the 124 conformance IDs are DEFERRED to later tasks and 5 are out of scope ([manifest](tests/manifest/conformance_manifest.json)); they are never counted as passed. PROPOSED: the draft contract package of KOS-MOTION-001, which the owner accepted on 2026-11-05 ([planning/TASKS.md](planning/TASKS.md), [review record](tasks/KOS-MOTION-001/REVIEW.md)); KOS-MOTION-002 was accepted by the owner on 2026-11-06 ([review record](tasks/KOS-MOTION-002/REVIEW.md); software evidence only); the contract stays a draft and is untagged, so it is not yet an interface other repositories may rely on. Passing tests is software evidence only, never physical or safety validation.

## 2. Position in the KritvaOS Ecosystem

Kritva Motion is one of the capability repositories planned for Kritva OS V2, next to the other capability repositories and above the platform foundation (kritva-core). It is planned and tracked from [kritva-program](https://github.com/KritvaOS/kritva-program). The roster, order and dependencies of repositories are owned by kritva-program (`v2/planning/repo-pipeline.json`), not by this README. Boundaries: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation.

## 3. Architecture

A draft architecture and contract are PROPOSED under task KOS-MOTION-001 and are not approved: [architecture/MOTION_ARCHITECTURE.md](architecture/MOTION_ARCHITECTURE.md), the decision register [architecture/MOTION_DECISIONS.md](architecture/MOTION_DECISIONS.md) and the normative draft contract [contract/MOTION_CONTRACT.md](contract/MOTION_CONTRACT.md) with its schemas, [error codes](contract/ERROR_CODES.md) and [conformance test plan](contract/CONFORMANCE_TEST_PLAN.md). The criteria are in [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) section 3. Until the task is reviewed and accepted, nothing in these documents is an interface that other repositories may rely on, and no runtime, simulator or physical validation exists. Interfaces are intended to be contract-first and versioned independently of program phases ([AGENTS.md](AGENTS.md)). Motion describes commands and limits for devices that move. The actuator hardware family is on HOLD in the program plan, no actuator is connected to anything in this repository, and nothing here validates physical behaviour: any claim about a physical limit, stop or fault response stays blocked by the program's physical-safety gate (V2-M6) and the human safety reviews recorded in kritva-program.

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
| 10 | [SECURITY.md](SECURITY.md) | AUTHORITATIVE for vulnerability reporting (route tested 18 October 2026, owner-attested) | How to report a vulnerability |

## 5. Repository Structure and File Responsibilities

Labels: INPUT is edited by hand and read by a tool or review; GENERATED is written by a tool and never edited; EVIDENCE supports a claim; AUTHORITATIVE owns a rule; REFERENCE governs nothing. A label is a role, not an approval.

| Path | Content | Label, status | Notes |
|---|---|---|---|
| [planning/](planning/) | Tasks, milestones, milestone status, review checklist, commit step, changelog | MIXED: planning records | Governs execution and acceptance |
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | Criteria and test gates for KOS-MOTION-001 (section 3) and KOS-MOTION-002 (section 3A) | AUTHORITATIVE; PROPOSED | Accepted criteria are never edited; a change is a new version |
| [architecture/](architecture/) | Draft architecture and decision register (MOTION-AD-001 to 045) | INPUT; PROPOSED | Not approved; the contract is the normative text |
| [contract/](contract/) | Draft Motion contract v0.1.0, five JSON schemas, error codes, conformance test plan | AUTHORITATIVE for the contract once approved; PROPOSED | Schema checks only; no runtime exists |
| [tasks/](tasks/KOS-MOTION-001/TASK.md) | Task record and proposed acceptance-criteria amendments for KOS-MOTION-001 | INPUT; PROPOSED | Amendments are not adopted |
| [scripts/](scripts/) | `docs_check.py` (link check), `pipeline/pr_gate.py` (PR gate), `security/` (commit checkers), `check_readme.py` (README check), `status/gen_status.py` (status generator and checker), `test_gate.py` (unit-test gate and conformance manifest check) | INPUT; IMPLEMENTED | `pipeline/` and `security/` are protected paths of the gate |
| [tests/](tests/) | `commit_message_check/`, `readme_check/` and `status_gen/` (tooling tests), `schema/` (the five contract schemas), `validator/` (reference validator and one conformance test per IN_SCOPE ID), `lifecycle/` (lifecycle engine, KOS-MOTION-003 PR-02 to PR-04), `gate/` (the test gate's own tests) and `manifest/conformance_manifest.json` | EVIDENCE; IMPLEMENTED | Software evidence only; deterministic, offline; DEFERRED IDs have no test |
| [.github/](.github/) | CODEOWNERS, pull request template, `kritva-gate.json` and five workflows | AUTHORITATIVE | `kritva-gate.json` configures the PR gate |
| [Makefile](Makefile) | Check targets; unimplemented gates exit 3 | INPUT; IMPLEMENTED | See section 11 |
| [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [LICENSE](LICENSE) | Rules, contribution steps, security policy, licence | AUTHORITATIVE | |
| [status/](status/) | `status.json` (GENERATED report, schema 2.0), the vendored `status.schema.json` and its recorded SHA-256 | GENERATED; IMPLEMENTED | Reports facts only; never edit `status.json` by hand |
| [src/kritva_motion/](src/kritva_motion/) | Reference validator: `config_validation.py`, `admission.py`; `lifecycle/` (pure in-memory lifecycle engine, KOS-MOTION-003 PR-02 to PR-04; standard library only) | IMPLEMENTED | Validates supplied data only; no runtime process, no I/O toward a backend or device; the lifecycle engine runs only on supplied inputs |
| `include/`, `docs/`, `examples/` | Interfaces, documentation, examples | NOT YET IMPLEMENTED (absent) | Added only when a real task needs them |

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
| V2-M2-MOTION-001 | V2-M2 BUILD & ARTIFACT | PROPOSED | Command and configuration validation, limit enforcement and admission-time fault-path tests pass; unit, integration and regression gates implemented. The runtime lifecycle, termination and fault state machine is a separate task. |
| V2-M5-MOTION-001 | V2-M5 EXECUTION | PROPOSED | Motion commands validated against a simulated actuator interface. |
| V2-M8-MOTION-001 | V2-M8 PRODUCTION | PROPOSED | Release and security review complete. |

The target dates are in [planning/MILESTONE.md](planning/MILESTONE.md); they are proposed targets, not approved dates and not delivery commitments (program decision PD-001). The status table is "as of the governance baseline commit" and may lag the repository (it shows the governance baseline as IN_REVIEW although the baseline change has since been merged). A milestone closes only through an approved `COMPLETION_RECORD.md`; a tag or a merge does not close it, and no completion record exists.

## 9. Tasks and Acceptance Criteria

- **Where tasks live.** [planning/TASKS.md](planning/TASKS.md) lists the tasks (registry type `repo-tasks-md`, prefix `KOS-MOTION`); the proposed task registry is program decision PD-004. Tasks are planning inventory with no weight and no credit until a separately approved baseline amendment.
- **Acceptance.** [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) holds the criteria and test gates; they are proposed until the owner approves the task. Unimplemented gates are reported as NOT_IMPLEMENTED and are never counted as a pass. [planning/REVIEW_CHECKLIST.md](planning/REVIEW_CHECKLIST.md) is the review list.
- Work is not accepted because a commit or merged pull request exists, a check is green or a milestone says it is proposed. Interface and boundary changes, safety and security behaviour and dependency changes need human review ([AGENTS.md](AGENTS.md)).

## 10. Status Reporting and Program Integration

**Progress view.** [status/STATUS.md](status/STATUS.md) is a generated progress view: a bar of accepted weight, with execution, evidence, acceptance and release readiness kept apart. `scripts/progress_report.py` renders it from the pinned snapshot `status/program_snapshot.json`, which kritva-program writes (`tools/publish_repo_progress.py`, decision D-120). The `progress-check` workflow runs on pull requests and on pushes to main, runs `python3 scripts/progress_report.py --check` (read-only), and fails when the report and the snapshot differ. The view is a derived snapshot of the program and can lag it; it records no acceptance, and its figures are not repeated in this README (README standard, rule 4).

`status/status.json` (schema 2.0) is generated by `python3 scripts/status/gen_status.py --write` and checked by `--check`; the generator reports facts only and fails closed on a missing, duplicate or unrecognised task status. It reports the two baselined tasks (KOS-MOTION-001 and KOS-MOTION-002, kritva-program baseline v9, D-100): execution comes from the status word in `planning/TASKS.md`, evidence is a criteria reference only until a task is ACCEPTED, when it is the passing CI runs recorded in the task's `EVIDENCE.json` (the generator fails closed on a missing or malformed record), and the report is never itself the acceptance. Credit comes only from a central approval with passing evidence. The program tracks its tasks through the registry named in `.github/kritva-gate.json` (`planning/TASKS.md`, type `repo-tasks-md`). This repository reports facts only and earns no program credit; nothing in it adds baseline weight (kritva-program decides baseline, weights, approvals and gates).

| Dimension | Source record | Authority |
|---|---|---|
| Execution | the task status in [planning/TASKS.md](planning/TASKS.md); KOS-MOTION-001 is ACCEPTED (owner, 2026-11-05) and KOS-MOTION-002 is ACCEPTED (owner, 2026-11-06) | The task owner records it |
| Evidence | KOS-MOTION-001: [tasks/KOS-MOTION-001/EVIDENCE.json](tasks/KOS-MOTION-001/EVIDENCE.json) cites three passing repository checks on the reviewed commit, and [REVIEW.md](tasks/KOS-MOTION-001/REVIEW.md) is the owner review; KOS-MOTION-002: [EVIDENCE.json](tasks/KOS-MOTION-002/EVIDENCE.json) cites three passing repository checks (including `unit-tests`) and [REVIEW.md](tasks/KOS-MOTION-002/REVIEW.md) is the owner review. They are not runtime tests. | Evidence is recorded at acceptance, by the author; the review is the owner's and is not independent |
| Acceptance | [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md), the review record and the central approvals in kritva-program | The independent reviewer and the owner, never a status report |
| Release readiness | not defined: no release, tag or completion record exists | The owner, through the central gates |

## 11. Build, Test, Regression and Validation

CI runs five workflows. `make check` is a local command and is not the same as CI.

| Workflow | Trigger | What it runs |
|---|---|---|
| `commit-message-check` | pull requests | the commit checker's unit tests, and the checker on the pull request's commits (rejects AI-session trailers and links only) |
| `pr-acceptance-gate` | pull requests | `scripts/pipeline/pr_gate.py static` against `.github/kritva-gate.json`: report-only rules R01 commit format, R02 task exists and is open, R03 acceptance criteria changed, R04 protected paths, R05 completion record, R06 required workflows, R07 required approvals, R08 dependencies. REJECT fails the check; NEEDS_HUMAN and APPROVE pass it; it posts or updates a report comment and approves and merges nothing |
| `readme-check` | pull requests; push to `main` | the README checker's unit tests, then `python3 scripts/check_readme.py README.md` (structure, metadata and local links only; a required check, D-106) |
| `unit-tests` | pull requests; push to `main` | `make test-unit` after installing the pinned `requirements-test.txt` (a required check, D-104; the `main` ruleset requires it, verified by read-back on 2026-11-06) |
| `secret-scan` | push to `main`; pull requests; manual dispatch | gitleaks over the git history |

| Command | Effect | Notes |
|---|---|---|
| `make check` | check | required planning files exist; the commit-message checker's unit tests run; it does not run `docs-check`, the PR gate or any contract test |
| `make docs-check` | check | every relative Markdown link points to an existing file (not an anchor check) |
| `make check-readme` | check | structural check of this README only (metadata, topics, relative links, placeholders); a PASS does not show the content is accurate; not part of `make check` or CI |
| `make test-unit` | check | runs the unit tests (schemas, validators, gate, status generator) and checks the conformance manifest against the plan (`scripts/test_gate.py`); needs `requirements-test.txt` installed (`PYTHON=...` selects the interpreter); software evidence only, never physical or safety validation |
| `make lint`, `make test-integration`, `make test-regression`, `make test`, `make acceptance` | placeholder | print NOT_IMPLEMENTED and exit 3: they check nothing and are never a pass |
| `python3 scripts/security/check_commit_format.py --range origin/main..HEAD` | check | the commit format of the commits on a branch (the PR gate runs the same check as rule R01) |

There is nothing to build. `make test-unit` runs the tests of the reference validator and checks the conformance manifest against the plan; a pass is software evidence for the IN_SCOPE conformance IDs only, never physical or safety validation, and it says nothing about DEFERRED IDs, the runtime, a backend or hardware. A passing `make check` shows only that the listed files exist and that the commit checker's own tests pass. It does not show that a design is right, that a gate is closed or that anything is safe. `.github/kritva-gate.json` declares five required checks (`secret-scan`, `commit-message-check`, `pr-acceptance-gate`, `unit-tests` and `readme-check`); that list is the gate's own declaration, not the branch ruleset. [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md) now name the same five. The owner decided that `pr-acceptance-gate` is a required check in the `main` ruleset (PD-018, D-061); the owner states that it has been added to the `main` ruleset (D-069); that is OWNER-ATTESTED and not independently verified from this README. `unit-tests` was added as a fourth required check by program decision D-104; the owner added it to the `main` ruleset and a read-back on 2026-11-06 listed secret-scan, commit-message-check, readme-check, pr-acceptance-gate and unit-tests, so for `unit-tests` the ruleset is verified, not attested. The ruleset also requires `readme-check`; program decision D-106 aligns `kritva-gate.json`, AGENTS.md, CONTRIBUTING.md and the central manifest with it (D-067 had kept it out of every ruleset until a later owner decision). A read-back on 2026-11-06 listed it.

## 12. Git Workflow and Review

Controlling statement ([AGENTS.md](AGENTS.md) section 3, the D-053 form): header `type(scope): summary` (types feat, fix, docs, refactor, test, build, ci, chore, perf, revert, security; at most 90 characters; an optional `[KOS-MOTION-NNN]` suffix must match the footer), exactly one `Task:` or `Tasks:` footer line, and `Tasks: None (reason)` only on a docs or chore commit that implements no task; merge by merge commit; pull requests use `.github/PULL_REQUEST_TEMPLATE.md`. [CONTRIBUTING.md](CONTRIBUTING.md) repeats the same rule. Enforcement: `commit-message-check` rejects only AI-session trailers and links; the format (rule R01) is checked by the `pr-acceptance-gate` report, whose `.github/kritva-gate.json` records the commit standard as adopted (the PR gate treats a missing footer as a failure). Work on a branch and open a pull request; do not push to `main`. Required checks and approvals are in section 11; the Code Owner reviews ([.github/CODEOWNERS](.github/CODEOWNERS)); with one owner the PR author cannot self-approve, so use the owner bypass or a second reviewer.

## 13. Safety and Security

No safety case exists. The repository contains a software-only reference validator that reads supplied data and performs no I/O toward a backend or device (an AST test forbids it), no Motion runtime and no hardware, and it makes no safety claim. The planned contract can still influence what other software does, so its safety implications need human review when it is designed. The planning records state that any hardware-in-loop or physical validation claim stays gated on program milestone V2-M6 (HOLD) and that no architecture or safety reviewer was assigned when the criteria were written (program decision PD-007, since resolved on an interim basis by D-047: both roles are assigned to the owner). Software acceptance, tests, simulation and mocks are never described as hardware or safety validation. Motion describes commands and limits for devices that move. The actuator hardware family is on HOLD in the program plan, no actuator is connected to anything in this repository, and nothing here validates physical behaviour: any claim about a physical limit, stop or fault response stays blocked by the program's physical-safety gate (V2-M6) and the human safety reviews recorded in kritva-program.

**Reporting a vulnerability:** follow [SECURITY.md](SECURITY.md). It names GitHub private vulnerability reporting as the first route and gives a direct-contact fallback. The Security Owner reports having tested the reporting route on 18 October 2026 (D-068); that is ATTESTED, not independently verified, and nothing here promises a response time. Never put details of an unfixed vulnerability in a public issue, pull request or commit message.

- Never commit secrets, private keys, tokens, passwords or production data. The `secret-scan` workflow runs on pull requests and on pushes to `main`.
- If a secret is committed by mistake, tell the Security Owner at once; removing it in a later commit does not make it safe.

## 14. Release and Versioning

No release exists and no version is defined. The plan is annotated SemVer tags (`vMAJOR.MINOR.PATCH`) created only after the approved merge, with contracts versioned independently of program phases and a MAJOR version for a breaking contract change ([AGENTS.md](AGENTS.md) sections 2 and 6). A milestone closes only through an approved completion record. This README records no release state.

## 15. Ownership and Escalation

| Role | Responsibility |
|---|---|
| Repository owner (Dinesh; `.github/CODEOWNERS`) | Directs the work, decides, approves and merges |
| Security Owner | Handles vulnerability reports and committed secrets |
| Architecture reviewer and safety reviewer | Both roles are assigned to the owner on an interim basis (D-047); that is not independent review, and the independence requirement remains unmet; the CODEOWNERS comments say the same (D-065) |
| Implementers (people and agents) | Implement approved scope, record evidence and follow `AGENTS.md` |

## 16. Related Repositories and References

| Repository | Relationship |
|---|---|
| [kritva-program](https://github.com/KritvaOS/kritva-program) | Program plan, baseline, decisions, repository pipeline, README standard |
| [kritva-core](https://github.com/KritvaOS/kritva-core) | Platform foundation (planned dependency) |
| [kritvaos-community](https://github.com/KritvaOS/kritvaos-community) | Public architecture description (planned dependency) |

## 17. License

The [LICENSE](LICENSE) file is the Apache License 2.0. Copyright (c) 2026 KritvaOS. The owner confirmed Apache-2.0 as the licence of this repository (program decision D-064, which closes PD-013), and [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) section 9 says the same.
