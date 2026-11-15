"""kritva-motion runtime (KOS-MOTION-004). Standard library only.

The driver is the only place where the lifecycle engine, the stores and an execution backend meet. It has no
clock, no thread and no I/O of its own: time is the caller's injected monotonic reading. Design:
tasks/KOS-MOTION-004/BACKEND.md section 4. Software evidence only: passing tests is never physical or safety
validation (contract 2.2, 17.7).
"""
from kritva_motion.runtime.driver import Driver, DriverError  # noqa: F401
