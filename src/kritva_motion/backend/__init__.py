"""Execution backend interface of the Motion contract (contract 17, KOS-MOTION-004).

The port, the capability declaration with its validator and the report and answer records. The simulator and the
runtime driver come in later pull requests. Standard library only; this package imports no other Motion module.
"""
from kritva_motion.backend.capabilities import Problem, is_conforming, validate_declaration
from kritva_motion.backend.interface import ExecutionBackend, OPERATIONS, is_backend, missing_operations
from kritva_motion.backend.reports import (BACKEND_FAULT_CODES, REPORT_KINDS, DispatchAnswer, Report, ReportError,
                                           TerminationAnswer, make_report, validate_report)

__all__ = ["Problem", "validate_declaration", "is_conforming", "ExecutionBackend", "OPERATIONS", "is_backend",
           "missing_operations", "Report", "ReportError", "REPORT_KINDS", "BACKEND_FAULT_CODES", "DispatchAnswer",
           "TerminationAnswer", "make_report", "validate_report"]
