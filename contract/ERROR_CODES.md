# Motion Error and Reason Codes v0.1.0-draft

Status: DRAFT revision 4. Referenced by [MOTION_CONTRACT.md](MOTION_CONTRACT.md), which is normative. Codes are stable strings; changing the meaning of a code is a MAJOR contract change.

Retryable means a client may resubmit later without changing the request: it says nothing about whether doing so is safe. Clients decide by the code, never by the message text.

## 1. Admission rejection codes (submission result `REJECTED`)

Listed in the order the validator checks them (contract section 8.4). Authorization (step 3) precedes the idempotency lookup (step 4).

| Code | Step | Meaning | Retryable |
|---|---|---|---|
| `UNAUTHENTICATED` | 1 | Identity assertion missing, invalid or expired | After fixing identity |
| `INVALID_SCHEMA` | 2 | Malformed envelope, missing or unknown field, unknown target type | No |
| `NON_FINITE_VALUE` | 2 | NaN or infinity in a numeric field | No |
| `UNSUPPORTED_CONTRACT_VERSION` | 2 | Contract MAJOR version not supported | No |
| `PERMISSION_DENIED` | 3 | Client lacks permission for the operation or target scope | No |
| `REQUEST_ID_CONFLICT` | 4 | Same `client_request_id` with different content | No |
| `CONFIG_NOT_ACTIVE` | 5 | No validated active configuration | Yes |
| `UNSUPPORTED_COMMAND` | 6 | Command type reserved or unknown (including `EXECUTE_TRAJECTORY`) | No |
| `UNSUPPORTED_TARGET_TYPE` | 6 | Reserved target type (`joint_group`, `end_effector`, `robot`) | No |
| `UNKNOWN_TARGET` | 6 | Target ID not in the active configuration | No |
| `COMMAND_NOT_FOUND` | 6 | `CANCEL` or query references an unknown or invisible `command_id` | No |
| `FAULT_NOT_FOUND` | 6 | `CLEAR_FAULT` references an unknown fault, a fault not on the target joint, or one the client may not see | No |
| `COMMAND_NOT_CANCELLABLE` | 6 | `CANCEL` references a `STOP`, `CLEAR_FAULT`, `CANCEL` or an engaged `HOLD` | No |
| `COMMAND_ALREADY_TERMINAL` | 6 | `CANCEL` references a command already in a terminal state | No |
| `UNSUPPORTED_MODE` | 7 | Joint does not support the requested mode (including `SET_POSITION` on a continuous joint) | No |
| `UNSUPPORTED_PRIORITY` | 7 | Priority other than the configured default | No |
| `UNIT_MISMATCH` | 7 | Declared unit does not match the joint type | No |
| `LIMIT_POSITION` | 8 | Position outside the effective limits | No |
| `LIMIT_VELOCITY` | 8 | Velocity outside the effective limits | No |
| `LIMIT_ACCELERATION` | 8 | Acceleration outside the effective limits | No |
| `INVALID_CONSTRAINT` | 8 | Constraint widens a configured limit or is contradictory | No |
| `INVALID_TIMEOUT` | 8 | `deadline_ms` or `execution_timeout_ms` is not a positive integer or exceeds the configured maximum | No |
| `BACKEND_UNAVAILABLE` | 9 | No available backend for the target | Yes |
| `BACKEND_CAPABILITY_UNSUPPORTED` | 9 | Backend does not declare the needed capability (mode, controlled stop, hold) | No |
| `TARGET_STATE_UNKNOWN` | 10 | Joint `control_state` is `UNKNOWN` (initial state, or physical condition no longer established) and the operation is `SET_POSITION`, `SET_VELOCITY` or `HOLD`, whatever the health state. `STOP`, `CANCEL` and queries are not affected | After the control state is established (contract 13.9) |
| `TARGET_FAULTED` | 10 | Joint health is `FAULTED` and the operation is not exempt (contract 8.6) | After `CLEAR_FAULT` |
| `TARGET_DEGRADED` | 10 | Joint health is `DEGRADED` and `degradation_policy` does not permit the operation | After recovery |
| `FEEDBACK_UNAVAILABLE` | 10 | Required feedback missing or invalid | Yes |
| `FEEDBACK_STALE` | 10 | Required feedback older than `max_feedback_age_ms` | Yes |
| `FAULT_NOT_CLEARABLE` | 10 | `CLEAR_FAULT` while the cause persists, control state is `UNKNOWN`, or a movement or termination is active. Applies only to a joint with a fault record | Yes |
| `HUMAN_CONFIRMATION_REQUIRED` | 10 | Fault clearance policy needs a human-operator attribute | No |
| `TARGET_BUSY` | 11 | Joint already has an active conflicting command | Yes |

A rejection returns `code`, a human-readable `message`, and where applicable the conflicting `target` and `command_id`.

## 2. Terminal reason codes

Every transition is recorded with a `reason_code`.

### COMPLETED

| Code | Meaning |
|---|---|
| `GOAL_REACHED` | `SET_POSITION` tolerance and settling satisfied |
| `DURATION_ELAPSED` | `SET_VELOCITY` duration elapsed |
| `STOP_CONFIRMED` | `STOP` confirmed by the backend |
| `HOLD_ENGAGED` | `HOLD` engagement confirmed |
| `CANCEL_EFFECTIVE` | `CANCEL` took effect on the referenced command |
| `FAULT_CLEARED` | `CLEAR_FAULT` succeeded |

### CANCELLED

| Code | Meaning |
|---|---|
| `CANCEL_REQUESTED` | Cancelled by `CANCEL` |
| `STOPPED` | Terminated by `STOP` |

### FAILED

| Code | Meaning |
|---|---|
| `DEADLINE_EXPIRED` | Execution did not start before the deadline; if already dispatched, after termination was confirmed |
| `EXECUTION_TIMEOUT` | Execution timeout expired and termination was confirmed |
| `TERMINATION_UNCONFIRMED` | Termination was accepted by the backend but not confirmed within `termination_confirm_timeout_ms` (the bound is not restarted by later causes); the joint is faulted and its control state is `UNKNOWN`. Also the reason for a `STOP` that could not be confirmed |
| `BACKEND_REJECTED_DISPATCH` | Backend refused to start execution, or refused a `STOP` before accepting a termination attempt |
| `FEEDBACK_LOST` | Required feedback lost during execution |
| `TRACKING_ERROR` | Joint fault: measured motion deviates beyond the configured bound |
| `JOINT_LIMIT_VIOLATION` | Joint fault: measured value outside configured limits |
| `BACKEND_UNAVAILABLE` | Backend became unavailable |
| `BACKEND_COMMUNICATION_LOSS` | Backend communication lost |
| `BACKEND_EXECUTION_FAILURE` | Backend reported an execution failure |
| `INTERNAL_ERROR` | Motion internal error; the joint is faulted |

## 3. Fault codes

| Code | Class | Clearance default |
|---|---|---|
| `FEEDBACK_LOST` | joint | `HUMAN_REQUIRED` unless configured |
| `TRACKING_ERROR` | joint | `HUMAN_REQUIRED` unless configured |
| `JOINT_LIMIT_VIOLATION` | joint | `HUMAN_REQUIRED` unless configured |
| `TERMINATION_UNCONFIRMED` | joint | `HUMAN_REQUIRED` unless configured |
| `BACKEND_UNAVAILABLE` | backend | `HUMAN_REQUIRED` unless configured |
| `BACKEND_COMMUNICATION_LOSS` | backend | `HUMAN_REQUIRED` unless configured |
| `BACKEND_EXECUTION_FAILURE` | backend | `HUMAN_REQUIRED` unless configured |

Which faults may be set to `CLIENT_AUTHORIZED` is an open item for the safety reviewer (contract section 19).

## 4. Termination causes

Recorded in the termination record (contract 10.6), in order: `CANCEL_REQUESTED`, `STOP_REQUESTED`, `EXECUTION_TIMEOUT`, `DEADLINE_EXPIRED`, `FAULT`. A confirmed termination with any `FAULT` cause ends `FAILED` with the first fault code; with `EXECUTION_TIMEOUT` or `DEADLINE_EXPIRED` ends `FAILED` with that reason (the one recorded first if both); with only cancel or stop causes ends `CANCELLED`, reason `STOPPED` if any `STOP_REQUESTED` cause exists, otherwise `CANCEL_REQUESTED`.

Control operations referencing a termination attempt: a `CANCEL` whose target does not become `CANCELLED` ends `FAILED` with the target's failure reason; a `STOP` whose shared attempt is confirmed ends `COMPLETED(STOP_CONFIRMED)` even if a fault was appended; a `STOP` whose attempt is unconfirmed ends `FAILED(TERMINATION_UNCONFIRMED)`; a `STOP` refused by the backend before any attempt was accepted ends `FAILED(BACKEND_REJECTED_DISPATCH)`.
