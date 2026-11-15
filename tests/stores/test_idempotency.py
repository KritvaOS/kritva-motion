"""Tests of the idempotency store (contract 7.3 and 7.4), KOS-MOTION-005 PR-03.

The five CT-ID methods are the single executable tests named by the IN_SCOPE manifest entries for
CT-ID-01 to CT-ID-05 (method name = ID with hyphens replaced by underscores). The other classes are
negative cases. Deterministic and offline: time is the injected monotonic reading; no system clock,
randomness or network. Software evidence only, never physical or safety validation.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.stores import (ConfigurationRegistry, Coordinator, IdempotencyStore, content_key,  # noqa: E402
                                  minimum_retention_ms)

RETENTION = 20000
A, B = "client-A", "client-B"


def setup(retention=RETENTION):
    e = LifecycleEngine(None, copy.deepcopy(S.base.BACKEND), None)
    store = IdempotencyStore(retention)
    reg = ConfigurationRegistry(e, S.base.CAPS, store)
    assert reg.activate(copy.deepcopy(S.base.CONFIG), 0)["outcome"] == "ACTIVATED"
    S.ready(e, "joint-1", t=0)
    S.ready(e, "joint-p", t=0)
    return e, store, Coordinator(e, store), reg


def prismatic(target=0.2, **over):
    return S.pos_cmd(target, "joint-p", unit="m", **over)


class TestIdempotencyConformance(unittest.TestCase):
    def test_CT_ID_01(self):
        """An identical resubmission returns the original result with the replay flag and creates no second
        command (7.4)."""
        e, store, co, _ = setup()
        first = co.submit(A, S.pos_cmd(0.5), 10)
        self.assertTrue(first.admission.accepted)
        self.assertFalse(first.admission.replay)
        again = co.submit(A, S.pos_cmd(0.5), 50)
        self.assertTrue(again.admission.accepted)
        self.assertTrue(again.admission.replay)
        self.assertEqual(again.command_id, first.command_id)
        self.assertEqual(len(e.commands()), 1)
        self.assertEqual((again.events, again.requests), ([], []))
        before = e.command(first.command_id)
        co.submit(A, S.pos_cmd(0.5), 60)
        self.assertEqual(e.command(first.command_id), before)       # a replay changes nothing
        stored = store.live_entries(60)[0]["decision"]
        self.assertEqual((stored["config_version"], stored["config_digest"]),
                         (before["config_version"], before["config_digest"]))

    def test_CT_ID_02(self):
        """The same request ID with different content is REQUEST_ID_CONFLICT, and no command is created (7.4)."""
        e, store, co, _ = setup()
        first = co.submit(A, S.pos_cmd(0.5), 10)
        for label, other in (("target", S.pos_cmd(0.4)), ("deadline", S.pos_cmd(0.5, deadline_ms=9000)),
                             ("constraints", S.pos_cmd(0.5, constraints={"max_velocity": 0.5}))):
            with self.subTest(label):
                r = co.submit(A, other, 20)
                self.assertFalse(r.admission.accepted)
                self.assertEqual((r.admission.code, r.admission.step), ("REQUEST_ID_CONFLICT", 4))
                self.assertFalse(r.admission.replay)
                self.assertIsNone(r.command_id)
        self.assertEqual(len(e.commands()), 1)
        self.assertTrue(co.submit(A, S.pos_cmd(0.5), 30).admission.replay)   # the original is still the stored one
        self.assertEqual(co.submit(A, S.pos_cmd(0.5), 31).command_id, first.command_id)

    def test_CT_ID_03(self):
        """Request identity is scoped to the client: the same ID from another client is an independent request (7.4)."""
        e, store, co, _ = setup()
        a = co.submit(A, S.pos_cmd(0.5), 10)
        b = co.submit(B, prismatic(0.2), 20)       # same client_request_id, other client, other content: no conflict
        self.assertTrue(b.admission.accepted)
        self.assertFalse(b.admission.replay)
        self.assertNotEqual(b.command_id, a.command_id)
        self.assertEqual(len(e.commands()), 2)
        same = co.submit(B, S.pos_cmd(0.5, client_request_id="req-9"), 30)   # A's content from B is judged on its own
        self.assertFalse(same.admission.replay)
        self.assertEqual(same.admission.code, "TARGET_BUSY")
        self.assertEqual(sorted(e["client_id"] for e in store.live_entries(30)), [A, B, B])   # three requests, two clients

    def test_CT_ID_04(self):
        """A replayed rejection returns the same rejection and creates no command (7.3)."""
        e, store, co, _ = setup()
        bad = S.pos_cmd(5.0)
        first = co.submit(A, bad, 10)
        self.assertFalse(first.admission.accepted)
        self.assertEqual(first.admission.code, "LIMIT_POSITION")
        self.assertIsNone(first.command_id)
        again = co.submit(A, copy.deepcopy(bad), 20)
        self.assertFalse(again.admission.accepted)
        self.assertTrue(again.admission.replay)
        self.assertEqual(again.admission.code, "LIMIT_POSITION")
        self.assertIsNone(again.command_id)
        self.assertEqual(e.commands(), [])
        stored = store.live_entries(20)[0]["decision"]
        self.assertEqual((stored["accepted"], stored["code"], stored["command_id"]), (False, "LIMIT_POSITION", None))

    def test_CT_ID_05(self):
        """After the retention period a reused ID is a new request (7.4)."""
        e, store, co, _ = setup(retention=RETENTION)
        self.assertEqual(co.submit(A, S.pos_cmd(5.0), 100).admission.code, "LIMIT_POSITION")
        self.assertTrue(co.submit(A, S.pos_cmd(5.0), 100 + RETENTION - 1).admission.replay)   # still inside
        late = co.submit(A, S.pos_cmd(5.0), 100 + RETENTION)          # at the expiry: a new request, judged again
        self.assertFalse(late.admission.replay)
        self.assertEqual(late.admission.code, "LIMIT_POSITION")
        # the same ID with different content after expiry is not a conflict but a new, accepted request
        e2, store2, co2, _ = setup(retention=RETENTION)
        co2.submit(A, S.pos_cmd(5.0), 100)
        e2.feedback("joint-1", S.sample(0.0), 100 + RETENTION)      # feedback is fresh again after the long wait
        fresh = co2.submit(A, S.pos_cmd(0.5), 100 + RETENTION)
        self.assertTrue(fresh.admission.accepted)
        self.assertFalse(fresh.admission.replay)
        self.assertEqual(len(e2.commands()), 1)


class TestStoreNegativeCases(unittest.TestCase):
    def test_audit_and_transport_fields_do_not_make_content_different(self):
        e, store, co, _ = setup()
        a = S.pos_cmd(0.5, issued_at="2026-11-15T00:00:00Z", identity_assertion="token-1")
        b = S.pos_cmd(0.5, issued_at="2026-11-15T00:00:09Z", identity_assertion="token-2")
        self.assertEqual(content_key(a), content_key(b))
        first = co.submit(A, a, 10)
        self.assertEqual(co.submit(A, b, 11).command_id, first.command_id)

    def test_rejections_before_the_lookup_are_not_recorded(self):
        e, store, co, _ = setup()
        r = co.submit(A, S.pos_cmd(0.5), 10, identity="INVALID")
        self.assertEqual(r.admission.code, "UNAUTHENTICATED")
        self.assertEqual(store.live_entries(10), [])
        self.assertTrue(co.submit(A, S.pos_cmd(0.5), 11).admission.accepted)

    def test_conflict_is_not_recorded_as_an_original_decision(self):
        e, store, co, _ = setup()
        co.submit(A, S.pos_cmd(0.5), 10)
        co.submit(A, S.pos_cmd(0.4), 11)
        self.assertEqual(len(store.live_entries(11)), 1)
        self.assertEqual(store.live_entries(11)[0]["decision"]["accepted"], True)

    def test_a_live_entry_is_never_overwritten(self):
        store = IdempotencyStore(1000)
        self.assertTrue(store.record(A, "r", S.pos_cmd(0.5), {"accepted": True, "code": None}, 0))
        self.assertFalse(store.record(A, "r", S.pos_cmd(0.4), {"accepted": False, "code": "X"}, 10))
        self.assertEqual(store.lookup(A, "r", S.pos_cmd(0.5), 20)["stored_decision"]["accepted"], True)
        self.assertTrue(store.record(A, "r", S.pos_cmd(0.4), {"accepted": False, "code": "X"}, 1000))   # expired: new

    def test_lookup_returns_copies_and_does_not_extend_retention(self):
        store = IdempotencyStore(1000)
        store.record(A, "r", S.pos_cmd(0.5), {"accepted": True, "code": None}, 0)
        got = store.lookup(A, "r", S.pos_cmd(0.5), 500)
        got["stored_decision"]["accepted"] = False
        self.assertTrue(store.lookup(A, "r", S.pos_cmd(0.5), 999)["stored_decision"]["accepted"])
        self.assertEqual(store.lookup(A, "r", S.pos_cmd(0.5), 1000)["status"], "NEW")

    def test_unusable_keys_are_not_stored(self):
        store = IdempotencyStore(1000)
        for client, req in ((None, "r"), ("", "r"), (A, None), (A, ""), (A, 7)):
            with self.subTest(client=client, req=req):
                self.assertFalse(store.record(client, req, S.pos_cmd(0.5), {"accepted": True}, 0))
                self.assertEqual(store.lookup(client, req, S.pos_cmd(0.5), 1), {"status": "NEW"})

    def test_bad_retention_values_are_refused(self):
        for bad in (0, -1, None, True, "5"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    IdempotencyStore(bad)


class TestRetentionMinimum(unittest.TestCase):
    def test_minimum_is_longest_execution_timeout_plus_termination_bound(self):
        self.assertEqual(minimum_retention_ms(S.base.CONFIG), 10000 + 1000)

    def test_activation_with_too_short_a_retention_is_refused(self):
        e = LifecycleEngine(None, copy.deepcopy(S.base.BACKEND), None)
        reg = ConfigurationRegistry(e, S.base.CAPS, IdempotencyStore(10999))
        rec = reg.activate(copy.deepcopy(S.base.CONFIG), 0)
        self.assertEqual((rec["outcome"], rec["refusal"]), ("REFUSED", "RETENTION_TOO_SHORT"))
        self.assertIsNone(reg.active_version)
        ok = ConfigurationRegistry(LifecycleEngine(None, copy.deepcopy(S.base.BACKEND), None), S.base.CAPS,
                                   IdempotencyStore(11000))
        self.assertEqual(ok.activate(copy.deepcopy(S.base.CONFIG), 0)["outcome"], "ACTIVATED")


class TestEngineHook(unittest.TestCase):
    def test_default_idempotency_is_new_and_behavior_is_unchanged(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1)
        self.assertTrue(r.admission.accepted)
        self.assertFalse(r.admission.replay)

    def test_a_supplied_conflict_rejects_at_step_four(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1, idempotency={"status": "DIFFERENT"})
        self.assertEqual((r.admission.code, r.admission.step), ("REQUEST_ID_CONFLICT", 4))
        self.assertEqual(e.commands(), [])


if __name__ == "__main__":
    unittest.main()
