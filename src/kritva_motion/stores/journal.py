"""Input journal and replay (CT-DET-02, contract 3.3 and 15; KOS-MOTION-005 PR-06).

Contract 15.1 holds the lifecycle of a command but not the feedback, backend and time inputs its outcome
depends on, so replay from history alone cannot reproduce an outcome (question Q-4). The journal is an
implementation aid, not a contract field and not a history field: an append-only, in-memory record of
every input applied to the engine, in order, with the monotonic reading each carried. `RecordingEngine`
wraps an engine and writes the journal as inputs go through; `replay` applies a journal to a fresh
engine. Because the engine is deterministic (CT-DET-01) the replay reproduces every command outcome, the
configuration version and digest each command was bound to, and every fault record.

No durability claim: the journal is a Python list. It reads no clock; time is in the recorded inputs.
"""
import copy

INPUT_METHODS = ("install_configuration", "submit", "dispatch", "execution_started", "feedback", "status_report",
                 "tick", "terminate", "termination_request_accepted", "termination_confirmed",
                 "termination_refused", "hold_confirmed", "hold_released", "hold_release_failed",
                 "backend_health", "joint_fault", "backend_fault", "backend_fault_cleared",
                 "execution_rejected", "update_backend_description")


class ReplayMismatch(Exception):
    """A replayed input behaved differently from the recorded one (it raised, or did not raise)."""


class InputJournal:
    def __init__(self, backend):
        self.backend = copy.deepcopy(backend)    # the backend description the engine was built with
        self._entries = []

    def append(self, method, args, kwargs, raised):
        self._entries.append({"sequence": len(self._entries) + 1, "method": method,
                              "args": copy.deepcopy(args), "kwargs": copy.deepcopy(kwargs), "raised": raised})

    def entries(self):
        return copy.deepcopy(self._entries)

    def __len__(self):
        return len(self._entries)


class RecordingEngine:
    """Delegates to an engine and journals every input method call. Queries pass through unrecorded."""

    def __init__(self, engine, journal):
        self._engine = engine
        self._journal = journal

    def __getattr__(self, name):
        target = getattr(self._engine, name)
        if name not in INPUT_METHODS:
            return target

        def recorded(*args, **kwargs):
            raised = None
            try:
                return target(*args, **kwargs)
            except Exception as exc:
                raised = type(exc).__name__
                raise
            finally:
                self._journal.append(name, args, kwargs, raised)
        return recorded


def replay(journal, engine_factory):
    """Apply a journal to a fresh engine built by `engine_factory(backend)` and return it. An input
    that raised when recorded must raise the same type again, and one that did not must not."""
    engine = engine_factory(copy.deepcopy(journal.backend))
    for entry in journal.entries():
        try:
            getattr(engine, entry["method"])(*entry["args"], **entry["kwargs"])
            raised = None
        except Exception as exc:
            raised = type(exc).__name__
        if raised != entry["raised"]:
            raise ReplayMismatch(f"entry {entry['sequence']} ({entry['method']}): recorded {entry['raised']}, replayed {raised}")
    return engine
