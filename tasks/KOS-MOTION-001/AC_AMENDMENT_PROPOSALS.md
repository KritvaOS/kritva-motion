# Proposed Acceptance Criteria Amendments for KOS-MOTION-001

Status: PROPOSED (revision 4), not accepted. `ACCEPTANCE_CRITERIA.md` is accepted-criteria-never-edited ("Change control", section 10) and is a protected path in `.github/kritva-gate.json`. Nothing in this file changes AC-001 to AC-005. A change is a new criteria version with its own review. The owner decides whether to adopt any of the items below; the design in this task satisfies AC-001 to AC-005 as written without them.

## A. Existing criteria

| Item | Current text | Assessment | Proposal |
|---|---|---|---|
| A-1 | AC-001: "Every command has a defined lifecycle (accepted, running, completed, cancelled, failed) with allowed transitions." | Satisfied as written. The design keeps exactly these five states. Rejection is a submission response, timeout is a failure reason, and `DISPATCH_PENDING` and `TERMINATING` are phases, not states | No text change. Record the mapping (contract 7) as the interpretation of AC-001 |
| A-2 | AC-002: "Units and limits are declared per command and enforced by validation; an out-of-limit command is rejected with a defined error." | SUBSTANTIVE AMENDMENT, not a clarification. Units are declared in each command, but effective limits come from the versioned robot configuration and may be narrowed by optional command constraints. That is not the same as every command declaring its own limits | Either (a) keep the wording and interpret "declared per command" as "units declared in each command and limits declared per command type and joint in versioned configuration", recording that reading in the review, or (b) submit a formal amendment: "Units are declared in each command. Limits are declared in the versioned robot configuration, may be narrowed by command constraints, are discoverable, and are enforced by validation; an out-of-limit command is rejected with a defined error." The owner decides; the criteria are not edited by this task |
| A-3 | AC-003: "Timeout, cancellation and fault behaviour are specified, including the state reported after a fault." | Satisfied by the termination record (contract 10.6), the two-dimension joint state (13.2) and the state-after-fault rule (13.5). Not yet checked against the exact current text of `ACCEPTANCE_CRITERIA.md` in the repository, only against the copy read in this session | None; verify wording at review |

## B. Requirements the design adds that no criterion covers

The contract includes these requirements. If the owner wants them to be acceptance-controlled, they need criteria. If not, they remain design requirements verified by the conformance plan but without acceptance weight.

| Proposed | Criterion (testable) | Verified by |
|---|---|---|
| AC-006 | Feedback validity and freshness are explicit, and completion is established only from valid fresh measured feedback, never from commanded values | CT-FB, CT-CMP |
| AC-007 | Submission is idempotent per client; a reused request ID with different content is rejected | CT-ID |
| AC-008 | Every operation is authorized by permission on operation and target; identity assertions follow the approved Core security interface (blocked until Core is pinned) | CT-AUTH |
| AC-009 | Each accepted command is bound to an immutable configuration version and the history records outcomes, transitions and authorization | CT-CFG, CT-HIS |
| AC-010 | Command and resource events carry sequence numbers; status queries are authoritative | CT-EV |

## C. Items the task cannot close

- AC-008 depends on a pinned Core security interface (README section 7).
- AC-004 needs the safety reviewer. The owner holds that role on an interim basis (D-047) and independence is not met.
- The acceptance standard is itself PROPOSED (PD-005, PD-006), so criteria wording may change again.
