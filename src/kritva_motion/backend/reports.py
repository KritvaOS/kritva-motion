"""What a backend says: operation answers and reports (contract 17.4 and 17.5, KOS-MOTION-004).

A backend answers an operation call at once (an answer) and reports later what happened (a report), which the
driver collects with `poll`. The records are plain frozen dataclasses; nothing here is new contract vocabulary:
the report kinds are the contract's own names. `termination_unconfirmed` is not a report: Motion decides it when
the bound passes (17.5). Pure, standard library only, no I/O, no clock.
"""
import math
from dataclasses import dataclass, field
from typing import Optional

from kritva_motion.backend.capabilities import HEALTH_VALUES, ID_PATTERN, Problem

EXECUTION_KINDS = ("execution_started", "execution_rejected", "termination_confirmed",
                   "hold_confirmed", "hold_released", "hold_release_failed")
REPORT_KINDS = EXECUTION_KINDS + ("feedback", "health", "fault", "fault_cleared")
BACKEND_FAULT_CODES = ("BACKEND_UNAVAILABLE", "BACKEND_COMMUNICATION_LOSS", "BACKEND_EXECUTION_FAILURE")  # ERROR_CODES.md
FEEDBACK_VALIDITY = ("VALID", "INVALID")


class ReportError(ValueError):
    """A report or an answer that is not well formed."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(str(p) for p in self.problems))


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _text(v):
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Report:
    """One backend report. Only the fields of its kind are used (see validate_report)."""
    kind: str
    backend_reference: Optional[str] = None   # execution reports: the opaque reference Motion gave at dispatch
    target: Optional[dict] = None             # termination_confirmed: the logical target {"type": "joint", "id": ...}
    joint_id: Optional[str] = None            # feedback; optional on hold reports
    reason: Optional[str] = None              # execution_rejected (required), hold_release_failed (optional)
    record: Optional[dict] = None             # feedback: contract 11.1 record
    health: Optional[str] = None              # health
    code: Optional[str] = None                # fault, fault_cleared
    joints: Optional[tuple] = None            # fault, fault_cleared: affected joints, None means every joint
    simulated: bool = False                   # true for a simulator's output (contract 17.7)


def validate_report(report):
    """Return every Problem of a report; an empty list means it is well formed for its kind."""
    out = []
    if not isinstance(report, Report):
        return [Problem("", "a report must be a Report")]
    k = report.kind
    if k not in REPORT_KINDS:
        return [Problem("kind", f"{k!r} is not one of {list(REPORT_KINDS)}")]
    if k in EXECUTION_KINDS and not _text(report.backend_reference):
        out.append(Problem("backend_reference", f"is required for {k}"))
    if k == "termination_confirmed":
        t = report.target
        if not (isinstance(t, dict) and t.get("type") == "joint" and isinstance(t.get("id"), str) and ID_PATTERN.match(t["id"])):
            out.append(Problem("target", "is required: the logical target {type: joint, id} the confirmation is bound to (17.5)"))
    if k == "execution_rejected" and not _text(report.reason):
        out.append(Problem("reason", "is required for execution_rejected"))
    if k == "feedback":
        if not (isinstance(report.joint_id, str) and ID_PATTERN.match(report.joint_id)):
            out.append(Problem("joint_id", "is required for feedback"))
        r = report.record
        if not isinstance(r, dict):
            out.append(Problem("record", "is required for feedback"))
        else:
            if r.get("validity") not in FEEDBACK_VALIDITY:
                out.append(Problem("record.validity", f"must be one of {list(FEEDBACK_VALIDITY)}"))
            elif r["validity"] == "VALID" and not _number(r.get("measured_position")):
                out.append(Problem("record.measured_position", "must be a finite number in a VALID record"))
            if not _number(r.get("backend_timestamp")):
                out.append(Problem("record.backend_timestamp", "must be a finite number"))
            if not _text(r.get("clock_domain")):
                out.append(Problem("record.clock_domain", "must be a non-empty string"))
            if not isinstance(r.get("clock_synchronized"), bool):
                out.append(Problem("record.clock_synchronized", "must be true or false"))
            if "measured_velocity" in r and r["measured_velocity"] is not None and not _number(r["measured_velocity"]):
                out.append(Problem("record.measured_velocity", "must be a finite number or absent"))
    if k == "health" and report.health not in HEALTH_VALUES:
        out.append(Problem("health", f"must be one of {list(HEALTH_VALUES)}"))
    if k == "fault" and report.code not in BACKEND_FAULT_CODES:
        out.append(Problem("code", f"must be one of {list(BACKEND_FAULT_CODES)}"))
    if k == "fault_cleared" and report.code is not None and report.code not in BACKEND_FAULT_CODES:
        out.append(Problem("code", f"must be one of {list(BACKEND_FAULT_CODES)} or absent"))
    if k in ("fault", "fault_cleared") and report.joints is not None:
        if not isinstance(report.joints, tuple) or not all(isinstance(j, str) and ID_PATTERN.match(j) for j in report.joints):
            out.append(Problem("joints", "must be a tuple of joint ids, or None for every joint"))
    return out


def make_report(kind, **fields):
    """Build a Report and raise ReportError unless it is well formed."""
    r = Report(kind=kind, **fields)
    problems = validate_report(r)
    if problems:
        raise ReportError(problems)
    return r


@dataclass(frozen=True)
class DispatchAnswer:
    """The immediate answer to dispatch, request_hold or release_hold (17.4).

    Accepted carries the backend_reference and no reason; rejected carries a reason and no reference. The start
    itself arrives later as a report; an accepted dispatch is not a start (7.2).
    """
    accepted: bool
    backend_reference: Optional[str] = None
    reason: Optional[str] = None
    simulated: bool = False                   # true for a simulator's output (contract 17.7)

    def __post_init__(self):
        problems = []
        if self.accepted:
            if not _text(self.backend_reference):
                problems.append(Problem("backend_reference", "is required when the dispatch is accepted"))
            if self.reason is not None:
                problems.append(Problem("reason", "must be absent when the dispatch is accepted"))
        else:
            if not _text(self.reason):
                problems.append(Problem("reason", "is required when the dispatch is rejected"))
            if self.backend_reference is not None:
                problems.append(Problem("backend_reference", "must be absent when the dispatch is rejected"))
        if problems:
            raise ReportError(problems)


@dataclass(frozen=True)
class TerminationAnswer:
    """The immediate answer to request_termination (17.5): request accepted or refused, never a confirmation.

    `termination_request_accepted` means only that the backend took the request; confirmation is a later
    `termination_confirmed` report bound to a backend_reference and a target.
    """
    accepted: bool
    reason: Optional[str] = None
    simulated: bool = False                   # true for a simulator's output (contract 17.7)

    def __post_init__(self):
        problems = []
        if self.accepted and self.reason is not None:
            problems.append(Problem("reason", "must be absent when the termination request is accepted"))
        if not self.accepted and not _text(self.reason):
            problems.append(Problem("reason", "is required when the termination request is refused"))
        if problems:
            raise ReportError(problems)
