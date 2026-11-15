"""Tests of the Execution Backend Interface port (contract 17.4, KOS-MOTION-004 PR-02): the shape of the port.

Whether a backend behaves as the contract says is checked by the conformance tests of the later PRs. Deterministic
and offline. Software evidence only.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kritva_motion.backend import (OPERATIONS, DispatchAnswer, ExecutionBackend, TerminationAnswer, is_backend,  # noqa: E402
                                   missing_operations)
from support import good_declaration  # noqa: E402


class Complete:
    def describe_capabilities(self):
        return good_declaration()

    def dispatch(self, request, now_ms):
        return DispatchAnswer(True, backend_reference="r")

    def request_termination(self, backend_reference, cause, now_ms):
        return TerminationAnswer(True)

    def request_hold(self, backend_reference, joint_id, now_ms):
        return DispatchAnswer(True, backend_reference=backend_reference)

    def release_hold(self, backend_reference, joint_id, now_ms):
        return DispatchAnswer(True, backend_reference=backend_reference)

    def health(self):
        return {"health": "AVAILABLE", "faults": []}

    def poll(self, now_ms):
        return []


class TestPort(unittest.TestCase):
    def test_the_port_has_the_operations_of_17_4(self):
        self.assertEqual(set(OPERATIONS), {"describe_capabilities", "dispatch", "request_termination", "request_hold",
                                           "release_hold", "health", "poll"})
        for name in OPERATIONS:
            self.assertTrue(callable(getattr(ExecutionBackend, name)), name)

    def test_a_complete_implementation_is_a_backend(self):
        self.assertTrue(is_backend(Complete()))
        self.assertEqual(missing_operations(Complete()), [])
        self.assertIsInstance(Complete(), ExecutionBackend)

    def test_a_partial_implementation_names_what_it_lacks(self):
        class Partial:
            def dispatch(self, request, now_ms):
                return DispatchAnswer(False, reason="x")

        self.assertFalse(is_backend(Partial()))
        self.assertEqual(missing_operations(Partial()),
                         ["describe_capabilities", "request_termination", "request_hold", "release_hold", "health", "poll"])

    def test_a_non_callable_attribute_does_not_count(self):
        class Wrong(Complete):
            poll = []

        self.assertEqual(missing_operations(Wrong()), ["poll"])

    def test_the_port_has_no_confirmation_operation_apart_from_poll(self):
        # 17.5: confirmation is a report that arrives through poll, never the return value of request_termination
        self.assertNotIn("confirm_termination", OPERATIONS)


if __name__ == "__main__":
    unittest.main()
