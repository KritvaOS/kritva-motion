#!/usr/bin/env python3
"""Regression gate (KOS-MOTION-004 PR-06, AC-406).

Runs the golden-trace comparison of tests/regression: every committed trace under tests/regression/golden/ must
equal, byte for byte, what the scenarios produce now. Exits 0 only when at least one test ran, all passed and none
was skipped; otherwise 1. A trace changes only through `python3 scripts/regression_update.py`, reviewed in the
pull request. Software evidence only: simulated backends say nothing about an actuator (contract 17.7).
Standard library only; offline; it does not read the clock."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from integration_gate import run  # noqa: E402
from test_gate import missing_test_dependency  # noqa: E402

TEST_DIR = "tests/regression"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--test-dir", default=TEST_DIR)
    a = ap.parse_args(argv)
    hint = missing_test_dependency()
    if hint:
        print(f"REGRESSION GATE FAIL: {hint}")
        print("regression gate: FAIL")
        return 1
    return run(a.root, a.test_dir, label="regression")


if __name__ == "__main__":
    sys.exit(main())
