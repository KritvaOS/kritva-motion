"""Lifecycle model as data: states, phases, the transition table of contract 7.5 and the terminal
reason codes of ERROR_CODES.md section 2. No name here is new: every one is the contract's.
"""
STATES = ("ACCEPTED", "RUNNING", "COMPLETED", "CANCELLED", "FAILED")
TERMINAL_STATES = ("COMPLETED", "CANCELLED", "FAILED")
PHASES = ("NONE", "DISPATCH_PENDING", "TERMINATING")

# Contract 7.5. Key: (from, to). None is "admission". Value: the row label used in LIFECYCLE.md section 3.
TRANSITIONS = {
    (None, "ACCEPTED"): "T1",
    ("ACCEPTED", "RUNNING"): "T2",
    ("ACCEPTED", "CANCELLED"): "T3",
    ("ACCEPTED", "FAILED"): "T4",
    ("RUNNING", "COMPLETED"): "T5",
    ("RUNNING", "CANCELLED"): "T6",
    ("RUNNING", "FAILED"): "T7",
}

# Contract 7.6: the phases a non-terminal state may carry. A terminal command has phase NONE.
PHASES_OF_STATE = {
    "ACCEPTED": ("NONE", "DISPATCH_PENDING", "TERMINATING"),
    "RUNNING": ("NONE", "TERMINATING"),
    "COMPLETED": ("NONE",),
    "CANCELLED": ("NONE",),
    "FAILED": ("NONE",),
}

# ERROR_CODES.md section 2, by terminal state.
REASON_CODES = {
    "COMPLETED": ("GOAL_REACHED", "DURATION_ELAPSED", "STOP_CONFIRMED", "HOLD_ENGAGED", "CANCEL_EFFECTIVE", "FAULT_CLEARED"),
    "CANCELLED": ("CANCEL_REQUESTED", "STOPPED"),
    "FAILED": ("DEADLINE_EXPIRED", "EXECUTION_TIMEOUT", "TERMINATION_UNCONFIRMED", "BACKEND_REJECTED_DISPATCH",
               "FEEDBACK_LOST", "TRACKING_ERROR", "JOINT_LIMIT_VIOLATION", "BACKEND_UNAVAILABLE",
               "BACKEND_COMMUNICATION_LOSS", "BACKEND_EXECUTION_FAILURE", "INTERNAL_ERROR"),
}


class IllegalTransition(Exception):
    """A lifecycle change that contract 7.5 does not list. It never changes any state."""


def is_allowed(frm, to):
    """True when contract 7.5 lists the transition between two existing states (admission is T1)."""
    return frm is not None and (frm, to) in TRANSITIONS


def check_transition(frm, to, reason_code):
    """Raise IllegalTransition unless (frm, to) is in the table and reason_code fits the target state.

    Only a terminal state carries a reason code from ERROR_CODES.md section 2. A non-terminal
    transition carries None, because the contract defines no reason code for it (interpretation I-14).
    """
    if not is_allowed(frm, to):
        raise IllegalTransition(f"{frm} -> {to} is not a transition of contract 7.5")
    if to in TERMINAL_STATES:
        if reason_code not in REASON_CODES[to]:
            raise IllegalTransition(f"{reason_code!r} is not a {to} reason code")
    elif reason_code is not None:
        raise IllegalTransition(f"a transition to {to} carries no reason code")


# Contract 10.5 and 10.6: the causes a termination record may hold, in the order ERROR_CODES.md section 4 lists them.
CAUSES = ("CANCEL_REQUESTED", "STOP_REQUESTED", "EXECUTION_TIMEOUT", "DEADLINE_EXPIRED", "FAULT")
TIMER_CAUSES = ("EXECUTION_TIMEOUT", "DEADLINE_EXPIRED")


def outcome_of_causes(causes):
    """The terminal state and reason a confirmed termination gives (contract 10.6 rule 2).

    causes: the recorded causes in the order the engine appended them. A timeout or deadline cause
    gives FAILED with the one recorded first; only cancel and stop causes give CANCELLED, with reason
    STOPPED if any STOP_REQUESTED is present and CANCEL_REQUESTED otherwise. A FAULT cause gives
    FAILED with the fault code and is handled where faults exist (PR-05); here it raises.
    """
    causes = list(causes)
    if not causes:
        raise IllegalTransition("a termination record needs at least one cause")
    for c in causes:
        if c not in CAUSES:
            raise IllegalTransition(f"{c!r} is not a termination cause")
    if "FAULT" in causes:
        raise NotImplementedError("a FAULT cause belongs to PR-05 of KOS-MOTION-003")
    for c in causes:
        if c in TIMER_CAUSES:
            return "FAILED", c
    return "CANCELLED", "STOPPED" if "STOP_REQUESTED" in causes else "CANCEL_REQUESTED"
