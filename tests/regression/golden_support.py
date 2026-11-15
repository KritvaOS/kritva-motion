"""Canonical rendering of the golden traces (KOS-MOTION-004 PR-06). One function renders a scenario, and both the
regression test and `scripts/regression_update.py` use it, so a golden file is exactly what the test compares.

A golden trace is canonical JSON (sorted keys, two-space indent, ASCII, one trailing newline) of what the integration
scenario produced on the scripted S1 simulator: the public output (events with sequence numbers, command records,
status, history, joint snapshots, faults, admission answers) and the boundary trace of the driver (what crossed to
and from the backend). Software evidence only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "integration"))
import integration_support as I  # noqa: E402

GOLDEN = ROOT / "tests" / "regression" / "golden"


def render(name, scenarios=None):
    sc = (scenarios or I.scenarios())[name]
    public, driver, _ = I.run_scenario("simulator", sc)
    doc = {"scenario": name, "public": public, "boundary_trace": driver.trace}
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def names():
    return sorted(I.scenarios())
