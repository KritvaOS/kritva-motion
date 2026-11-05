# KOS-MOTION-002: Command validation, limit enforcement and fault-path tests

Status (revision 2): IN_PROGRESS since 2026-11-05; KOS-MOTION-001 was accepted the same day, so the dependency is met. Work proceeds in small pull requests (see section 8). Owner approval recorded in chat on 2026-11-04 (Dinesh), program decision D-100. Milestone: V2-M2-MOTION-001. Acceptance begins after KOS-MOTION-001 is accepted; the program baseline has no dependency field, so the dependency is enforced here.
Task owner: Dinesh (repository owner). Architecture and safety reviewer roles: Dinesh, interim (D-047); independent review is not in place.
The task is in program baseline v9 (weight 5) and earns credit only through a central approval with passing evidence. Motion reports facts only.

## 1. Scope

A software-only reference validator for the Motion contract v0.1.0 and the tests that run it, in Python 3.12.

| Deliverable | Notes |
|---|---|
| Configuration validator | Contract section 3; may report several violations |
| Command admission validator | Fixed order of contract 8.4; first failure only; deterministic sub-order inside a step, documented in this task record |
| `AdmissionContext` | One read-only input structure: command envelope and version, supplied identity and permission results, idempotency lookup result, active configuration, supplied target, command and fault records, backend health and capabilities, joint-state snapshot, supplied monotonic reference time |
| Result structure | Accepted or rejected, first error code, step or field, optional message; no command ID, no state change |
| Limit enforcement | Contract 8.3 intersection of backend, configuration and command limits |
| State preconditions | Contract 8.6 exemption matrix and 13.6 `CLEAR_FAULT` preconditions on a supplied snapshot; read and query authorization on a separate path |
| Schema tests | The five schemas with positive and negative documents, run by `make test-unit` |
| Test manifest and mapping | Each of the conformance test IDs marked IN_SCOPE, DEFERRED or OUT_OF_SCOPE; IN_SCOPE IDs mapped to executable tests |
| `make test-unit` | A real gate; the `unit-tests` workflow and required check are added in separate changes (Makefile and `.github/` are protected paths) |

Toolchain (D-100): standard-library validator; JSON Schema Draft 2020-12 conformance through a pinned test-only `jsonschema` dependency with pinned transitive dependencies (hashes preferred), local schema references, offline runs. No home-grown or vendored partial schema engine.

## 2. Out of scope

The runtime lifecycle, termination and fault state machine, CLEAR_FAULT execution and recovery (candidate KOS-MOTION-003, not registered); integration and regression gates; the Execution Backend Interface implementation; simulators; any physical adapter, firmware, Mind or Skill integration; any hardware-in-loop or physical safety validation (gate V2-M6, HOLD). Core authentication and authorization are not implemented: the validator evaluates supplied results. Acceleration command semantics are not added: `LIMIT_ACCELERATION` is reserved (contract 8.3, MOTION-AD-045).

## 3. Acceptance mapping

Criteria AC-201 to AC-207 are in [ACCEPTANCE_CRITERIA.md](../../ACCEPTANCE_CRITERIA.md) section 3A and are proposed until accepted. The tests show correct decisions for a supplied, structurally valid context. They do not show that a live snapshot is current, that commands cannot race, that a backend is authoritative, that termination occurs or that a fault propagates.

## 4. Dependencies

| Dependency | State |
|---|---|
| KOS-MOTION-001 accepted | Required before acceptance of this task; the contract is PROPOSED |
| MOTION status source in kritva-program | Registered before the baseline freeze (D-100) |
| `unit-tests` workflow and required check | Added in kritva-motion, then recorded centrally (as D-097) |
| kritva-core security interface | Not pinned; authorization is a supplied input |

## 5. Risks and open items

1. The V2-M2-MOTION-001 outcome ("gates implemented") needs clarification through the program process; this task alone does not close it.
2. Self-approval under D-047: review is interim and not independent.
3. The task title says fault-path tests; only admission-time fault, degraded and unknown cases belong here.
4. Weights (5, an initial planning estimate) are set by the program baseline, not by this record.

## 6. Review and evidence

Required approvals follow `.github/kritva-gate.json` (REPO_CODE_OWNER and ARCHITECTURE_REVIEWER, both Dinesh, interim). Required checks on the exact closing commit: secret-scan, commit-message-check, pr-acceptance-gate, plus `unit-tests` once added. Evidence references are commit SHAs and CI run IDs, never branch names. Closure needs an approved completion record and an annotated SemVer tag per the program acceptance standard.

## 8. Delivery plan (proposed, small pull requests)

Each step is its own pull request with one `Task: KOS-MOTION-002` footer. The plan is a working order and is not an acceptance record; steps may be merged or split during review.

| Step | Content | Notes |
|---|---|---|
| 1 | Start of work (this change) | Status IN_PROGRESS only |
| 2 | Test scaffolding: pinned test-only dependency list, schema tests (AC-205) | No `Makefile` change; run with `python3 -m unittest` |
| 3 | Configuration validator and tests (AC-201) | Contract section 3 |
| 4 | Admission validator, `AdmissionContext`, limits and sub-order (AC-202, AC-203) | Contract 8.3 and 8.4; sub-order documented here |
| 5 | State preconditions and the read and query path (AC-204) | Contract 8.6 and 13.6 |
| 6 | Test manifest and mapping (AC-206) | Every conformance ID marked |
| 7 | `make test-unit` and the `unit-tests` workflow (AC-205, AC-206 gate) | `Makefile` and `.github/` are protected paths: owner-merged; the central required-check decision follows (as D-097) |
| 8 | Documentation of the software-evidence limit and acceptance (AC-207) | Owner review, not independent (D-047) |

## 7. Commit rules

`type(scope): summary` with one `Task: KOS-MOTION-002` footer. No AI-session trailer or link (AGENTS.md section 3). Branch and pull request; no push to `main`.
