"""CT-FB-03 (contract 11.2 and 11.3), KOS-MOTION-005 PR-04: the feedback status of a joint is VALID, STALE,
INVALID or MISSING, reported distinctly and never as valid when it is not. The engine of KOS-MOTION-003
already reports it; this test is the dedicated mapped test (question Q-8: closed by mapping, no new
feedback code). Deterministic and offline. Software evidence only, never physical or safety validation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402


class TestFeedbackStatus(unittest.TestCase):
    def test_CT_FB_03(self):
        """Stale, invalid and missing feedback are reported distinctly and never as valid (11.2, 11.3)."""
        e = S.engine()
        seen = {}
        s = e.joint_state("joint-1", 0)
        seen["MISSING"] = s
        self.assertEqual((s["feedback_status"], s["is_current"]), ("MISSING", False))
        self.assertNotIn("measured_position", s)                       # missing is explicit: no value is shown
        e.feedback("joint-1", S.sample(0.3), 10, "2026-11-15T00:00:10Z")
        s = e.joint_state("joint-1", 210)                              # age 200 is at the limit: still valid
        self.assertEqual((s["feedback_status"], s["is_current"]), ("VALID", True))
        s = e.joint_state("joint-1", 211)                              # older than max_feedback_age_ms: STALE
        seen["STALE"] = s
        self.assertEqual((s["feedback_status"], s["is_current"]), ("STALE", False))
        res = e.feedback("joint-1", S.sample(0.9, validity="INVALID"), 300)
        s = e.joint_state("joint-1", 300)
        seen["INVALID"] = s
        self.assertEqual((s["feedback_status"], s["is_current"]), ("INVALID", False))
        self.assertEqual(s["measured_position"], 0.3)                  # the invalid 0.9 is never shown as measured state
        self.assertEqual(res.events[0]["data"]["feedback_status"], "INVALID")   # the joint event says the same
        e2 = S.engine()
        e2.feedback("joint-1", S.sample(0.9, validity="INVALID"), 5)   # invalid before any valid sample
        s = e2.joint_state("joint-1", 5)
        self.assertEqual((s["feedback_status"], s["is_current"]), ("INVALID", False))
        self.assertNotIn("measured_position", s)
        e.feedback("joint-1", S.sample(0.4), 310)
        seen["VALID"] = e.joint_state("joint-1", 310)
        self.assertEqual(seen["VALID"]["feedback_status"], "VALID")
        self.assertEqual({k: v["feedback_status"] for k, v in seen.items()},
                         {"MISSING": "MISSING", "STALE": "STALE", "INVALID": "INVALID", "VALID": "VALID"})
        for k in ("MISSING", "STALE", "INVALID"):
            self.assertNotEqual(seen[k]["feedback_status"], "VALID")
            self.assertFalse(seen[k]["is_current"])
        # backend health and feedback validity are independent (11.3)
        e.backend_health("DEGRADED", 311)
        s = e.joint_state("joint-1", 311)
        self.assertEqual((s["feedback_status"], s["backend_status"]), ("VALID", "DEGRADED"))


if __name__ == "__main__":
    unittest.main()
