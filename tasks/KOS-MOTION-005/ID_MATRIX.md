# KOS-MOTION-005: ID dependency matrix

Derived from `tests/manifest/conformance_manifest.json` and `contract/CONFORMANCE_TEST_PLAN.md` on main (2026-11-15). It covers every ID that is not IN_SCOPE: 30 IDs (25 DEFERRED and 5 OUT_OF_SCOPE). The 94 IN_SCOPE IDs of KOS-MOTION-002 and KOS-MOTION-003 are unchanged and must keep passing. The classification below is proposed and is confirmed by the owner in PR-01. The column "Status now" is the status when this file was written; the manifest is the source of truth and the manifest wins where this file differs.

Targets: 19 IDs (5 configuration activation, 5 idempotency, 3 history and feedback status, 5 events, 1 replay). CT-DET-02 is the least certain target: contract 15.1 does not list the feedback and backend inputs that a replay of an outcome would need (task record question Q-4), so PR-01 may return it to DEFERRED and the target count would become 18. The other 11 IDs stay outside this task: 5 need the Core security interface, which is not pinned; CT-BE-02 and the 5 OUT_OF_SCOPE backend IDs belong to the candidate task KOS-MOTION-004 (backend interface, simulator, integration and regression gates); neither is registered.

| ID | Status now | Contract | Plan text (shortened) | Class | Decision | Delivery |
|---|---|---|---|---|---|---|
| CT-CFG-01 | DEFERRED | 3.2 | Submissions are rejected `CONFIG_NOT_ACTIVE` until a configuration validates | Configuration activation | Target of KOS-MOTION-005 | PR-02 |
| CT-CFG-03 | DEFERRED | 3.3 | Accepted commands record the configuration version and digest | Configuration activation | Target of KOS-MOTION-005 | PR-02 |
| CT-CFG-04 | DEFERRED | 3.3, 3.4 | A configuration update during execution leaves the active command bound to the old version | Configuration activation | Target of KOS-MOTION-005 | PR-02 |
| CT-CFG-05 | DEFERRED | 3.4 | An incompatible update is refused while affected commands are active | Configuration activation | Target of KOS-MOTION-005 | PR-02 |
| CT-CFG-06 | DEFERRED | 3.4 | Rollback is explicit, authorized and traceable | Configuration activation | Target of KOS-MOTION-005 | PR-02 |
| CT-ID-01 | DEFERRED | 7.4 | Identical resubmission returns the original result with `idempotent_replay = true` and creates no second command | Idempotency store | Target of KOS-MOTION-005 | PR-03 |
| CT-ID-02 | DEFERRED | 7.4 | Same ID, different content: `REQUEST_ID_CONFLICT` | Idempotency store | Target of KOS-MOTION-005 | PR-03 |
| CT-ID-03 | DEFERRED | 7.4 | Same `client_request_id` from a different client is an independent request | Idempotency store | Target of KOS-MOTION-005 | PR-03 |
| CT-ID-04 | DEFERRED | 7.3 | A replayed rejection returns the same rejection | Idempotency store | Target of KOS-MOTION-005 | PR-03 |
| CT-ID-05 | DEFERRED | 7.4 | After retention expiry a reused ID is a new request | Idempotency store | Target of KOS-MOTION-005 | PR-03 |
| CT-FB-03 | DEFERRED | 11.2, 11.3 | Stale, invalid and missing feedback are reported distinctly and never as valid | History and feedback status | Target of KOS-MOTION-005 (CT-LC-05: the rejection and history half; the lifecycle half is covered by KOS-MOTION-003) | PR-04 |
| CT-HIS-01 | DEFERRED | 15 | History retains every field in 15.1, distinguishes rejected from accepted, and never overwrites | History and feedback status | Target of KOS-MOTION-005 (CT-LC-05: the rejection and history half; the lifecycle half is covered by KOS-MOTION-003) | PR-04 |
| CT-LC-05 | DEFERRED | 7.3, 15 | Rejected submissions have no `command_id` and no lifecycle, and appear in history | History and feedback status | Target of KOS-MOTION-005 (CT-LC-05: the rejection and history half; the lifecycle half is covered by KOS-MOTION-003) | PR-04 |
| CT-EV-01 | DEFERRED | 14.4 | Sequence numbers increase by one per stream; gaps are detectable | Event publisher | Target of KOS-MOTION-005 | PR-05 |
| CT-EV-02 | DEFERRED | 14.4 | Duplicate delivery is tolerated; status query is authoritative after loss | Event publisher | Target of KOS-MOTION-005 | PR-05 |
| CT-EV-03 | DEFERRED | 14.2 | Execution continues when no subscriber is attached or notification delivery fails | Event publisher | Target of KOS-MOTION-005 | PR-05 |
| CT-EV-04 | DEFERRED | 14.3 | Joint and backend changes appear in their own streams, not in command streams | Event publisher | Target of KOS-MOTION-005 | PR-05 |
| CT-EV-05 | DEFERRED | 14.4 | Clients tolerate transports that are best effort: gaps are detected only where sequence continuity is provided, and state queries recover | Event publisher | Target of KOS-MOTION-005 | PR-05 |
| CT-DET-02 | DEFERRED | 3.3, 15 | Replay from history and configuration reproduces command outcomes | Replay from history | Target of KOS-MOTION-005, classification to be confirmed in PR-01 (Q-4); stays DEFERRED if the history of contract 15.1 cannot reproduce outcomes | PR-06 |
| CT-BE-02 | DEFERRED | 17.3 | Motion refuses to dispatch operations the backend does not declare | Backend interface | Stays DEFERRED (candidate KOS-MOTION-004) | - |
| CT-BE-01 | OUT_OF_SCOPE | 17.2 | A conforming backend declares every capability in 17.2 | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-03 | OUT_OF_SCOPE | 4.1, 17 | No actuator-specific identifier appears in any public message or error | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-04 | OUT_OF_SCOPE | 17.4 | Backend start, feedback, termination confirmation and fault reports drive the lifecycle as specified | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-06 | OUT_OF_SCOPE | 17.1 | Swapping the simulator for another conforming backend changes no public behaviour | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-BE-07 | OUT_OF_SCOPE | 17.5 | Termination request accepted is not confirmation; a partial or unknown outcome is treated as unconfirmed; confirmation is bound to the backend reference and target | Backend interface or simulator | Stays OUT_OF_SCOPE (candidate KOS-MOTION-004) | - |
| CT-AUTH-01 | DEFERRED | 16.2 | Missing, invalid and expired assertions are rejected `UNAUTHENTICATED` | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-02 | DEFERRED | 16.3, 16.4 | Operation and target scope are both checked before acceptance; denials are audited | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-03 | DEFERRED | 16.4 | Internal components receive no implicit authorization | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-04 | DEFERRED | 16.3 | Authorization is evaluated by permission, not by component identity | Core security interface | Stays DEFERRED until the interface is pinned | - |
| CT-AUTH-06 | DEFERRED | 7.4, 8.4 | A stored result is returned only to the same authenticated client; other clients cannot learn that a request ID exists | Core security interface | Stays DEFERRED until the interface is pinned | - |

Row check: 19 targets + 5 Core security IDs + 1 backend DEFERRED ID + 5 OUT_OF_SCOPE backend IDs = 30. PR-01 adds a test that compares this table with the manifest.
