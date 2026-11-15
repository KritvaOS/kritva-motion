"""The Execution Backend Interface as an abstract port (contract 17.1, 17.4, KOS-MOTION-004).

Transport-independent and pull-based (interpretation I-43): the driver calls the operations and collects what the
backend has to say with `poll`. All time is the caller's monotonic reading `now_ms`; a backend never reads a
clock. Motion reaches a backend only through this port (17.1) and owns the interface: an implementation must not
redefine Motion semantics, and the backend reports capability, execution status, feedback and confirmations but
owns no command-level policy (17.6).

`kritva_motion.lifecycle.port.ExecutionPort` keeps its four methods for the engine's request vocabulary; this
port is the complete interface of 17.4 and is what the driver (a later PR) calls. Pure, standard library only.
"""
from typing import Protocol, runtime_checkable

from kritva_motion.backend.reports import DispatchAnswer, Report, TerminationAnswer

OPERATIONS = ("describe_capabilities", "dispatch", "request_termination", "request_hold", "release_hold", "health", "poll")


@runtime_checkable
class ExecutionBackend(Protocol):
    def describe_capabilities(self) -> dict:
        """The capability declaration (capabilities.py), current at the call (17.2)."""

    def dispatch(self, request: dict, now_ms: float) -> DispatchAnswer:
        """Start execution of a validated command (17.4). Accepted or rejected with a backend reason; the start is
        reported later by `execution_started` or `execution_rejected`."""

    def request_termination(self, backend_reference: str, cause: str, now_ms: float) -> TerminationAnswer:
        """Request controlled termination (17.5). Never a confirmation."""

    def request_hold(self, backend_reference: str, joint_id: str, now_ms: float) -> DispatchAnswer:
        """Request a position hold, if supported (17.4)."""

    def release_hold(self, backend_reference: str, joint_id: str, now_ms: float) -> DispatchAnswer:
        """End a hold (17.4)."""

    def health(self) -> dict:
        """Backend health and faults: {"health": AVAILABLE | DEGRADED | UNAVAILABLE | FAULTED, "faults": [codes]} (17.4)."""

    def poll(self, now_ms: float) -> list:
        """The reports the backend has ready at `now_ms`, in the order it produced them, each returned once."""


def missing_operations(candidate):
    """Names of the operations of the port that `candidate` does not provide as callables (empty when complete)."""
    return [name for name in OPERATIONS if not callable(getattr(candidate, name, None))]


def is_backend(candidate):
    """True when `candidate` provides every operation of the port. A shape check only; conformance of its
    declaration and behaviour is checked by the validator and the conformance tests."""
    return not missing_operations(candidate)


__all__ = ["ExecutionBackend", "OPERATIONS", "missing_operations", "is_backend", "DispatchAnswer", "TerminationAnswer", "Report"]
