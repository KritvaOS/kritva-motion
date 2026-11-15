# KOS-MOTION-004: Motion execution backend interface, simulator and integration and regression gates

Status (revision 3): IMPLEMENTATION COMPLETE, ready for owner review; not accepted. APPROVED (kritva-program D-134, weight 7) and baselined in v15 (D-135); PR-01 (design record), PR-02 (backend interface package), PR-03 (scripted S1 simulator, CT-BE-01), PR-04 (runtime driver, engine hooks, CT-BE-02, CT-BE-04, CT-BE-07), PR-05 (`make test-integration`, a second backend, the identifier scan, CT-BE-03, CT-BE-06) and PR-06 (`make test-regression` with golden traces, the fixed-seed property test of the driver, `make test`, CI workflows, final documents) are delivered: all 6 target IDs have one dedicated test (119 IN_SCOPE, 5 DEFERRED CT-AUTH IDs, 0 OUT_OF_SCOPE). Acceptance and its review record are the owner's separate step. History: PROPOSED in revision 1 with the PR-01 design record awaiting owner review. Opened 2026-11-15 after the owner closed V2-M2-MOTION-003 and chose to work on this task (chat: "let us work on KOS-MOTION-004", scope chosen: backend interface, simulator and gates; simulator scripted and deterministic only; first deliverable: task design record and proposal). Not in any baseline yet: the proposal is in kritva-program (`v2/planning/KOS_MOTION_004_PROPOSAL.md`) and needs an owner decision. No implementation starts before the owner approves PR-01 by merging it and the task is baselined.
Task owner: Dinesh (repository owner). Architecture and safety reviewer roles: Dinesh, interim (D-047); the review is not independent and every acceptance record says so.
The task earns credit only through a central approval with passing evidence. Motion reports facts only.

## 1. Scope

A software-only Execution Backend Interface (contract 17), a deterministic scripted simulator behind it, a runtime driver that connects the KOS-MOTION-003 engine and the KOS-MOTION-005 stores to a backend through that interface, and the first real integration and regression gates. Pure, in-memory, Python standard library, injected monotonic clock, no I/O, no threads. The design document [BACKEND.md](BACKEND.md) is part of PR-01; the IDs it targets are in [ID_MATRIX.md](ID_MATRIX.md).

| Deliverable | Contract |
|---|---|
| The backend interface as an abstract, transport-independent port: `describe_capabilities`, `dispatch`, `request_termination`, `request_hold` and `release_hold`, feedback, health, and the backend reports `execution_started`, `execution_rejected`, `termination_request_accepted`, `termination_confirmed`, `termination_unconfirmed` (decided by Motion) | 17.1, 17.4, 17.5, 17.6 |
| A capability declaration with every item of 17.2 and a validator that reports each missing or malformed item | 17.2 |
| Validation of every outgoing operation against the declared capabilities before dispatch | 17.3 |
| Backend reports that drive the lifecycle as specified: start, rejection, termination accepted, confirmed or unconfirmed, hold, feedback, health and faults | 17.4, 17.5 |
| A simulator at level S1 (contract simulation): scripted, deterministic, on the injected clock, declaring its capabilities, labelled as simulation in every output; no joint dynamics, no kinematics | 17.7 |
| Swap invariance: a second conforming backend changes no public behaviour | 17.1 |
| No actuator-specific identifier in any public message or error | 4.1, 17 |
| `make test-integration` and `make test-regression` implemented, with CI workflows | ACCEPTANCE_CRITERIA.md section 5 |

## 2. Out of scope

Simulation levels S2 (joint dynamics) and S3 (kinematics and dynamics), any real actuator adapter, firmware, ROS 2 and any transport (DDS, MQTT, gRPC), the Core security interface and any authentication or authorization implementation (the five CT-AUTH IDs stay DEFERRED), persistent storage, real-time behaviour, hardware-in-loop, and any physical or safety validation (gate V2-M6, HOLD). The `make acceptance` and `make lint` gates stay NOT_IMPLEMENTED.

## 3. Acceptance mapping

Criteria AC-401 to AC-407 are in [ACCEPTANCE_CRITERIA.md](../../ACCEPTANCE_CRITERIA.md) section 3D and are proposed until accepted. The tests show that the interface, the driver and the simulator follow the contract for a scripted backend. They do not show that any real actuator, transport or firmware conforms, that a simulated stop is a physical stop, that real time behaves like the injected clock, that concurrent callers cannot race, or anything about the Core security interface. Simulation results are software evidence and are never reported as physical validation (contract 17.7).

## 4. Governing rules

1. The contract is the baseline. The task adds no state, phase, reason code, event name or contract field. Open semantics are recorded in `BACKEND.md` as interpretations or contract findings and never added silently. The capability declaration shape of `BACKEND.md` section 3 is an interpretation, not a new contract schema.
2. Approval of PR-01 authorizes implementation and does not authorize any change to the contract. A needed change is a separate contract clarification.
3. The lifecycle semantics of KOS-MOTION-003 and the store semantics of KOS-MOTION-005 do not change. Small hooks are allowed only when listed in `BACKEND.md` section 8 with the earlier tests as the regression run: all 113 earlier IN_SCOPE tests keep passing at every step.
4. The engine, the stores and the admission code never import the backend package, the simulator or the driver. The simulator imports no engine or store. Only the driver connects them (a test checks the import direction).
5. No network, file, database, subprocess, thread or system clock in the source. Time is the injected monotonic clock.
6. DEFERRED IDs are never reported as passed. The manifest gate stays as it is.

## 5. Delivery plan

Order follows the dependencies: the driver needs the interface and a backend to drive; the gates need the driver.

| PR | Deliverable | Target IDs (see ID_MATRIX.md) |
|---|---|---|
| PR-01 | Design record: this file, `BACKEND.md` (port, record shapes, invariants, questions Q-1 to Q-10 answered), the ID matrix with a test that compares it with the manifest, criteria AC-401..AC-407, TASKS.md row. Protected path (criteria): owner merge. Hard owner review stop | none |
| PR-02 | The backend interface package: the port, the capability declaration and its validator, the backend report records, the import-direction test | none (infrastructure) |
| PR-03 | The scripted simulator S1 and its own tests; it declares every 17.2 item | CT-BE-01 (1) |
| PR-04 | The runtime driver: capability check before dispatch, translation of backend reports into engine inputs, termination semantics, the engine hooks of `BACKEND.md` section 8 | CT-BE-02, CT-BE-04, CT-BE-07 (3) |
| PR-05 | `make test-integration`: scenario tests through the driver, the stores, the engine and the simulator; a second conforming backend; the identifier scan over public output; CI workflow | CT-BE-03, CT-BE-06 (2) |
| PR-06 | `make test-regression`: golden traces and their update command, a fixed-seed property test of the driver invariants, `make test`, CI workflow, manifest and final documents | none (gates) |

Targets add up to 6. Each implementation PR ships its own tests and updates the manifest for the IDs it covers, so the gate stays green at every step. The split is a delivery order; the task is accepted as a whole.

## 6. Review plan

Interim owner review (D-047), declared not independent. Compensating evidence: one dedicated test per target ID checked by the existing gate, a test that compares the ID matrix with the manifest, negative sequences (refused dispatch, late and duplicate reports, partial termination, unsynchronized clock, backend loss), a fixed-seed property test with seed, iteration count and command recorded in the CI evidence, all 113 earlier tests still passing, golden traces compared byte for byte, CI evidence bound to the exact commit. The checklist is `REVIEW.md`, written at closure. A read-only review by a second person is welcome and optional.

## 7. Dependencies

| Dependency | State |
|---|---|
| KOS-MOTION-003 accepted | met (D-121) |
| KOS-MOTION-005 accepted and milestone V2-M2-MOTION-003 closed | met (D-132, D-133) |
| Baseline that contains this task | not yet: proposal in kritva-program, owner decisions pending |
| `unit-tests`, `readme-check` and `progress-check` required checks | in place (D-104, D-106, D-123) |
| New CI workflows for the two gates | added in PR-05 and PR-06; becoming required checks is an owner action on the `main` ruleset |
| Core security interface | not pinned; stays out of scope |

## 8. Questions answered in PR-01

Each is recorded in `BACKEND.md` as an interpretation or an open contract finding with the proposed handling; the owner confirms or changes each by reviewing PR-01. None changes the contract.

| Q | Question | Proposed handling |
|---|---|---|
| Q-1 | Package layout and import direction | `kritva_motion.backend` (port, capabilities, reports, simulator) and `kritva_motion.runtime` (driver). Only the driver imports the engine, the stores and the backend package; a test checks it |
| Q-2 | Contract 17.4 allows "event or poll" and "stream or poll" | One pull model: the driver calls `poll(now_ms)` and receives the backend's reports in order. No callbacks, no threads, deterministic |
| Q-3 | Contract 17.2 lists the capability items but defines no format | A declaration as plain data that extends the `backend` description admission already reads (health, capabilities, joint limits) with the missing items; a validator names every missing or malformed item. Recorded as an interpretation and a contract finding. No schema file is added to `contract/` |
| Q-4 | Contract 17.3 says validate before dispatch, but admission already refuses undeclared capabilities, and `BACKEND_CAPABILITY_UNSUPPORTED` is an admission code, not a terminal reason | The driver re-checks each outgoing operation against the current declaration (it may differ from the one at admission). A failure ends the command `FAILED(BACKEND_REJECTED_DISPATCH)` with the undeclared capability named in the record detail; no dispatch happens. Interpretation, no new code |
| Q-5 | The engine has no input for a backend that rejects a dispatch (`execution_rejected`, 17.4 and 17.5); only refused terminations and hold releases give `BACKEND_REJECTED_DISPATCH` | Add one engine hook `execution_rejected` with the same guards as `execution_started` (unknown, terminal, duplicate and terminating inputs are ignored and recorded). Listed in `BACKEND.md` section 8; the 113 earlier tests are the regression run. If it proves larger than a hook, PR-04 stops and returns to the owner |
| Q-6 | Finding F-8: the engine emits neither `BACKEND_HEALTH_CHANGED` nor `FEEDBACK_STATUS_CHANGED`, so the `backend` stream has no health producer | Close F-8 in PR-04 as part of the wiring: the engine emits both events, using only names that 14.3 lists. If the owner prefers, F-8 stays open and `BACKEND_HEALTH_CHANGED` is emitted by the driver instead. Recommended: the engine, so the lifecycle record stays the single source |
| Q-7 | CT-BE-06 needs a second conforming backend | A second, deliberately different backend (`LoopbackBackend`) lives under `tests/`, not in the source, so the package ships one simulator. The same scenario set runs on both and the public outputs are compared |
| Q-8 | What "integration" and "regression" mean for `ACCEPTANCE_CRITERIA.md` section 5 | Integration: scenario tests over real in-repo boundaries (driver, stores, engine, simulator, event sink), no mock of our own code. Regression: committed golden traces (canonical JSON) compared byte for byte, updated only by an explicit command and reviewed in the PR. `make test` runs unit, integration and regression; `acceptance` and `lint` stay NOT_IMPLEMENTED |
| Q-9 | Which milestone holds the task | A new repo milestone V2-M2-MOTION-004 (software, same pattern as -002 and -003). V2-M5-MOTION-001 ("validated against a simulated actuator interface") stays for S2 and S3 level simulation, so an S1 contract simulator is not presented as more |
| Q-10 | Weight in the baseline | Proposed in the kritva-program proposal with its reasoning; the owner sets it when approving. Not decided in this repository |

## 9. Honest limits

Software evidence only. 5 conformance IDs stay DEFERRED (CT-AUTH-01, 02, 03, 04, 06) and none is OUT_OF_SCOPE after this task. Contract section 16 stays PROVISIONAL, the contract stays a draft and no tag is created by this task. A conforming simulator shows that the interface is implementable and the driver follows the contract; it does not show that an actuator, firmware or transport does.
