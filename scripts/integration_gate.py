#!/usr/bin/env python3
"""Integration-test gate (KOS-MOTION-004 PR-05, AC-406).

Runs the scenario tests of tests/integration, which drive the real driver, stores, lifecycle engine and a backend
(the scripted S1 simulator and a second, different backend) with no mock of this repository's own code. Exits 0
only when at least one test was found, every test passed and none was skipped; otherwise 1. It prints one
evidence line. A pass is software evidence only: simulated backends say nothing about an actuator, a transport
or firmware (contract 17.7). Standard library only (the tests use the pinned test dependencies); offline; it does
not read the clock.
"""
import argparse
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gate import Recorder, missing_test_dependency  # noqa: E402

TEST_DIR = "tests/integration"
MANIFEST = "tests/manifest/conformance_manifest.json"


def run(root, test_dir=TEST_DIR, manifest=MANIFEST, out=sys.stdout, label="integration"):
    root = Path(root).resolve()
    d = root / test_dir
    if not d.is_dir():
        print(f"{label} gate: {test_dir} does not exist", file=out)
        return 1
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    suite = unittest.TestLoader().discover(str(d), top_level_dir=str(d))
    result = unittest.TextTestRunner(stream=out, verbosity=1, resultclass=Recorder).run(suite)
    problems = []
    if result.testsRun == 0:
        problems.append(f"no {label} test was discovered")
    if result.skipped_ids:
        problems.append(f"{len(result.skipped_ids)} test(s) were skipped; the gate allows no skips")
    if not result.wasSuccessful() or result.bad:
        problems.append("tests failed")
    ids = []
    mp = root / manifest
    if mp.is_file():
        modules = {i.split(".")[0] for i in result.ran}
        for e in json.loads(mp.read_text(encoding="utf-8")).get("entries", []):
            t = e.get("test") if isinstance(e, dict) else None
            if e.get("status") == "IN_SCOPE" and isinstance(t, str) and t.split(".")[0] in modules:
                if t in result.ran and t not in result.bad:
                    ids.append(e["id"])
                else:
                    problems.append(f"{e['id']}: its {label} test {t} did not run and pass")
    print(f"{label} evidence: tests_run={result.testsRun} conformance_ids_evidenced={sorted(ids)}", file=out)
    for p in problems:
        print(f"{label.upper()} GATE FAIL: {p}", file=out)
    print(f"{label} gate: FAIL" if problems else f"{label} gate: ok", file=out)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--test-dir", default=TEST_DIR)
    a = ap.parse_args(argv)
    hint = missing_test_dependency()
    if hint:
        print(f"INTEGRATION GATE FAIL: {hint}")
        print("integration gate: FAIL")
        return 1
    return run(a.root, a.test_dir)


if __name__ == "__main__":
    sys.exit(main())
