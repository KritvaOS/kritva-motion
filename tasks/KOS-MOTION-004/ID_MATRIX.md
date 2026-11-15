# KOS-MOTION-004: ID dependency matrix

Derived from `tests/manifest/conformance_manifest.json` and `contract/CONFORMANCE_TEST_PLAN.md` on main (2026-11-15), after KOS-MOTION-005 was accepted. It covers every ID that is not IN_SCOPE: 11 IDs (6 DEFERRED and 5 OUT_OF_SCOPE). The 113 IN_SCOPE IDs of KOS-MOTION-002, 003 and 005 are unchanged and must keep passing. The classification below is proposed and is confirmed by the owner in PR-01. The column "Status now" is the status when this file was written; the manifest is the authority and a test compares the two.

Targets: 6 IDs (all contract 17: capability declaration, dispatch against declared capabilities, no actuator-specific identifier, backend reports driving the lifecycle, swap invariance, termination semantics). The other 5 IDs (CT-AUTH) need the Core security interface, which is not pinned, and stay DEFERRED. After the task the manifest would hold 119 IN_SCOPE, 5 DEFERRED and 0 OUT_OF_SCOPE IDs, 124 in all.

| ID | Status now | Contract | Plan text (shortened) | Class | Decision | Delivery |
|---|---|---|---|---|---|---|
| CT-BE-01 | OUT_OF_SCOPE | 17.2 | A conforming backend declares every capability in 17.2 | Backend interface | Target of KOS-MOTION-004: the simulator declares every item and the validator rejects a declaration that omits one | PR-03 |
| CT-BE-02 | DEFERRED | 17.3 | Motion refuses to dispatch operations the backend does not declare | Backend interface | Target of KOS-MOTION-004: the driver re-checks every outgoing operation against the current declaration | PR-04 |
| CT-BE-03 | OUT_OF_SCOPE | 4.1, 17 | No actuator-specific identifier appears in any public message or error | Backend interface | Target of KOS-MOTION-004: a scan over all public output of the integration scenarios | PR-05 |
| CT-BE-04 | OUT_OF_SCOPE | 17.4 | Backend start, feedback, termination confirmation and fault reports drive the lifecycle as specified | Backend interface | Target of KOS-MOTION-004: every report kind drives the engine through the driver | PR-04 |
| CT-BE-06 | OUT_OF_SCOPE | 17.1 | Swapping the simulator for another conforming backend changes no public behaviour | Backend interface | Target of KOS-MOTION-004: the same scenarios on the simulator and on a second backend give identical public output | PR-05 |
| CT-BE-07 | OUT_OF_SCOPE | 17.5 | Termination request accepted is not confirmation; a partial or unknown outcome is treated as unconfirmed; confirmation is bound to the backend reference and target | Backend interface | Target of KOS-MOTION-004: accepted, confirmed and unconfirmed kept apart, confirmation bound to reference and target | PR-04 |
| CT-AUTH-01 | DEFERRED | 16.2 | Missing, invalid and expired assertions are rejected `UNAUTHENTICATED` | Core security interface | Stays DEFERRED until the interface is pinned (out of scope of KOS-MOTION-004) | - |
| CT-AUTH-02 | DEFERRED | 16.3, 16.4 | Operation and target scope are both checked before acceptance; denials are audited | Core security interface | Stays DEFERRED until the interface is pinned (out of scope of KOS-MOTION-004) | - |
| CT-AUTH-03 | DEFERRED | 16.4 | Internal components receive no implicit authorization | Core security interface | Stays DEFERRED until the interface is pinned (out of scope of KOS-MOTION-004) | - |
| CT-AUTH-04 | DEFERRED | 16.3 | Authorization is evaluated by permission, not by component identity | Core security interface | Stays DEFERRED until the interface is pinned (out of scope of KOS-MOTION-004) | - |
| CT-AUTH-06 | DEFERRED | 7.4, 8.4 | A stored result is returned only to the same authenticated client; other clients cannot learn that a request ID exists | Core security interface | Stays DEFERRED until the interface is pinned (out of scope of KOS-MOTION-004) | - |

Row check: 6 targets + 5 Core security IDs = 11. PR-01 adds a test that compares this table with the manifest. The test `tests/gate/test_id_matrix_005.py` and the lifecycle matrix test pin the earlier classification of the six backend IDs; the PRs that deliver them record the new status in those tests, as KOS-MOTION-005 did.
