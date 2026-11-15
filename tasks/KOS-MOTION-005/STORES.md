# KOS-MOTION-005: stores, configuration activation and event publisher (design)

Status: DRAFT for the PR-01 owner review (hard stop). Nothing in this document is implemented. It is derived from contract `v0.1.0-draft` sections 3, 7, 11, 14 and 15, from `contract/CONFORMANCE_TEST_PLAN.md`, and from the code on main as read on 2026-11-15 (`src/kritva_motion/admission.py`, `config_validation.py`, `lifecycle/engine.py`). Where this document and the contract differ, the contract wins and the difference is a contract finding. Software evidence only: passing tests is never physical or safety validation (contract 2.2). The review is the interim D-047 role and is not independent.

## 1. What the code on main gives this task

Reading the existing code settled most of the attach points. Four of them need an owner decision (marked in section 6).

| # | Fact in the code | Consequence for this task |
|---|---|---|
| F-1 | `AdmissionContext.idempotency` takes a supplied lookup result `{"status": "NEW" or "IDENTICAL" or "DIFFERENT", "stored_decision": {...}}` and admission step 4 returns the stored decision or `REQUEST_ID_CONFLICT`. | The store only has to produce that lookup result and record the decision. Admission order (identity and authorization before idempotency) is kept because the store feeds admission and does not bypass it. |
| F-2 | `LifecycleEngine.submit` builds the admission context itself and never passes `idempotency`, so it is always `NEW`. It also has no client identity parameter. | One engine hook is needed: an optional `idempotency` keyword on `submit`, default `NEW`. This is the only change to engine semantics that the idempotency store needs (Q-7). |
| F-3 | `LifecycleEngine.__init__(config, backend, config_digest)` fixes one configuration for the life of the engine. The docstring says activation "is not built here". `_joint_cfg` is read at run time for per-joint parameters of commands already in flight (for example feedback age and termination timers), while deadline and execution timeout are copied at acceptance. | CT-CFG-04 ("a configuration update during execution leaves the active command bound to the old version") cannot be met by swapping `_config`: in-flight commands would change behavior. The engine must keep each configuration version and let each command read its own version (Q-7, the largest change this task makes to the engine, with a full regression run). |
| F-4 | `Result.events` holds event records "without id or sequence number" (contract 14.3 fields `stream`, `event_type`, `occurred_at`, `data`). Nothing is delivered. | The publisher adds `event_id` and the per-stream `sequence_number`, in order, from `Result.events`. No engine change is needed for events. |
| F-5 | A rejected submission returns an `AdmissionResult` and creates no command and no record (contract 7.3 needs it in history). | History must record rejections itself, from the admission result. |
| F-6 | `joint_state` already reports `feedback_status` as `MISSING`, `INVALID`, `STALE` or `VALID` and `is_current` (contract 11.3). | CT-FB-03 may already be demonstrable by a test over existing behavior, which would make it a mapping task and not a build task (Q-8). |
| F-7 | `validate_configuration(config, capabilities)` exists (KOS-MOTION-002) and returns violations. Digest computation is not defined anywhere. | Activation reuses the validator. The digest algorithm is an interpretation (Q-10). |

## 2. Components

All in `src/kritva_motion/stores/`, standard library only, no I/O, no system clock. Each takes its time from the same injected monotonic reading as the engine. Names below are working names to be confirmed in review.

| Component | Responsibility | Contract |
|---|---|---|
| `ConfigurationRegistry` | Holds the active configuration, its version and digest, and the history of activations and rollbacks. `activate(config, capabilities, authorization)` validates with `validate_configuration`, refuses an incompatible update while affected commands are active, and makes the new version apply to later commands only. `rollback(version, authorization)` is explicit, authorized and recorded. Before the first successful activation there is no active configuration. | 3.2, 3.3, 3.4 |
| `IdempotencyStore` | Keyed by `(client_id, client_request_id)`. `lookup(client_id, request_id, content, now)` returns the admission lookup result of F-1. `record(client_id, request_id, content, decision, now)` stores the original decision (an accepted result or a rejection). Entries expire after the retention period. | 7.3, 7.4 |
| `CommandHistory` | Append-only. One record per submission with the fields of 15.1 that this layer can fill. The interface has `append` and `read` and no overwrite or delete operation. Retention is a parameter. | 15 |
| `EventPublisher` | Takes `Result.events` in order, assigns `event_id` and a sequence number per stream (`command`, `joint`, `backend`), and offers each event to an `EventSink`. A sink that raises or refuses never changes the result of the engine call. | 14.2, 14.3, 14.4 |
| `EventSink` | A `Protocol` with one method, `deliver(event)`. No implementation in `src`. Test sinks model a missing subscriber, a failing sink, duplication and loss. | 14.2 |
| `Coordinator` | Wires the pieces for one submission: registry (active configuration), idempotency lookup, engine call with the lookup result, history append, idempotency record, publisher. It holds no lifecycle logic. | 7.1 |

The reference consumer that tolerates duplicates and detects gaps (contract 14.4) lives in `tests/stores/`, not in `src`: it is part of the evidence, not of the product.

## 3. Record shapes

Plain data (dicts), as the engine does. Fields are the contract's own; none is added.

- **Idempotency entry:** `client_id`, `client_request_id`, `content_key` (see Q-3), `decision` (`accepted`, `code`, and for an accepted submission the original `command_id`, `config_version`, `config_digest`, `accepted_at`), `stored_at_ms`, `expires_at_ms`. A replay returns the original result with `idempotent_replay` true and creates no second command. A replayed rejection returns the same rejection.
- **History record (15.1):** `client_id`, `client_request_id`, `command_id` (only if accepted), `operation`, `target`, `submitted_at`, `accepted_at`, `execution_started_at`, `completed_at`, `lifecycle_history` (state, phase, reason, timestamp, taken from the engine's transitions), `validation_result`, `result`, `fault_references`, `backend_reference`, `config_version`, `config_digest`, `authorization_outcome` (as supplied), effective deadline and timeouts. A rejected record has no `command_id` and no lifecycle (7.3). Records of an accepted command are updated only by appending lifecycle entries, never by overwriting an earlier entry.
- **Event (14.3):** `event_id` (unique), `stream` (`kind`, `id`), `sequence_number` (starts at 1 and increases by one within the stream), `occurred_at`, `event_type`, `data`.
- **Activation record:** `version`, `digest`, `activated_at_ms`, `kind` (`ACTIVATE` or `ROLLBACK`), `authorization` (as supplied), `outcome` (activated, or refused with the incompatibility named).

## 4. Invariants (checked by the fixed-seed property test)

1. For one `(client_id, client_request_id)` inside the retention period, at most one command is ever created.
2. A replay returns the stored decision byte for byte, with `idempotent_replay` true, and never changes any state.
3. Sequence numbers within a stream are exactly 1, 2, 3, ... in publication order, with no repeat and no gap, whatever the sinks do.
4. Event delivery failure never changes a command, a joint, the history or any returned result.
5. Every accepted command's `config_version` and `config_digest` equal the active version and digest at its admission and never change afterwards.
6. A configuration activation never changes the parameters used by a command accepted before it.
7. History is append-only: after any sequence of operations, every earlier record and every earlier lifecycle entry is unchanged.
8. A rejected submission has a history record and no `command_id`.
9. No store, registry or publisher method reads the system clock; all time comes from the injected reading, which never goes backwards.

## 5. Design per target ID

| ID | Mechanism | Test sketch |
|---|---|---|
| CT-CFG-01 | Registry with no active configuration; admission step 5 rejects `CONFIG_NOT_ACTIVE`; first valid activation enables submission | submit before activation, then activate an invalid config (still rejected), then a valid one |
| CT-CFG-03 | Version and digest bound at admission (engine already records them); registry supplies both | accepted command carries the active version and digest |
| CT-CFG-04 | Per-command configuration binding (F-3) | activate version 2 while a command of version 1 runs; the command keeps version 1 parameters and records |
| CT-CFG-05 | Compatibility check against active commands (Q-9) | an update that removes or narrows a joint with an active command is refused with the incompatibility named |
| CT-CFG-06 | `rollback` with a supplied authorization result, recorded in the activation history | rollback without authorization is refused; an authorized rollback is traceable |
| CT-ID-01 | Store lookup `IDENTICAL` | resubmit identical content, same result, no second command |
| CT-ID-02 | Store lookup `DIFFERENT` | same ID with different content is `REQUEST_ID_CONFLICT` |
| CT-ID-03 | Key includes `client_id` | same request ID from another client is independent |
| CT-ID-04 | Store keeps rejections | a replayed rejection returns the same rejection |
| CT-ID-05 | Expiry at `expires_at_ms` | after retention a reused ID is a new request |
| CT-HIS-01 | `CommandHistory` | every 15.1 field present where fillable, rejected distinct from accepted, no overwrite operation exists |
| CT-LC-05 | Rejection recorded in history with no `command_id` and no lifecycle | submit an invalid command, read history, replay it |
| CT-FB-03 | Existing `feedback_status`, plus the status event (Q-8) | missing, invalid and stale feedback each reported distinctly, never `VALID` |
| CT-EV-01 | Per-stream counter | sequences 1..n by one, gaps detectable by the reference consumer |
| CT-EV-02 | At-least-once test sink delivers twice | consumer tolerates duplicates; `joint_state` and `command` queries are authoritative after loss |
| CT-EV-03 | Publisher isolates sink failure | no sink, and a raising sink, leave execution results unchanged |
| CT-EV-04 | Stream kind from the event | joint and backend changes appear in their own streams only |
| CT-EV-05 | Best-effort sink drops events | consumer reports gaps where sequences are continuous and recovers by query |
| CT-DET-02 | Replay of recorded inputs (Q-4) | re-run from history and configuration reproduces command outcomes, or the ID returns to DEFERRED |

## 6. Questions for the owner (PR-01 decisions)

Each answer is recorded here as an interpretation or an open contract finding. None changes the contract.

| Q | Question | Proposed handling |
|---|---|---|
| Q-1 | Identity and authorization are supplied (section 16 is PROVISIONAL) | Client identity and the authorization outcome are supplied inputs. The five CT-AUTH IDs stay DEFERRED |
| Q-2 | Contract 7.4 puts the idempotency retention in the configuration, but 3.1 does not list it and `config_validation.py` does not validate it | Contract finding. Retention is a validated parameter of the store, at least the longest effective execution timeout plus the termination-confirmation bound (7.4), checked at activation |
| Q-3 | What counts as identical content (7.4) | A canonical comparison over the command fields (`command_type`, `target`, `parameters`, `deadline_ms`, `execution_timeout_ms`, `contract_version`) excluding audit and transport fields. Interpretation |
| Q-4 | CT-DET-02 replays outcomes from history and configuration; 15.1 does not hold feedback and backend inputs | Either keep an input journal as an implementation aid (not a contract field) or return CT-DET-02 to DEFERRED and end at 18 targets. Recommendation: decide after PR-04, when the journal's cost is known; PR-01 records the choice to defer the decision |
| Q-5 | 15.2 does not assume permanent storage | In-memory append-only, retention a parameter, no overwrite operation. No durability claim |
| Q-6 | 14.2 names no transport; 14.4 allows at-least-once or best effort | `EventSink` protocol only; reference consumer in the tests |
| Q-7 | The engine must not change semantically, yet F-2 and F-3 need two changes | (a) the `idempotency` keyword on `submit` (default `NEW`, behavior unchanged for existing callers); (b) per-command configuration binding: the engine keeps a table of configuration versions, each command stores its version and reads its own per-joint parameters. Both are limited to attaching, each is covered by the existing 94 tests plus new ones, and the full regression run is a PR-02 exit condition. If (b) proves larger than a hook, PR-02 stops and returns to the owner |
| Q-8 | F-6: CT-FB-03 may already hold for existing behavior | PR-04 first checks whether a mapped test over `feedback_status` and the status event is enough. If so, no new feedback code is written and the ID is closed by mapping |
| Q-9 | What makes an update incompatible with an active command (3.4) | Proposed minimum: the update removes the command's joint, drops the command's operation mode for it, or narrows a limit below an in-flight command's request. Anything else is an open contract finding |
| Q-10 | `config_digest` has no algorithm in the contract | SHA-256 over canonical JSON (sorted keys, compact separators, UTF-8), hex digest. Interpretation, recorded as a contract finding |

The open interpretation points I-27, I-32, I-34 and I-35 of KOS-MOTION-003 are re-read in PR-01 for any effect here; none is believed to apply, which the owner confirms.

## 7. Engine changes this task makes (the complete list)

1. `submit(..., idempotency=None)`: passes the lookup result into the admission context. Default behavior is unchanged.
2. Per-command configuration binding (Q-7b): the configuration table and the per-command version reads. This touches the places that read `_joint_cfg` for in-flight commands. It is delivered in PR-02 with its own tests, and every one of the 94 earlier IN_SCOPE tests must still pass unchanged.

No other engine change is planned. A needed third change goes to the owner first.

Delivered in PR-02 (revision 2): `install_configuration(config, digest)` (the engine can start with no configuration, installs versions into a binding table and refuses the same version with another digest), `open_commands()` for the compatibility check, and `_cfg_of(command)` for the reads of a command's own settling window (`position_tolerance`, `max_feedback_age_ms`, `settling_duration_ms`), default deadline and timeout, and termination bound. The binding stayed a hook: the per-command reads are four lines, so PR-02 did not stop. The `idempotency` keyword (item 1) comes with PR-03.

Delivered in PR-03 (revision 3): the `idempotency` keyword on `submit` (item 1; default unchanged), `IdempotencyStore`, and the first form of the `Coordinator` (lookup, engine call, record, replay of the stored original `command_id`). A decision is stored only when it was taken at admission step 4 or later, because steps 1 to 3 run before the lookup and `REQUEST_ID_CONFLICT` is not an original decision. The retention minimum (the largest `max_execution_timeout_ms` plus the largest `termination_confirm_timeout_ms`) is checked when the registry activates a configuration, as `RETENTION_TOO_SHORT` (Q-2, still a contract finding because 3.1 does not list the field).

**I-37 (interpretation, refines Q-3).** Content identity covers `contract_version`, `command_type`, `target`, `parameters`, `constraints`, `priority`, `deadline_ms` and `execution_timeout_ms`. `client_request_id` is the key; `identity_assertion` and `issued_at` are audit and transport fields and never make two submissions different. Q-3 listed the fields without `constraints` and `priority`; both change what a command does, so identical content needs them equal.

Delivered in PR-04 (revision 4): `CommandHistory` and the history wiring of the `Coordinator` (`submit` appends one record per non-replay submission, `observe(result)` appends the command events of any engine Result as lifecycle entries and the faults named by termination causes as references). No engine change was needed. CT-FB-03 is closed by mapping as Q-8 proposed: the engine already reports `MISSING`, `INVALID`, `STALE` and `VALID` in `joint_state` and in the joint event, and a dedicated test now maps to it.

**I-38 (interpretation).** An idempotent replay (7.4) is not a new submission record: it returns the stored original result, so it is appended to the original record as a replay marker, which keeps one record per distinct decision and keeps lifecycle entries attached to one record. A `REQUEST_ID_CONFLICT` is a different decision and gets its own rejected record. `execution_started_at`, `completed_at` and `result` are derived on read from the appended lifecycle entries, so they cannot be overwritten. Retention drops whole records only, and never an accepted command that is not terminal.

Delivered in PR-05 (revision 5): `EventPublisher` and the `EventSink` port (`deliver(event)`, nothing implements it in `src`), and the publisher wiring in the `Coordinator`: `observe(result)` takes each engine Result once, appends its command events to the history and publishes all its events; `command_status` is GET_COMMAND_STATUS with `last_sequence_number`. No engine change.

**I-39 (interpretation).** `event_id` is `<kind>:<stream id>:<sequence number>` (unique, and within the schema pattern). A sink failure is an exception from `deliver`; it is recorded (sink index, event id, error type) and never reaches the caller, so numbering and execution do not depend on sinks. Command events carry the originating `client_id` (14.5), taken from the submission; joint and backend events carry none, because no single client originates them. `occurred_at` is the caller's UTC audit value, passed through. Tail loss on a stream is invisible to sequence continuity and is found by comparing the consumer's last number with `last_sequence_number` from the status query.

**F-8 (finding, nothing changed).** Contract 14.3 lists `BACKEND_HEALTH_CHANGED` and `FEEDBACK_STATUS_CHANGED`, but the KOS-MOTION-003 engine emits neither (a backend health report and a change of feedback status produce no event; `JOINT_STATE_CHANGED` carries the feedback status in its snapshot). CT-EV-04 needs only that the events that exist are in their own streams. Emitting the two events would be a change to the engine and goes to the owner as a separate step.

**I-36 (interpretation, new).** Joint-level monitoring that is not a command parameter (the age after which feedback counts as stale, `feedback_required`, the loss check of 11.5 and a status report's age limit) reads the active version, because it describes the joint and not one command. A later version may change these for a command already running; the compatibility rule of Q-9 does not cover them. If the owner wants them bound to the command too, that is a contract clarification, not a code change here.

## 8. Layout and gate

`src/kritva_motion/stores/` (`__init__.py`, `config_registry.py`, `idempotency.py`, `history.py`, `events.py`, `coordinator.py`), tests in `tests/stores/`, and `tests/stores` is added to `UNIT_TEST_DIRS` in `scripts/test_gate.py` by the first implementation PR that adds a test there. Each PR updates `tests/manifest/conformance_manifest.json` for the IDs it covers. The Python used for the gate is 3.11 or newer (`make test-unit PYTHON=python3.12`).

## 9. What this document does not claim

It does not show that anything survives a restart, that an event transport delivers, that authentication works, that a backend behaves as supplied, that real time behaves like the injected clock, or that concurrent callers cannot race. It is a design draft: the owner's answers in PR-01 replace section 6, and no implementation PR starts before that sign-off.
