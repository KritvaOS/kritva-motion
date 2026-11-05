"""The standard-library envelope check must agree with the JSON schema (AC-202, AC-205).

`kritva_motion.admission.schema_problem` is a hand-written mirror of contract/motion-command.schema.json
(the reference validator is standard library only, D-100). This test runs both on a fixed corpus of
documents built by systematic mutation (no randomness) and requires the same verdict. A NaN or an
infinity in a number slot is valid for the schema and is refused later, as NON_FINITE_VALUE, so the
corpus compares verdicts with that class set aside. Needs the test-only `jsonschema` dependency; a
missing dependency fails the run.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kritva_motion import admission as ad  # noqa: E402

SCHEMA = json.loads((ROOT / "contract" / "motion-command.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
TARGET = {"type": "joint", "id": "joint-1"}


def base(kind, **over):
    params = {"SET_POSITION": {"target_position": 0.5, "unit": "rad"},
              "SET_VELOCITY": {"target_velocity": 0.1, "unit": "rad/s", "duration_ms": 100},
              "STOP": {}, "HOLD": {}, "CANCEL": {"command_id": "cmd-1"}, "CLEAR_FAULT": {"fault_id": "f-1"},
              "EXECUTE_TRAJECTORY": {}}[kind]
    d = {"contract_version": "0.1.0", "client_request_id": "req-1", "command_type": kind, "parameters": params,
         "identity_assertion": {"x": 1}, "constraints": {"max_velocity": 1.0, "max_acceleration": 2.0, "position_min": -1.0,
                                                         "position_max": 1.0, "unit_system": "SI"},
         "priority": 0, "deadline_ms": 1000, "execution_timeout_ms": 2000, "issued_at": "2026-11-05T10:00:00Z"}
    if kind != "CANCEL":
        d["target"] = dict(TARGET)
    d.update(over)
    return d


ALIENS = [None, True, False, "x", "", "a\nb", "abc\n", 0, -1, 1, 1.0, 1.5, 10 ** 12, [], {}, [1], {"a": 1},
          "rad", "m", "rad/s", "SI", "joint", "robot", "1.0.0", "0.1", "STOP", "CANCEL"]
KINDS = ("SET_POSITION", "SET_VELOCITY", "STOP", "HOLD", "CANCEL", "CLEAR_FAULT", "EXECUTE_TRAJECTORY")


def paths(node, prefix=()):
    if isinstance(node, dict):
        for k in sorted(node):
            yield prefix + (k,)
            yield from paths(node[k], prefix + (k,))


def get(doc, path):
    for k in path:
        doc = doc[k]
    return doc


def corpus():
    for kind in KINDS:
        b = base(kind)
        yield f"{kind}:base", b
        for p in paths(b):
            d = copy.deepcopy(b)
            parent = get(d, p[:-1])
            del parent[p[-1]]
            yield f"{kind}:delete:{'.'.join(p)}", d
            for i, a in enumerate(ALIENS):
                d = copy.deepcopy(b)
                get(d, p[:-1])[p[-1]] = copy.deepcopy(a)
                yield f"{kind}:set:{'.'.join(p)}:{i}", d
            d = copy.deepcopy(b)
            tgt = get(d, p[:-1]) if len(p) > 1 else d
            if isinstance(tgt, dict):
                tgt["surprise"] = 1
                yield f"{kind}:extra-in:{'.'.join(p[:-1])}", d
        for other in KINDS:
            d = copy.deepcopy(b)
            d["command_type"] = other
            yield f"{kind}:as:{other}", d


class TestMirror(unittest.TestCase):
    def test_verdicts_agree_on_the_corpus(self):
        n = 0
        for name, doc in corpus():
            n += 1
            want = VALIDATOR.is_valid(doc)
            got = ad.schema_problem(doc) is None
            if want != got:
                errs = [e.message for e in VALIDATOR.iter_errors(doc)][:2]
                self.fail(f"{name}: schema valid={want}, mirror valid={got} {ad.schema_problem(doc)} {errs}")
        self.assertGreater(n, 2500)
        print(f"\nenvelope mirror: {n} documents compared with the schema")

    def test_non_object_envelopes(self):
        for doc in (None, [], "x", 1, True):
            self.assertFalse(VALIDATOR.is_valid(doc))
            self.assertIsNotNone(ad.schema_problem(doc))

    def test_non_finite_numbers_are_not_schema_errors(self):
        for kind, path in (("SET_POSITION", ("parameters", "target_position")), ("SET_VELOCITY", ("parameters", "target_velocity")),
                           ("STOP", ("deadline_ms",)), ("STOP", ("constraints", "max_velocity"))):
            for v in (float("nan"), float("inf"), float("-inf")):
                d = base(kind)
                get(d, path[:-1])[path[-1]] = v
                self.assertIsNone(ad.schema_problem(d), (kind, path, v))


if __name__ == "__main__":
    unittest.main()
