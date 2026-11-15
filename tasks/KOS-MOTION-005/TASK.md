# KOS-MOTION-005: Motion stores, configuration activation and event publisher

Status (revision 1): IN_PROGRESS, started 2026-11-15 with the PR-01 design record (this file, `STORES.md`, `ID_MATRIX.md` and criteria AC-501 to AC-507); implementation starts only after the owner approves PR-01. The task was approved in kritva-program decision D-129 (proposal `v2/planning/KOS_MOTION_005_PROPOSAL.md`) and baselined in v14 at weight 6 under the repo milestone V2-M2-MOTION-003 (D-130).
Task owner: Dinesh (repository owner). Architecture and safety reviewer roles: Dinesh, interim (D-047); the review is not independent and every acceptance record says so.
The task earns credit only through a central approval with passing evidence. Motion reports facts only.

## 1. Scope

Pure, in-memory, deterministic reference implementations, in the Python standard library, of the Motion contract parts that need a store, an activation step or a publisher. They sit around the KOS-MOTION-003 lifecycle engine through explicit ports and do not change its semantics. They are driven by supplied inputs and the same injected monotonic clock. The design document [STORES.md](STORES.md) is part of PR-01; the IDs it targets are in [ID_MATRIX.md](ID_MATRIX.md).

| Deliverable | Contract |
|---|---|
| Configuration activation: validation before activation, `CONFIG_NOT_ACTIVE` until a configuration is validated and active, version and digest binding at admission, activation that applies only to later commands, refusal of an incompatible update while affected commands are active, explicit and traceable rollback | 3.2, 3.3, 3.4 |
| Idempotency store: identical resubmission returns the original result with `idempotent_replay`, same ID with different content is `REQUEST_ID_CONFLICT`, request identity scoped to the client, a replayed rejection returns the same rejection, a reused ID after retention expiry is a new request | 7.3, 7.4 |
| Command history: one append-only record per submission with the fields of 15.1 that this layer can fill, accepted and rejected submissions kept apart, no silent overwrite, configurable retention | 15 |
| Feedback status per joint (`VALID`, `STALE`, `INVALID`, `MISSING`), reported distinctly and never as valid | 11.2, 11.3 |
| Event streams (`command`, `joint`, `backend`): unique `event_id`, one sequence number per stream increasing by one, events in their own streams, an abstract event sink with no transport, and execution that continues without a subscriber or when delivery fails; the status query stays authoritative | 14.1 to 14.5 |
| Replay of command outcomes from history and configuration (CT-DET-02), if question Q-4 allows it | 3.3, 15 |

## 2. Out of scope

The Core security interface and any authentication or authorization implementation (identity and authorization results stay supplied inputs, as in KOS-MOTION-002), the Execution Backend Interface implementation, simulators, hardware, ROS 2 and any transport (DDS, MQTT, gRPC), persistent or durable storage, the integration and regression gates, and any physical or safety validation (gate V2-M6, HOLD). The candidate task KOS-MOTION-004 (backend interface, simulator, integration and regression gates) is not registered and keeps CT-BE-02 and the five OUT_OF_SCOPE backend IDs.

## 3. Acceptance mapping

Criteria AC-501 to AC-507 are in [ACCEPTANCE_CRITERIA.md](../../ACCEPTANCE_CRITERIA.md) section 3C and are proposed until accepted. The tests show that the stores, the activation step and the publisher follow the contract for supplied, ordered inputs. They do not show that anything is durable across a restart, that an event transport delivers, that authentication or authorization works, that a backend behaves as supplied, that real time behaves like the injected clock or that concurrent callers cannot race.

## 4. Governing rules

1. The contract is the baseline. The task adds no state, phase, reason code, event name or contract field. Open semantics are recorded in `STORES.md` as interpretations or contract findings and never added silently.
2. Approval of PR-01 authorizes implementation and does not authorize any change to the contract. A needed change is a separate contract clarification.
3. The lifecycle semantics of KOS-MOTION-003 do not change. A needed change requires a contract revision and a regression run. All 94 earlier IN_SCOPE tests keep passing at every step.
4. No backend, simulator, transport, network, file or database access, and no read of the system clock.
5. DEFERRED IDs are never reported as passed. The manifest gate stays as it is.

## 5. Delivery plan

Order follows the dependencies between the pieces: replay needs history and configuration, and history needs the idempotency and rejection records.

| PR | Deliverable | Target IDs (see ID_MATRIX.md) |
|---|---|---|
| PR-01 | Design record: `STORES.md` (ports, record shapes, invariants, questions Q-1 to Q-10 answered), the confirmed ID matrix with a test that compares it with the manifest, criteria AC-501..AC-507, TASKS.md row. Protected path (criteria): owner merge. Hard owner review stop | none |
| PR-02 | Configuration activation and rollback | CT-CFG-01, 03, 04, 05, 06 (5) |
| PR-03 | Idempotency store and replay of results and rejections | CT-ID-01 to 05 (5) |
| PR-04 | Command history, rejection records and feedback status | CT-HIS-01, CT-LC-05, CT-FB-03 (3) |
| PR-05 | Event streams, sequence numbers and the abstract event sink | CT-EV-01 to 05 (5) |
| PR-06 | Replay from history, fixed-seed property test, manifest update, final documents and the review record | CT-DET-02 (1) |

Targets add up to 19. Each implementation PR ships its own tests and updates the manifest for the IDs it covers, so the gate stays green at every step. The split is a delivery order; the task is accepted as a whole.

## 6. Review plan

Interim owner review (D-047), declared not independent. Compensating evidence: one dedicated test per target ID checked by the existing gate, a test that compares the ID matrix with the manifest, negative sequences (duplicate, conflicting, stale, expired and out-of-order inputs), a fixed-seed property test with seed, iteration count and command recorded in the CI evidence (it does not replace the mapped tests), all 94 earlier tests still passing, CI evidence bound to the exact commit. The checklist is `REVIEW.md`, written at closure. A read-only review by a second person is welcome and optional.

## 7. Dependencies

| Dependency | State |
|---|---|
| KOS-MOTION-003 accepted | met (D-121) |
| Baseline that contains this task | not yet: proposal in kritva-program, owner decisions pending |
| `unit-tests`, `readme-check` and `progress-check` required checks | in place (D-104, D-106, D-123) |
| Core security interface | not pinned; authentication and authorization stay supplied inputs |
| Unit gate on Python 3.11 or newer (`make test-unit PYTHON=python3.12`) | in place |

## 8. Questions answered in PR-01

Each is recorded in `STORES.md` as an interpretation or an open contract finding with the owner's answer. None changes the contract.

| Q | Question | Proposed handling |
|---|---|---|
| Q-1 | Contract 7.4 scopes identity to the authenticated client and CT-CFG-06 needs an authorized rollback, but section 16 is PROVISIONAL and the interface is not pinned | Client identity and authorization outcome are supplied inputs, as in KOS-MOTION-002. No claim is made for section 16 and the five CT-AUTH IDs stay DEFERRED |
| Q-2 | Contract 7.4 says the idempotency retention is stated in the configuration and is at least the longest effective execution timeout plus the termination-confirmation bound, but 3.1 does not list the field and open item 6 sets no minimum | PR-01 checks the configuration schema. If the field is absent it is recorded as a contract finding and retention is a validated parameter of the store, checked against that minimum at activation |
| Q-3 | What counts as identical content for 7.4 | A canonical comparison over the command fields of the submission, excluding audit and transport fields, stated in `STORES.md`. Recorded as an interpretation |
| Q-4 | CT-DET-02 replays outcomes from history and configuration, but 15.1 holds lifecycle history, results and references and not the feedback and backend inputs an outcome depends on | Settle in PR-01, or record there that it is settled after PR-04, when the cost is known: either an input journal kept as an implementation aid (not a contract field) or return CT-DET-02 to DEFERRED, which makes the target count 18 |
| Q-5 | Contract 15.2 does not assume permanent storage | An in-memory append-only store with configurable retention. "Never overwrites" is shown by a store interface that has no overwrite operation. No durability claim |
| Q-6 | Contract 14.2 names no transport and 14.4 allows at-least-once or best-effort delivery | An abstract event sink port. Test sinks model failure, duplication and loss. The reference consumer that tolerates duplicates and detects gaps lives in the tests, not in the source |
| Q-7 | The engine of KOS-MOTION-003 must not change semantically, but reading it shows two needed changes: `submit` has no way to receive an idempotency lookup, and the engine fixes one configuration for its life while in-flight commands read per-joint parameters from it | (a) an optional `idempotency` keyword on `submit`, default `NEW`; (b) per-command configuration binding, with a table of configuration versions. Both are listed in `STORES.md` section 7 with the 94 earlier tests as the regression run. If (b) proves larger than a hook, PR-02 stops and returns to the owner |
| Q-8 | The engine already reports `feedback_status` (`MISSING`, `INVALID`, `STALE`, `VALID`), so CT-FB-03 may already hold for existing behavior | PR-04 checks first whether a mapped test is enough. If it is, the ID is closed by mapping and no feedback code is written |
| Q-9 | Contract 3.4 does not say what makes an update incompatible with an active command | A minimum rule in `STORES.md` (the update removes the command's joint, drops its mode, or narrows a limit below an in-flight request); anything beyond it is an open contract finding |
| Q-10 | Contract 3.3 names `config_digest` and defines no algorithm | SHA-256 over canonical JSON, recorded as an interpretation and a contract finding |

The design proposal in kritva-program lists Q-1 to Q-7; Q-8 to Q-10 were found while reading the engine and are added here. The interpretation points I-27, I-32, I-34 and I-35 left open by KOS-MOTION-003 are reviewed in PR-01 for any effect on this task.

## 9. Honest limits

Software evidence only. 11 IDs outside the targets stay DEFERRED or OUT_OF_SCOPE. Contract section 16 stays PROVISIONAL, the contract stays a draft and no tag is created by this task. The integration and regression gates still exit 3 (NOT_IMPLEMENTED).
