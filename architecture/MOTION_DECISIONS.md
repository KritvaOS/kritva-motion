# Motion Architecture Decision Register (KOS-MOTION-001)

Status: DRAFT revision 5 for owner review, after three cross-check reviews (7 blockers, then 2, then 1), now addressed (see "Revision history"). KOS-MOTION-001 was approved by the owner in chat on 2026-11-02. The decisions below stay PROPOSED until the owner approves this register in review; the approval of the task is not an approval of each decision. Interface decisions also need an entry in kritva-program `v2/DECISIONS.md` under the program rules (AGENTS.md section 2).

This register replaces the 25 decisions numbered in the design discussion, whose numbering was inconsistent. IDs below are canonical. The normative text is [MOTION_CONTRACT.md](../contract/MOTION_CONTRACT.md); this register records rationale and origin only.

| ID | Decision | Status | Contract section |
|---|---|---|---|
| MOTION-AD-001 | Generalized motion-command architecture; joint control is the first capability | PROPOSED | 1 |
| MOTION-AD-002 | Extensible target model (joint, joint_group, end_effector, robot); only `joint` supported in v0.1.0; others reserved | PROPOSED | 4 |
| MOTION-AD-003 | Command modes are position and velocity only; torque, current and PWM are below Motion | PROPOSED | 5 |
| MOTION-AD-004 | `SET_POSITION` is absolute in the configured joint coordinate system; relative moves deferred | PROPOSED | 5 |
| MOTION-AD-005 | `SET_VELOCITY` is a signed velocity; zero is not STOP or HOLD | PROPOSED | 5 |
| MOTION-AD-006 | Asynchronous execution: admission returns a result and `command_id`; accepted commands run independently and reach a terminal state | PROPOSED | 7 |
| MOTION-AD-007 | One active command per joint; conflicting commands rejected `TARGET_BUSY`; no silent replacement; queuing deferred | PROPOSED | 9 |
| MOTION-AD-008 | `CANCEL` (command), `STOP` (target) and `HOLD` (target) are distinct operations and are software controls, not safety functions | PROPOSED | 6, 9 |
| MOTION-AD-009 | Command deadline (before start) and execution timeout (after start) are independent and optional | PROPOSED | 10 |
| MOTION-AD-010 | Feedback carries measured position and velocity with timestamp, validity, source and backend status; commanded values never stand in for measured | PROPOSED | 11 |
| MOTION-AD-011 | Feedback freshness is configured per joint (`max_feedback_age`, policy, required flag) | PROPOSED | 11 |
| MOTION-AD-012 | Completion is feedback-based with per-joint tolerance and settling duration | PROPOSED | 12 |
| MOTION-AD-013 | Three limit categories (configuration, command, backend); effective envelope is the intersection; no silent clamping | PROPOSED | 8 |
| MOTION-AD-014 | Fault classes: command error, joint fault, backend fault; FAILED (command outcome) is separate from FAULTED (condition); no automatic resume | PROPOSED | 13 |
| MOTION-AD-015 | Idempotent submission with `client_request_id` (client) and `command_id` (Motion); `REQUEST_ID_CONFLICT` on changed content | PROPOSED | 7 |
| MOTION-AD-016 | `priority` field present; single default level in v0.1.0; priority never overrides arbitration or limits | PROPOSED | 5, 9 |
| MOTION-AD-017 | Queryable command history with lifecycle traceability and configurable retention | PROPOSED | 15 |
| MOTION-AD-018 | Mandatory status query plus abstract lifecycle notifications; no transport named | PROPOSED | 14 |
| MOTION-AD-019 | At-least-once events with `event_id` and sequence numbers; status query is authoritative | PROPOSED | 14 |
| MOTION-AD-020 | Permission-based authorization on operation and target scope; permission names PROVISIONAL | PROPOSED | 16 |
| MOTION-AD-021 | Platform security owns authentication; Motion validates the identity assertion via the approved Core interface and enforces authorization | PROPOSED | 16 |
| MOTION-AD-022 | Robot configuration owns joint definitions; Motion owns runtime interpretation and enforcement | PROPOSED | 3 |
| MOTION-AD-023 | Every accepted command is bound to an immutable configuration version (and digest) | PROPOSED | 3 |
| MOTION-AD-024 | Motion reaches execution backends only through a versioned Execution Backend Interface with declared capabilities | PROPOSED | 17 |
| MOTION-AD-025 | Simulator fidelity levels S1 (contract), S2 (joint dynamics), S3 (robot); simulation is software evidence only; implementation is outside KOS-MOTION-001 | PROPOSED | 17 |
| MOTION-AD-026 | KOS-MOTION-001 delivers architecture, contract, schemas, error codes and a conformance test plan; no runtime or simulator. Trajectory, joint_group, end_effector, robot, multi-joint coordination and multiple priorities are reserved and return `UNSUPPORTED_*` | PROPOSED | 2, 4 |
| MOTION-AD-027 | Termination resolution: a bounded confirmation wait that is never restarted by later causes; unconfirmed termination ends the command `FAILED(TERMINATION_UNCONFIRMED)`, faults the joint and sets control state `UNKNOWN`; the termination record keeps all causes | PROPOSED | 10 |
| MOTION-AD-028 | Public lifecycle keeps the five AC-001 states; rejection is a submission response; timeout is a failure reason; cancelling is a non-terminal phase | PROPOSED | 7 |
| MOTION-AD-029 | STOP is a target-level operation never rejected as busy, accepted best-effort on a faulted joint, confirmed by the backend even when nothing is active; it ends an active command with reason `STOPPED`; STOP, HOLD, CANCEL and CLEAR_FAULT have their own `command_id`; HOLD completes on engagement and leaves the joint `HOLDING` | PROPOSED | 6, 9 |
| MOTION-AD-030 | Joint state has two dimensions: control state (IDLE, ACTIVE, HOLDING, UNKNOWN) and health state (READY, DEGRADED, FAULTED); explicit authorized clearing of one identified fault at a time | PROPOSED | 13 |
| MOTION-AD-031 | Joint and backend state changes use resource-scoped event streams, separate from command-scoped sequences | PROPOSED | 14 |
| MOTION-AD-032 | Clock domains: durations on Motion's monotonic clock; UTC only for audit; feedback age from Motion receipt time; backend timestamps carry clock domain | PROPOSED | 10, 11 |
| MOTION-AD-033 | Motion owns and versions the Execution Backend Interface; the actuator family conforms to it | PROPOSED | 17 |
| MOTION-AD-034 | Movement execution slot is separate from the persistent HOLDING condition; STOP, CANCEL, CLEAR_FAULT and queries do not occupy the slot; repeated HOLD on a HOLDING joint is accepted and confirmed | PROPOSED | 6, 9 |
| MOTION-AD-035 | Command execution phases NONE, DISPATCH_PENDING, TERMINATING under the five public states; a late start confirmation never revives a terminating or terminal command | PROPOSED | 7 |
| MOTION-AD-036 | Authorization precedes idempotency replay; a stored result is returned only to the same client with current authorization | PROPOSED | 8 |
| MOTION-AD-037 | Continuous revolute joints support velocity only in v0.1.0; position control of continuous joints is reserved | PROPOSED | 3, 8, 18 |
| MOTION-AD-038 | Policy vocabularies (feedback timeout, fault clearance, degradation) are defined by the contract and validated at configuration activation; unspecified degradation permits no movement | PROPOSED | 3, 13 |
| MOTION-AD-039 | Movement commands own the termination record; STOP and CANCEL are control operations that derive outcomes from it (CANCEL fails with its target's reason; a confirmed STOP stays successful when a fault is appended) | PROPOSED | 7, 10, 13 |
| MOTION-AD-040 | A STOP during an outstanding termination joins that attempt without restarting the bound; a STOP after a terminal outcome is a new attempt | PROPOSED | 6, 9, 10 |
| MOTION-AD-041 | Degradation policy grants permission in principle only; runtime preconditions still apply and activation rejects policies that cannot meet completion rules | PROPOSED | 3, 13 |
| MOTION-AD-042 | Control state starts UNKNOWN; recovery from UNKNOWN is confirmed STOP then CLEAR_FAULT; no implicit override; admission rejection, unconfirmed termination and lost knowledge are distinct | PROPOSED | 2, 13 |
| MOTION-AD-043 | `control_state` UNKNOWN independently blocks SET_POSITION, SET_VELOCITY and HOLD (`TARGET_STATE_UNKNOWN`) whatever the health state; initial UNKNOWN is not a fault; recovery without a fault record is authoritative status or a confirmed STOP; CLEAR_FAULT applies only to a recorded fault | PROPOSED | 8, 13 |
| MOTION-AD-044 | CLEAR_FAULT is a Motion-internal atomic state change whose preconditions are re-evaluated when applied; a new fault or termination in the window fails the clear and clears nothing | PROPOSED | 13 |
| MOTION-AD-045 | Acceleration is a declared maximum constraint only in v0.1.0; no command requests an acceleration value; `LIMIT_ACCELERATION` is reserved for a later version and is not produced | PROPOSED | 8 |

## Mapping from the discussion's numbering

The discussion numbered some decisions twice and skipped AD-005. Canonical IDs follow the order above. Content is unchanged except where AD-026 to AD-033 refine or correct it: AD-024 and AD-025 no longer put the backend implementation and simulator inside KOS-MOTION-001; AD-009 gains AD-027; the discussion's nine-state lifecycle becomes AD-028; AD-008 gains AD-029; AD-014 gains AD-030 and AD-031; AD-009 and AD-011 gain AD-032; AD-024 gains AD-033. AD-034 to AD-044 come from the cross-check reviews (below).

## Open items that block approval of the contract

1. kritva-core security interface is not pinned (AD-020, AD-021). Permission names and the identity assertion format stay PROVISIONAL.
2. kritva-core and kritvaos-community versions or commits are not pinned (README section 7).
3. Safety reviewer input on which faults require a human or safety-authority action before a joint's health may return to READY (AD-030). The reviewer role is held by the owner on an interim basis (D-047); independence is not met.
4. Whether the program wants D-entries per decision or one entry for the register.

## Revision history

Revision 2 applies a cross-check review by ChatGPT (2026-11-02) that returned 7 blockers, 8 majors and 2 minors. Changes: faulted-joint exemptions (8.6), STOP semantics on an idle or faulted joint (6.2), movement slot model (9.1, AD-034), dispatch phases and a late-start rule (7.6, AD-035), authorization before idempotency replay (8.4, AD-036), a termination record that does not restart the bound (10.6), backend termination semantics (17.5), single-fault CLEAR_FAULT (13.6), two-dimension joint state (13.2, AD-030), degradation and policy vocabularies (3.6, 13.8, AD-038), continuous joints reserved (3.7, AD-037), cancellation eligibility (6.1), backend numerical limits (17.2), and event wording (14.4). Where this register and the review differ: continuous joints are reserved rather than defined with an unwrapped coordinate, `TERMINATING` stays a command phase and not a joint control state, and the AC-002 rewording is classified as a substantive amendment, not a clarification.

Revision 3 applies a second cross-check pass (2026-11-02) that returned 2 blockers, 4 majors and 3 minors: fault propagation across movement and control-operation commands (13.4, 7.8, AD-039), STOP joining an outstanding termination (6.2, AD-040), policy permission versus runtime admissibility for degraded feedback (3.6, 13.8, AD-041), initial control state and UNKNOWN recovery (13.9, AD-042), rejection versus unconfirmed termination (2.4), deterministic termination reasons (10.6), and the is_current definition (13.5). Header status reads revision 3.
Revision 4 applies the final cross-check pass (2026-11-02): 1 blocker and 2 majors. UNKNOWN control state now blocks SET_POSITION, SET_VELOCITY and HOLD regardless of health, with new code `TARGET_STATE_UNKNOWN` at validation step 10 (8.4, 8.6, AD-043); recovery of an UNKNOWN joint without a fault record by authoritative status or confirmed STOP, initial UNKNOWN stated as not a fault (13.9, AD-043); CLEAR_FAULT acceptance boundary and atomic application (13.4, 13.6, AD-044); live feedback checks retained after configuration validation (13.8).

Revision 5 (2026-11-04) applies one blocker of an external cross-check of the KOS-MOTION-002 proposal: contract 8.3 listed `LIMIT_ACCELERATION` although no v0.1.0 command requests an acceleration, so the code could not be produced. Acceleration is now a declared maximum constraint only, the code is reserved (8.3, `ERROR_CODES.md`, AD-045), and a requested-acceleration command is not added. Schemas and the conformance test plan are unchanged (no test referenced the code). The owner approved the clarification in chat on 2026-11-04 (program decision D-100).
