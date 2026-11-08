"""The abstract execution port (contract 17.4): what a backend adapter must offer the engine.

This is a Protocol only. The engine does not call it: it returns backend requests as data and a
later task (KOS-MOTION-004) connects an implementation without changing the lifecycle semantics.
"""
from typing import Any, Protocol


class ExecutionPort(Protocol):
    def dispatch(self, request: dict) -> Any: ...

    def request_termination(self, backend_reference: str, cause: str) -> Any: ...

    def request_hold(self, joint_id: str) -> Any: ...

    def release_hold(self, joint_id: str) -> Any: ...
