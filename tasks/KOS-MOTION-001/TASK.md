# KOS-MOTION-001: Motion command and state contract

Status (revision 4): owner approval recorded in chat on 2026-11-02 (Dinesh). Start of work is not yet recorded in `planning/TASKS.md` or in kritva-program; see "Records to update". Milestone: V2-M1-MOTION-001 (program target 2026-11-30, a proposed target and not a commitment).
Task owner: Dinesh (repository owner). Architecture and safety reviewer roles: Dinesh, interim (D-047); independent review is not in place.
This task earns no program credit: Motion is not in the approved program baseline and this repository reports facts only.

## 1. Scope

Deliver the architecture and the normative v0.1.0 Motion command and state contract for joint-level position and velocity control, with an extensible, versioned model.

Deliverables, all in this task:

| Deliverable | Path |
|---|---|
| Decision register (reconciled, PROPOSED) | `architecture/MOTION_DECISIONS.md` |
| Architecture, components, ownership, data flow | `architecture/MOTION_ARCHITECTURE.md` |
| Normative contract v0.1.0 | `contract/MOTION_CONTRACT.md` |
| Schemas: command, submission result, command status, joint state, event | `contract/*.schema.json` |
| Error, reason and fault codes | `contract/ERROR_CODES.md` |
| Execution Backend Interface specification | `contract/MOTION_CONTRACT.md` section 17 |
| Conformance test plan | `contract/CONFORMANCE_TEST_PLAN.md` |
| Acceptance mapping and proposed amendments | this file, `AC_AMENDMENT_PROPOSALS.md` |
| Changelog entry | `planning/CHANGELOG.md` |

## 2. Out of scope

Runtime command manager and lifecycle code, backend registry, simulators (S1, S2, S3), physical actuator adapter, firmware, Mind and Skill integration, joint_group, end_effector and robot targets, trajectories, multi-joint coordination, multiple priority levels, torque and current control, and any physical or safety validation. Each belongs to later tasks proposed through kritva-program. No task ID, weight or date for them is approved by this task.

## 3. Acceptance mapping

`ACCEPTANCE_CRITERIA.md` is unchanged. Gates: `make check` and `make docs-check` apply; `make test-unit`, `make test-integration` and `make test-regression` remain NOT_IMPLEMENTED and are never a pass.

| Criterion | Where satisfied | Evidence to record at acceptance |
|---|---|---|
| AC-001 lifecycle and allowed transitions | Contract section 7 | Review record; schema tests CT-SCH-04 run against the schemas |
| AC-002 units, limits, enforced validation, defined error | Contract sections 3, 5, 8; [ERROR_CODES](../../contract/ERROR_CODES.md). The limits-per-command wording is open: see A-2 in `AC_AMENDMENT_PROPOSALS.md` | Review record; schema tests; owner decision on A-2 |
| AC-003 timeout, cancellation, fault, state after fault | Contract sections 6, 9, 10, 13 (termination record, two-dimension joint state, STOP and CLEAR_FAULT semantics) | Review record |
| AC-004 safety boundary | Contract sections 2.2, 17.7; architecture section 3 | Safety review by the safety reviewer (interim, not independent) |
| AC-005 transport and drivers below the contract | Contract sections 2.1, 14.2, 17 | Review record |

Because no runtime exists, the lifecycle, validation and fault criteria are verified at this stage by contract review, a cross-check review and schema validation (evidence classes in `contract/CONFORMANCE_TEST_PLAN.md` section 0). Schema tests alone do not show that lifecycle, race, authorization or termination behaviour is correct. Runtime verification is specified in the conformance plan and happens in later tasks. This limitation is stated in `ACCEPTANCE_CRITERIA.md` section 9 and is not converted into a pass.

## 4. Dependencies

| Dependency | State |
|---|---|
| kritva-core approved security interface | Not pinned; blocks freezing contract section 16 |
| kritva-core platform contract, kritvaos-community architecture | Not pinned; versions or SHAs recorded in `ACCEPTANCE_CRITERIA.md` when approved |
| kritva-sense | Peer; the sensing feedback relationship is out of this task |
| kritva-actuator | Downstream of the Execution Backend Interface; on HOLD |

## 5. Risks and open items

1. Unpinned Core security interface: the contract's authorization section stays PROVISIONAL.
2. Which faults need human or safety-authority action (contract 13.6, 19): needs the safety reviewer; independence is unmet.
3. Retention minimums and the public API form (library, messages or both) are open (contract 19). Position control of continuous revolute joints is reserved, not defined.
4. The AC-002 wording question (A-2) needs an owner decision.
5. Interface decisions need entries in kritva-program `v2/DECISIONS.md`.
6. The V2-M1 target leaves about four weeks; scope is bounded by the deliverables above.

## 6. Review and evidence

Required approvals follow `.github/kritva-gate.json`: REPO_CODE_OWNER and ARCHITECTURE_REVIEWER (both Dinesh, interim; with one owner the author cannot self-approve, so the owner bypass or a second reviewer is needed). Required checks on the exact closing commit: secret-scan, commit-message-check, pr-acceptance-gate. Evidence references are commit SHAs and CI run IDs, never branch names. The task is done only under the program Definition of Done (`ACCEPTANCE_CRITERIA.md` section 8).

## 7. Records to update when work starts

1. `planning/TASKS.md`: set the status of KOS-MOTION-001 from NOT_STARTED to IN_PROGRESS (a change recorded by the task owner).
2. kritva-program: record the owner's approval and the decisions in `v2/DECISIONS.md`, and reconcile the MOTION workstream registration (`workstreams.json` has `MOTION.repo` null) if the owner wants it.
3. README sections 1, 3 and 10 currently say no architecture exists; update them when the documents merge and run `make check-readme`.
4. Folders `architecture/`, `contract/` and `tasks/KOS-MOTION-001/` are created because this task needs them; the rule against empty folders is respected.
5. Commit format: `type(scope): summary` with one `Task: KOS-MOTION-001` footer. No AI-session trailer or link (AGENTS.md section 3). Branch, pull request, no push to `main`.
