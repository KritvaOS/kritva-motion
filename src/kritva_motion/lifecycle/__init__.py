"""kritva-motion lifecycle engine (KOS-MOTION-003). Standard library only.

A pure, in-memory, deterministic reference implementation of the Motion lifecycle, termination and
fault semantics of the contract. It talks to no backend, stores nothing, publishes nothing and never
reads the system clock. Design: tasks/KOS-MOTION-003/LIFECYCLE.md. Software evidence only: passing
tests is never physical or safety validation (contract 2.2).
"""
from kritva_motion.lifecycle.engine import ClockError, LifecycleEngine, Result  # noqa: F401
from kritva_motion.lifecycle.model import IllegalTransition  # noqa: F401
