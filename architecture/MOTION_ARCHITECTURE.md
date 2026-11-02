# Kritva Motion Architecture (DRAFT v0.1.0)

Task: KOS-MOTION-001 (approved by the owner in chat on 2026-11-02; this document is a draft for review)
Authority: architecture, components, ownership, data flow and boundaries. The sole normative source for interfaces is [MOTION_CONTRACT.md](../contract/MOTION_CONTRACT.md). Rationale per decision is in [MOTION_DECISIONS.md](MOTION_DECISIONS.md).

Nothing here is an interface other repositories may rely on until the contract is reviewed and tagged. No implementation exists.

## 1. Purpose

Kritva Motion defines what movement is requested and how that request is validated, executed, monitored and terminated, independent of the underlying actuator hardware. Joint-level position and velocity are the first capability; the model is extensible without redesign (MOTION-AD-001).

## 2. Scope of KOS-MOTION-001

Delivered by this task: this architecture, the normative v0.1.0 contract, JSON schemas, error codes, the Execution Backend Interface specification and a conformance test plan.

Not delivered: runtime command manager, backend registry, simulator (S1 or higher), physical actuator adapter, firmware integration, Mind and Skill integration. These are later tasks, proposed through kritva-program (MOTION-AD-026).

## 3. Safety boundary

Software acceptance of this architecture or contract, including tests, simulation and mocks, is never physical or safety validation. `STOP`, `HOLD` and `CANCEL` are software motion controls and not emergency-stop or certified safety functions. Any claim about a physical limit, stop distance, stop time or hardware fault response stays gated on program milestone V2-M6 (HOLD) and the human safety reviews in kritva-program.

## 4. Context

```text
Kritva Mind --> Kritva Skill --> [ Motion API ] --+
Supervisory services ---------> [ Motion API ] ---+
                                                  v
   Kritva platform security (identity)  --> Motion core
   Robot configuration (versioned)      --> Motion core
                                                  |
                                   Execution Backend Interface (owned by Motion)
                                         |                      |
                                 Simulator backend       Kritva Actuator family
                                 (later task)            (later; HOLD)
```

Feedback enters Motion through the Execution Backend Interface. Motion does not acquire sensor data and does not duplicate kritva-sense; a future sensing feedback path would be a separate, versioned contract.

## 5. Components

| Component | Responsibility | Owns |
|---|---|---|
| Motion API | Versioned public interface for clients: submit, control, query, subscribe | Public contract surface |
| Identity and authorization gate | Validates the identity assertion through the Core security interface; checks permission on operation and target before admission | Authorization decisions and audit (not credentials) |
| Command manager | Idempotency, `command_id` assignment, history | Command records |
| Command validator | Schema, version, target, mode, units, limits, backend capabilities, preconditions, in a fixed order | Admission result |
| Arbitration | One active command per joint; STOP exemption | Per-joint execution policy |
| Lifecycle manager | Public lifecycle, deadlines, execution timeouts, termination confirmation | Command state |
| Joint state manager | Control state and health state, fault records, fault clearing | Joint state |
| Feedback manager | Consumes backend feedback, evaluates validity and freshness, completion checks | Measured state |
| Event publisher | Command-scoped and resource-scoped events, abstract transport | Event sequences |
| Configuration loader | Validates and activates versioned robot configuration, binds versions to commands | Active configuration reference |
| Backend registry | Registration and capability discovery for backends (specified here, implemented later) | Capability records |

## 6. Ownership

| Information or function | Owner |
|---|---|
| Client identity, credentials, token verification, identity lifecycle | Kritva platform security (kritva-core) |
| Identity assertion validation, operation permissions, target access enforcement, authorization audit | Motion |
| Joint IDs, types, direction, units, limits, feedback freshness, supported modes, tolerance and settling | Robot configuration |
| Runtime validation, arbitration, lifecycle, completion evaluation | Motion |
| Backend capability reporting, dispatch, feedback production, stop confirmation | Execution backend |
| Execution Backend Interface definition and versioning | Motion |
| Motor control (torque, current, PWM), encoders, firmware | Actuator and embedded workstreams |

## 7. Data flows

Command flow: client submits a command with `client_request_id` and an identity assertion; Motion validates the identity, checks idempotency, authorizes, validates the command, binds the active configuration version, and returns either a rejection with an error code or an acceptance with a `command_id`. The command starts `ACCEPTED`. Arbitration and backend dispatch follow; the backend confirms start and Motion moves the command to `RUNNING`. Feedback is evaluated against the completion criteria to reach `COMPLETED`, or timeouts, cancellation or faults lead to `CANCELLED` or `FAILED`.

Feedback flow: the backend produces feedback with its own timestamp and clock domain; Motion records its monotonic receipt time, evaluates validity and freshness per joint configuration, updates joint state, and publishes resource-scoped events on changes.

Control flow: `CANCEL`, `STOP` and `HOLD` follow the same admission and authorization path, with arbitration rules in the contract. Termination is complete only on backend confirmation or after the bounded wait expires.

Observability flow: the status query is authoritative. The event interface provides at-least-once delivery where the selected implementation supports it, otherwise best effort; clients tolerate duplicates, detect gaps where sequence continuity is provided, and recover by querying state.

## 8. Extensibility

Reserved targets (`joint_group`, `end_effector`, `robot`), `EXECUTE_TRAJECTORY`, multi-joint coordination and multiple priority levels have identifiers in the contract and return `UNSUPPORTED_*` until a later MINOR version defines them. Multi-joint coordination needs defined atomic admission, resource arbitration and partial-failure semantics before it can be supported.

## 9. Constraints and dependencies

kritva-core (approved contract, not pinned) supplies the security interface. kritvaos-community (public architecture description, not pinned) is the architectural reference. kritva-sense is a peer for sensor data contracts. kritva-mind and kritva-skill are downstream consumers. kritva-actuator is downstream of this repository's backend interface (repo-pipeline.json). Versions and commits are pinned in ACCEPTANCE_CRITERIA.md when the contracts they refer to are approved; none are pinned yet.

## 10. Simulation levels (future tasks, non-normative)

| Level | Description | Status |
|---|---|---|
| S1 contract simulation | Deterministic command, lifecycle, state and feedback behaviour | First simulator; later task |
| S2 joint dynamics | Position, velocity, acceleration and configurable response | Future |
| S3 robot simulation | Multi-joint kinematics and dynamics | Future |

None is a KOS-MOTION-001 deliverable. Simulation output is software evidence and is never reported as physical validation.

## 11. Confirmation principle

Motion never reports a command, joint or backend as stopped, completed, engaged or recovered unless the condition has been confirmed through the backend interface or established from valid fresh feedback. Joint state is two independent dimensions, control state (idle, active, holding, unknown) and health state (ready, degraded, faulted), so a health change never hides a running command and an unconfirmed stop is reported as unknown, not idle.
