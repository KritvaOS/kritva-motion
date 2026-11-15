"""Tests of configuration activation and rollback (contract 3.2 to 3.4), KOS-MOTION-005 PR-02.

The five CT-CFG methods are the single executable tests named by the IN_SCOPE manifest entries for
CT-CFG-01, 03, 04, 05 and 06 (method name = ID with hyphens replaced by underscores). The other
classes are negative cases and checks of the engine hook. Deterministic and offline: no clock, no
randomness, no network. They show that activation follows the contract for supplied, ordered inputs;
software evidence only, never physical or safety validation.
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
from kritva_motion.stores import ConfigurationRegistry, config_digest  # noqa: E402

CAPS, BACKEND, joint = S.base.CAPS, S.base.BACKEND, S.base.joint


def cfg(version, **joint_1_over):
    c = copy.deepcopy(S.base.CONFIG)
    c["config_version"] = version
    c["joints"][0] = joint(**joint_1_over)
    return c


def fresh():
    """An engine with no configuration and a registry over it."""
    e = LifecycleEngine(None, copy.deepcopy(BACKEND), None)
    return e, ConfigurationRegistry(e, CAPS)


def active(version="1", **over):
    e, reg = fresh()
    assert reg.activate(cfg(version, **over), 0)["outcome"] == "ACTIVATED"
    S.ready(e, t=0)
    return e, reg



class TestConfigurationConformance(unittest.TestCase):
    def test_CT_CFG_01(self):
        """No command is accepted until a configuration is validated and active (3.2)."""
        e, reg = fresh()
        r = e.submit(S.pos_cmd(), 1)
        self.assertFalse(r.admission.accepted)
        self.assertEqual(r.admission.code, "CONFIG_NOT_ACTIVE")
        self.assertIsNone(r.command_id)
        bad = cfg("1")
        del bad["joints"]
        rec = reg.activate(bad, 2)
        self.assertEqual((rec["outcome"], rec["refusal"]), ("REFUSED", "INVALID_CONFIGURATION"))
        self.assertIsNone(reg.active_version)
        self.assertEqual(e.submit(S.pos_cmd(), 3).admission.code, "CONFIG_NOT_ACTIVE")
        self.assertEqual(reg.activate(cfg("1"), 4)["outcome"], "ACTIVATED")
        S.ready(e, t=5)
        self.assertTrue(e.submit(S.pos_cmd(), 6).admission.accepted)

    def test_CT_CFG_03(self):
        """An accepted command records the version and digest of the configuration active at admission (3.3)."""
        e, reg = active("7")
        expect = config_digest(cfg("7"))
        self.assertEqual(reg.digest_of("7"), expect)
        self.assertEqual(len(expect), 64)
        r = e.submit(S.pos_cmd(), 1)
        c = e.command(r.command_id)
        self.assertEqual((c["config_version"], c["config_digest"]), ("7", expect))
        self.assertEqual(e.joint_state("joint-1", 1)["config_version"], "7")
        self.assertEqual(config_digest(cfg("7")), config_digest(copy.deepcopy(cfg("7"))))
        self.assertNotEqual(config_digest(cfg("7")), config_digest(cfg("8")))

    def test_CT_CFG_04(self):
        """An activation applies only to commands accepted after it; an earlier command keeps its version
        and its own parameters for its whole life (3.3, 3.4)."""
        e, reg = active("1", settling_duration_ms=100, termination_confirm_timeout_ms=1000)
        r1 = e.submit(S.pos_cmd(target=0.5), 1)
        e.execution_started(r1.command_id, e.command(r1.command_id)["backend_reference"], 2)
        rec = reg.activate(cfg("2", settling_duration_ms=5000, termination_confirm_timeout_ms=7000), 3)
        self.assertEqual(rec["outcome"], "ACTIVATED")
        self.assertEqual(e.command(r1.command_id)["config_version"], "1")
        # the earlier command settles by its own 100 ms window, not by version 2's 5000 ms
        e.feedback("joint-1", S.sample(0.5), 10)
        e.feedback("joint-1", S.sample(0.5), 120)
        self.assertEqual(e.command(r1.command_id)["state"], "COMPLETED")
        # a later command is bound to version 2 and uses its parameters
        r2 = e.submit(S.pos_cmd(target=0.4, client_request_id="req-2") if False else
                      S.env("SET_POSITION", "joint-1", parameters={"target_position": 0.4, "unit": "rad"},
                            client_request_id="req-2"), 130)
        self.assertTrue(r2.admission.accepted)
        self.assertEqual(e.command(r2.command_id)["config_version"], "2")
        self.assertEqual(e.command(r2.command_id)["config_digest"], reg.digest_of("2"))
        e.execution_started(r2.command_id, e.command(r2.command_id)["backend_reference"], 131)
        e.feedback("joint-1", S.sample(0.4), 140)
        e.feedback("joint-1", S.sample(0.4), 300)
        self.assertEqual(e.command(r2.command_id)["state"], "RUNNING")     # 5000 ms window not yet over
        e.terminate(r2.command_id, "CANCEL_REQUESTED", 310)
        self.assertEqual(e.command(r2.command_id)["termination"]["bound_ms"], 7000)

    def test_earlier_command_keeps_its_termination_bound(self):
        e, reg = active("1", termination_confirm_timeout_ms=1000)
        r1 = e.submit(S.pos_cmd(), 1)
        e.execution_started(r1.command_id, e.command(r1.command_id)["backend_reference"], 2)
        reg.activate(cfg("2", termination_confirm_timeout_ms=9000), 3)
        e.terminate(r1.command_id, "CANCEL_REQUESTED", 4)
        self.assertEqual(e.command(r1.command_id)["termination"]["bound_ms"], 1000)

    def test_CT_CFG_05(self):
        """An update that is incompatible with an active command is refused with an explicit report (3.4)."""
        e, reg = active("1")
        r1 = e.submit(S.pos_cmd(target=1.2), 1)
        e.execution_started(r1.command_id, e.command(r1.command_id)["backend_reference"], 2)
        rec = reg.activate(cfg("2", position_max=1.0), 3)
        self.assertEqual((rec["outcome"], rec["refusal"]), ("REFUSED", "INCOMPATIBLE_WITH_OPEN_COMMANDS"))
        self.assertEqual(rec["detail"], [{"command_id": r1.command_id, "joint_id": "joint-1",
                                          "reason": "POSITION_LIMIT_NARROWED"}])
        self.assertEqual(reg.active_version, "1")
        self.assertEqual(e.active_configuration_version(), "1")
        self.assertIsNone(reg.digest_of("2"))
        self.assertEqual(reg.history()[-1]["refusal"], "INCOMPATIBLE_WITH_OPEN_COMMANDS")
        # once the command is terminal the same update is accepted
        e.terminate(r1.command_id, "CANCEL_REQUESTED", 4)
        e.termination_request_accepted(r1.command_id, e.command(r1.command_id)["backend_reference"], 5)
        e.termination_confirmed(r1.command_id, e.command(r1.command_id)["backend_reference"], 6)
        self.assertEqual(e.command(r1.command_id)["state"], "CANCELLED")
        self.assertEqual(reg.activate(cfg("2", position_max=1.0), 7)["outcome"], "ACTIVATED")

    def test_CT_CFG_06(self):
        """Rollback is explicit, needs a granted authorization result and is traceable (3.4)."""
        e, reg = active("1")
        reg.activate(cfg("2", position_max=1.4), 1)
        refused = reg.rollback("1", 2)
        self.assertEqual((refused["outcome"], refused["refusal"]), ("REFUSED", "NOT_AUTHORIZED"))
        self.assertEqual(reg.active_version, "2")
        self.assertEqual(reg.rollback("1", 3, permission_granted=False)["refusal"], "NOT_AUTHORIZED")
        done = reg.rollback("1", 4, permission_granted=True)
        self.assertEqual((done["outcome"], done["kind"], done["previous_version"]), ("ACTIVATED", "ROLLBACK", "2"))
        self.assertEqual(reg.active_version, "1")
        self.assertEqual(e.active_configuration_version(), "1")
        self.assertEqual(done["digest"], reg.digest_of("1"))
        r = e.submit(S.pos_cmd(), 5)
        self.assertEqual(e.command(r.command_id)["config_version"], "1")
        log = reg.history()
        self.assertEqual([x["sequence"] for x in log], list(range(1, len(log) + 1)))
        self.assertEqual([(x["kind"], x["outcome"]) for x in log],
                         [("ACTIVATE", "ACTIVATED"), ("ACTIVATE", "ACTIVATED"), ("ROLLBACK", "REFUSED"),
                          ("ROLLBACK", "REFUSED"), ("ROLLBACK", "ACTIVATED")])


class TestActivationNegativeCases(unittest.TestCase):
    def test_reused_version_is_refused_and_changes_nothing(self):
        e, reg = active("1")
        self.assertEqual(reg.activate(cfg("1", position_max=1.0), 1)["refusal"], "VERSION_ALREADY_KNOWN")
        self.assertEqual(reg.digest_of("1"), config_digest(cfg("1")))

    def test_unknown_and_active_rollback_targets(self):
        e, reg = active("1")
        self.assertEqual(reg.rollback("9", 1, True)["refusal"], "UNKNOWN_VERSION")
        self.assertEqual(reg.rollback("1", 2, True)["refusal"], "ALREADY_ACTIVE")

    def test_invalid_update_keeps_the_active_version(self):
        e, reg = active("1")
        bad = cfg("2")
        bad["joints"][0]["position_min"] = 5.0
        rec = reg.activate(bad, 1)
        self.assertEqual(rec["refusal"], "INVALID_CONFIGURATION")
        self.assertTrue(rec["detail"])
        self.assertEqual(reg.active_version, "1")

    def test_removing_a_joint_or_a_mode_with_an_open_command_is_refused(self):
        e, reg = active("1")
        r = e.submit(S.pos_cmd(), 1)
        e.execution_started(r.command_id, e.command(r.command_id)["backend_reference"], 2)
        no_mode = cfg("2", modes=["velocity"])
        self.assertEqual(reg.activate(no_mode, 3)["detail"][0]["reason"], "MODE_DROPPED")
        no_joint = cfg("3")
        del no_joint["joints"][0]
        self.assertEqual(reg.activate(no_joint, 4)["detail"][0]["reason"], "JOINT_REMOVED")
        self.assertEqual(reg.active_version, "1")

    def test_history_is_append_only_and_returns_copies(self):
        e, reg = active("1")
        reg.activate(cfg("2"), 1)
        snap = reg.history()
        snap[0]["outcome"] = "TAMPERED"
        again = reg.history()
        self.assertEqual(again[0]["outcome"], "ACTIVATED")
        self.assertEqual(len(again), 2)
        self.assertFalse(any(hasattr(reg, n) for n in ("delete", "remove", "overwrite", "clear")))


class TestEngineHook(unittest.TestCase):
    def test_install_same_version_with_a_different_digest_is_refused(self):
        e = LifecycleEngine(copy.deepcopy(S.base.CONFIG), copy.deepcopy(BACKEND), "d1")
        e.install_configuration(copy.deepcopy(S.base.CONFIG), "d1")
        with self.assertRaises(ValueError):
            e.install_configuration(copy.deepcopy(S.base.CONFIG), "d2")

    def test_engine_built_with_a_configuration_is_unchanged(self):
        e = S.engine()
        self.assertEqual(e.active_configuration_version(), "1")
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1)
        self.assertEqual(e.command(r.command_id)["config_digest"], "digest-1")


if __name__ == "__main__":
    unittest.main()
