"""Schema tests for the five Motion contract schemas (AC-205, conformance group CT-SCH-01..09).

Each case is a document, the schema it is checked against and whether it must validate. Every
schema is first checked as a valid Draft 2020-12 schema. The documents are examples for software
conformance only: passing them is never physical or safety validation. The tests are
deterministic: no clock, no randomness, no network. A missing `jsonschema` fails the run
(an ImportError); it never skips.

Run:  python3 -m unittest discover -s tests/schema -v
"""
import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
NAMES = {
    "command": "motion-command.schema.json",
    "status": "motion-command-status.schema.json",
    "event": "motion-event.schema.json",
    "joint": "motion-joint-state.schema.json",
    "result": "motion-submission-result.schema.json",
}
SCHEMAS = {k: json.loads((CONTRACT / v).read_text(encoding="utf-8")) for k, v in NAMES.items()}
ALL_CT_SCH = {f"CT-SCH-{i:02d}" for i in range(1, 10)}

DIGEST = "sha256:" + "a" * 64
TS = "2026-11-05T10:00:00Z"
TARGET = {"type": "joint", "id": "joint-1"}


def command(kind, **over):
    base = {"contract_version": "0.1.0", "client_request_id": "req-1", "command_type": kind}
    params = {
        "SET_POSITION": {"target_position": 0.5, "unit": "rad"},
        "SET_VELOCITY": {"target_velocity": 0.1, "unit": "rad/s"},
        "STOP": {},
        "HOLD": {},
        "CANCEL": {"command_id": "cmd-1"},
        "CLEAR_FAULT": {"fault_id": "fault-1"},
    }[kind]
    base["parameters"] = params
    if kind != "CANCEL":
        base["target"] = dict(TARGET)
    base.update(over)
    return base


def status(**over):
    d = {"command_id": "cmd-1", "operation": "SET_POSITION", "state": "RUNNING", "phase": "NONE",
         "config_version": "1", "config_digest": DIGEST, "last_sequence_number": 3}
    d.update(over)
    return d


def joint(**over):
    d = {"joint_id": "joint-1", "control_state": "IDLE", "health_state": "READY",
         "feedback_status": "VALID", "is_current": True, "backend_status": "AVAILABLE", "config_version": "1"}
    d.update(over)
    return d


def event(**over):
    d = {"event_id": "ev-1", "stream": {"kind": "command", "id": "cmd-1"}, "sequence_number": 1,
         "occurred_at": TS, "event_type": "COMMAND_STATE_CHANGED"}
    d.update(over)
    return d


def accepted(**over):
    d = {"result": "ACCEPTED", "command_id": "cmd-1", "config_version": "1", "config_digest": DIGEST,
         "accepted_at": TS, "idempotent_replay": False}
    d.update(over)
    return d


def rejected(**over):
    d = {"result": "REJECTED", "idempotent_replay": False, "error": {"code": "INVALID_SCHEMA", "message": "m"}}
    d.update(over)
    return d


def without(doc, *keys):
    d = copy.deepcopy(doc)
    for k in keys:
        d.pop(k, None)
    return d


def terminating(outcome):
    return {"causes": ["STOP_REQUESTED"], "requested_at": TS, "confirm_bound_ms": 500, "outcome": outcome}


# (case id, conformance IDs, schema key, document, must validate)
CASES = [
    ("cmd-set-position", ["CT-SCH-01"], "command", command("SET_POSITION"), True),
    ("cmd-set-velocity", ["CT-SCH-01"], "command", command("SET_VELOCITY"), True),
    ("cmd-stop", ["CT-SCH-01"], "command", command("STOP"), True),
    ("cmd-hold", ["CT-SCH-01"], "command", command("HOLD"), True),
    ("cmd-cancel", ["CT-SCH-01"], "command", command("CANCEL"), True),
    ("cmd-clear-fault", ["CT-SCH-01", "CT-SCH-09"], "command", command("CLEAR_FAULT"), True),
    ("cmd-missing-unit", ["CT-SCH-02"], "command", command("SET_POSITION", parameters={"target_position": 0.5}), False),
    ("cmd-unknown-type", ["CT-SCH-02"], "command", command("STOP", command_type="JUMP"), False),
    ("cmd-unknown-target-type", ["CT-SCH-02"], "command", command("STOP", target={"type": "wheel", "id": "w"}), False),
    ("cmd-extra-field", ["CT-SCH-02"], "command", command("STOP", surprise=1), False),
    ("cmd-cancel-with-target", ["CT-SCH-03", "CT-SCH-09"], "command", command("CANCEL", target=dict(TARGET)), False),
    ("cmd-stop-with-parameters", ["CT-SCH-03"], "command", command("STOP", parameters={"x": 1}), False),
    ("cmd-clear-fault-no-target", ["CT-SCH-09"], "command", without(command("CLEAR_FAULT"), "target"), False),
    ("cmd-clear-fault-no-fault-id", ["CT-SCH-09"], "command", command("CLEAR_FAULT", parameters={}), False),
    ("status-valid-running", ["CT-SCH-04"], "status", status(), True),
    ("status-valid-completed", ["CT-SCH-04"], "status",
     status(state="COMPLETED", reason_code="REACHED", completed_at=TS), True),
    ("status-terminal-with-phase", ["CT-SCH-04"], "status",
     status(state="COMPLETED", reason_code="REACHED", completed_at=TS, phase="TERMINATING",
            termination=terminating("PENDING")), False),
    ("status-timed-out-not-a-state", ["CT-SCH-04"], "status", status(state="TIMED_OUT"), False),
    ("status-six-states-refused", ["CT-SCH-04"], "status", status(state="PAUSED"), False),
    ("status-dispatch-pending-accepted", ["CT-SCH-08"], "status", status(state="ACCEPTED", phase="DISPATCH_PENDING"), True),
    ("status-dispatch-pending-running", ["CT-SCH-08"], "status", status(state="RUNNING", phase="DISPATCH_PENDING"), False),
    ("status-terminating-pending", ["CT-SCH-08"], "status",
     status(phase="TERMINATING", termination=terminating("PENDING")), True),
    ("status-terminating-no-record", ["CT-SCH-08"], "status", status(phase="TERMINATING"), False),
    ("status-terminating-confirmed", ["CT-SCH-08"], "status",
     status(phase="TERMINATING", termination=terminating("CONFIRMED")), False),
    ("joint-valid-idle", ["CT-SCH-05"], "joint", joint(), True),
    ("joint-valid-active", ["CT-SCH-05"], "joint", joint(control_state="ACTIVE", active_command_id="cmd-1"), True),
    ("joint-faulted-no-fault-ids", ["CT-SCH-05"], "joint", joint(health_state="FAULTED"), False),
    ("joint-faulted-with-fault-ids", ["CT-SCH-05"], "joint", joint(health_state="FAULTED", fault_ids=["f1"]), True),
    ("joint-degraded-no-reasons", ["CT-SCH-05"], "joint", joint(health_state="DEGRADED"), False),
    ("joint-degraded-with-reasons", ["CT-SCH-05"], "joint",
     joint(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"]), True),
    ("joint-active-no-command", ["CT-SCH-05"], "joint", joint(control_state="ACTIVE"), False),
    ("joint-stale-but-current", ["CT-SCH-05"], "joint", joint(feedback_status="STALE", is_current=True), False),
    ("joint-stale-not-current", ["CT-SCH-05"], "joint", joint(feedback_status="STALE", is_current=False), True),
    ("event-command-state", ["CT-SCH-06"], "event", event(), True),
    ("event-joint-fault", ["CT-SCH-06"], "event",
     event(stream={"kind": "joint", "id": "joint-1"}, event_type="JOINT_FAULT_RAISED"), True),
    ("event-backend-health", ["CT-SCH-06"], "event",
     event(stream={"kind": "backend", "id": "b1"}, event_type="BACKEND_HEALTH_CHANGED"), True),
    ("event-kind-type-mismatch", ["CT-SCH-06"], "event", event(event_type="JOINT_FAULT_RAISED"), False),
    ("event-backend-kind-command-type", ["CT-SCH-06"], "event",
     event(stream={"kind": "backend", "id": "b1"}), False),
    ("result-accepted", ["CT-SCH-07"], "result", accepted(), True),
    ("result-rejected", ["CT-SCH-07"], "result", rejected(), True),
    ("result-accepted-no-command-id", ["CT-SCH-07"], "result", without(accepted(), "command_id"), False),
    ("result-rejected-with-command-id", ["CT-SCH-07"], "result", rejected(command_id="cmd-1"), False),
]


def validator(key):
    return Draft202012Validator(SCHEMAS[key])


class TestSchemasAreValid(unittest.TestCase):
    def test_every_schema_is_a_valid_draft_2020_12_schema(self):
        for key, schema in SCHEMAS.items():
            with self.subTest(schema=key):
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                Draft202012Validator.check_schema(schema)

    def test_all_references_are_local(self):
        def refs(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "$ref":
                        yield v
                    else:
                        yield from refs(v)
            elif isinstance(node, list):
                for v in node:
                    yield from refs(v)
        for key, schema in SCHEMAS.items():
            for r in refs(schema):
                with self.subTest(schema=key, ref=r):
                    self.assertTrue(r.startswith("#/"), "non-local schema reference")


class TestCases(unittest.TestCase):
    def test_cases(self):
        for case_id, ids, key, doc, ok in CASES:
            with self.subTest(case=case_id):
                errors = list(validator(key).iter_errors(doc))
                if ok:
                    self.assertEqual(errors, [], [e.message for e in errors])
                else:
                    self.assertTrue(errors, "the document was expected to be refused")

    def test_case_ids_are_unique(self):
        ids = [c[0] for c in CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_schema_has_a_positive_and_a_negative_case(self):
        for key in SCHEMAS:
            with self.subTest(schema=key):
                self.assertIn(True, [c[4] for c in CASES if c[2] == key])
                self.assertIn(False, [c[4] for c in CASES if c[2] == key])

    def test_every_ct_sch_id_has_an_executable_case(self):
        covered = {i for c in CASES for i in c[1]}
        self.assertEqual(covered, ALL_CT_SCH)
        for ct in sorted(ALL_CT_SCH):
            with self.subTest(ct=ct):
                self.assertTrue([c for c in CASES if ct in c[1]])

    def test_each_ct_sch_id_has_a_refusal_unless_it_is_positive_only(self):
        # CT-SCH-01 is the only positive-only conformance ID (valid envelopes validate).
        for ct in sorted(ALL_CT_SCH - {"CT-SCH-01"}):
            with self.subTest(ct=ct):
                self.assertIn(False, [c[4] for c in CASES if ct in c[1]])


class TestEvidenceReport(unittest.TestCase):
    def test_report_counts_are_separate(self):
        docs = len(CASES)
        schemas = len(SCHEMAS)
        ids = len({i for c in CASES for i in c[1]})
        line = f"schema evidence: example documents={docs} schemas={schemas} conformance ids covered={ids}/{len(ALL_CT_SCH)}"
        print("\n" + line)
        self.assertEqual((schemas, ids), (5, 9))


if __name__ == "__main__":
    unittest.main()
