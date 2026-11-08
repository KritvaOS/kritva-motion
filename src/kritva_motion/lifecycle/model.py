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
