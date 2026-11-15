"""kritva-motion stores (KOS-MOTION-005). Standard library only.

Pure, in-memory, deterministic reference implementations of the Motion contract parts that need a
store, an activation step or a publisher. They sit around the KOS-MOTION-003 lifecycle engine, do no
I/O and never read the system clock: time is the injected monotonic reading. Design:
tasks/KOS-MOTION-005/STORES.md. Software evidence only: passing tests is never physical or safety
validation (contract 2.2).
"""
from kritva_motion.stores.config_registry import ConfigurationRegistry, config_digest  # noqa: F401
from kritva_motion.stores.coordinator import Coordinator  # noqa: F401
from kritva_motion.stores.idempotency import IdempotencyStore, content_key, minimum_retention_ms  # noqa: F401
