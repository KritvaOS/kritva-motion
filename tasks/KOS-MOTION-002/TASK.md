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

## 7. Commit rules

`type(scope): summary` with one `Task: KOS-MOTION-002` footer. No AI-session trailer or link (AGENTS.md section 3). Branch and pull request; no push to `main`.

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

## 9. Configuration validator: shape and interpretations (step 3)

Code: `src/kritva_motion/config_validation.py`; tests: `tests/validator/test_config_validation.py`. Run: `python3 -m unittest discover -s tests/validator`.

- The contract lists the configuration fields (3.1) but defines no serialization. The validator takes plain data (dicts and lists) in the shape documented at the top of the module. This shape is a task decision, not a contract rule.
- Violations carry a `rule` name, the contract section, the path and a message. The contract defines no error code for configuration activation (3.2), so these names are not contract error codes. `ERROR_CODES.md` is unchanged.
- Interpretations for owner review (not stated in the contract text): (a) unknown fields are refused, to catch misspelled settings; (b) a joint mode or joint type the declared backend capabilities do not list is a policy the backend cannot satisfy; (c) listing `HOLD` in a degradation policy when the backend declares no position hold is refused as a policy that can never be used (13.8 also checks hold support on every admission); (d) a non-continuous joint needs `position_min` below `position_max`; `continuous: true` is refused for a prismatic joint and with position limits; (e) `settling_duration_ms` may be zero, the other durations must be positive.
- The validator checks the configuration only. It does not activate, version-bind or digest a configuration: there is no activation runtime in this task.

## 10. Admission validator, steps 1 to 9: decisions and findings (step 4)

Code: `src/kritva_motion/admission.py` (standard library only); tests: `tests/validator/test_admission.py` and, with the test-only `jsonschema` dependency, `tests/schema/test_envelope_mirror.py`. Steps 10 (joint state and preconditions) and 11 (arbitration) are later changes: until then `admit()` raises `NotImplementedError` for a command that passed steps 1 to 9, so nothing is accepted by a partial check.

Owner decision (2026-11-05, chat): the contract mentions a configured maximum for `deadline_ms` and `execution_timeout_ms` (ERROR_CODES `INVALID_TIMEOUT`) and a configured default priority (5.6) but section 3.1 lists neither. The configuration validator therefore accepts three optional per-joint fields: `max_deadline_ms`, `max_execution_timeout_ms` and `default_priority` (default 0). A contract clarification is to be proposed later; the contract is not changed here.

Sub-order inside a step (deterministic, not stated in the contract): step 2 INVALID_SCHEMA, NON_FINITE_VALUE, UNSUPPORTED_CONTRACT_VERSION; step 6 command type, target type, target ID, then the referenced command (not found, already terminal, not cancellable) or fault; step 7 mode, priority, unit; step 8 INVALID_CONSTRAINT, LIMIT_POSITION, LIMIT_VELOCITY, INVALID_TIMEOUT (a constraint must be valid before it can define a limit); step 9 BACKEND_UNAVAILABLE, then BACKEND_CAPABILITY_UNSUPPORTED. Unknown fields are reported in sorted order.

Interpretations for owner review:

- A supplied idempotency lookup of status IDENTICAL returns the stored decision with `replay` true and no command ID, after steps 1 to 3 (an unauthenticated or unauthorized client never gets a stored result). DIFFERENT is REQUEST_ID_CONFLICT.
- BACKEND_UNAVAILABLE for health UNAVAILABLE or FAULTED, or no backend supplied; DEGRADED is available at step 9. Step 9 does not apply to CANCEL and CLEAR_FAULT (the CLEAR_FAULT backend checks belong to 13.6 at step 10).
- A backend that declares neither numerical joint limits nor an explicit "no narrower limit" for a joint is refused BACKEND_CAPABILITY_UNSUPPORTED for movement commands (8.3: Motion must not assume the whole configured envelope); at step 8 an undeclared limit narrows nothing.
- An empty effective position range (for example a backend range outside the configured one) is INVALID_CONSTRAINT. A position constraint on a joint without position limits is INVALID_CONSTRAINT.
- Constraints on STOP, HOLD, CANCEL and CLEAR_FAULT are ignored (no limit applies to them); their timeouts are still checked against the maximums.
- The standard-library envelope check mirrors `motion-command.schema.json`; a test compares the two on a fixed corpus of mutated documents. `format` keywords (`date-time`) are annotations and are not asserted.

Findings for a later contract clarification (nothing changed here):

1. `deadline_ms` or `execution_timeout_ms` of zero or below is rejected INVALID_SCHEMA at step 2 by the schema (`exclusiveMinimum`), although `ERROR_CODES.md` lists a non-positive value under INVALID_TIMEOUT (step 8). INVALID_TIMEOUT is therefore reachable only for a value above the configured maximum.
2. The identifier pattern `^[A-Za-z0-9._:-]{1,128}$` also accepts one trailing newline, because `$` matches before it in common regular-expression engines; contract 1.4 says only the listed characters are allowed.
3. LIMIT_ACCELERATION stays reserved (MOTION-AD-045): the effective acceleration maximum is computed as the intersection but no command value is compared with it.
