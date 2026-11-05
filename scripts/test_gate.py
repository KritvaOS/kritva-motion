#!/usr/bin/env python3
"""Unit-test gate with a conformance manifest check (KOS-MOTION-002, AC-206).

Runs the unit tests of the listed directories and checks tests/manifest/conformance_manifest.json
against contract/CONFORMANCE_TEST_PLAN.md. The gate fails (exit 1) when

- no test is discovered, or any test fails, errors or is skipped;
- the manifest IDs differ from the plan IDs (missing, extra or duplicate), a status is unknown, or
  contract_sections differ from the plan row;
- an IN_SCOPE entry does not name exactly one test that was discovered, ran and passed, or two
  entries name the same test;
- a DEFERRED or OUT_OF_SCOPE entry has no reason or names a test.

It prints one evidence line with the counts per status. DEFERRED is never reported as implemented
or passed. A pass is software evidence only, never physical or safety validation.
Standard library only; offline; it does not read the clock.
"""
import argparse
import json
import re
import sys
import unittest
from pathlib import Path

UNIT_TEST_DIRS = ["tests/schema", "tests/validator", "tests/gate", "tests/status_gen"]
MANIFEST = "tests/manifest/conformance_manifest.json"
PLAN = "contract/CONFORMANCE_TEST_PLAN.md"
STATUSES = ("IN_SCOPE", "DEFERRED", "OUT_OF_SCOPE")
ROW = re.compile(r"^\| (CT-[A-Z]+-\d+) \|(.*)$")


class Recorder(unittest.TextTestResult):
    """Records one outcome per test id; a failed subtest fails its test."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ran, self.bad, self.skipped_ids = [], set(), set()

    def startTest(self, test):
        super().startTest(test)
        self.ran.append(test.id())

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.bad.add(test.id())

    def addError(self, test, err):
        super().addError(test, err)
        self.bad.add(test.id())

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.skipped_ids.add(test.id())

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.bad.add(test.id())  # an expected failure is not a pass

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.bad.add(test.id())

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.bad.add(test.id())


def plan_rows(path):
    rows = {}
    dups = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        ident = cells[0]
        if ident in rows:
            dups.append(ident)
        rows[ident] = cells[2] if len(cells) > 2 else ""
    return rows, dups


def check_manifest(manifest, plan, passed, discovered):
    """Return (problems, counts). passed and discovered are sets of test ids."""
    problems = []
    rows, plan_dups = plan_rows(plan)
    problems += [f"plan lists {i} more than once" for i in plan_dups]
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        return ["manifest has no entries list"], {}
    entries = manifest["entries"]
    ids = [e.get("id") if isinstance(e, dict) else None for e in entries]
    for i in sorted({x for x in ids if ids.count(x) > 1}, key=str):
        problems.append(f"manifest lists {i} more than once")
    problems += [f"manifest is missing {i}" for i in sorted(set(rows) - set(ids))]
    problems += [f"manifest has {i} which is not in the plan" for i in sorted(set(ids) - set(rows), key=str)]
    used = {}
    counts = {s: 0 for s in STATUSES}
    for e in entries:
        if not isinstance(e, dict):
            problems.append("manifest entry is not an object")
            continue
        i, status = e.get("id"), e.get("status")
        if status not in STATUSES:
            problems.append(f"{i}: unknown status {status!r}")
            continue
        counts[status] += 1
        if i in rows and e.get("contract_sections") != rows[i]:
            problems.append(f"{i}: contract_sections {e.get('contract_sections')!r} differs from the plan {rows[i]!r}")
        if status == "IN_SCOPE":
            t = e.get("test")
            if not isinstance(t, str) or not t:
                problems.append(f"{i}: IN_SCOPE needs exactly one test id (a string)")
                continue
            if "reason" in e and not e["reason"]:
                problems.append(f"{i}: empty reason")
            if t in used:
                problems.append(f"{i}: test {t} is also mapped to {used[t]}")
            used[t] = i
            if t not in discovered:
                problems.append(f"{i}: test {t} was not discovered")
            elif t not in passed:
                problems.append(f"{i}: test {t} did not pass")
        else:
            if "test" in e:
                problems.append(f"{i}: {status} must not name a test")
            if not isinstance(e.get("reason"), str) or not e["reason"].strip():
                problems.append(f"{i}: {status} needs a reason")
    return problems, counts


def evidence_line(counts, unit_total):
    return (f"conformance evidence: ids={sum(counts.values())} in_scope_passed={counts.get('IN_SCOPE', 0)} "
            f"deferred={counts.get('DEFERRED', 0)} out_of_scope={counts.get('OUT_OF_SCOPE', 0)} "
            f"unit_tests_run={unit_total}")


def group_counts(manifest):
    out = {}
    for e in manifest.get("entries", []):
        if isinstance(e, dict) and e.get("status") == "IN_SCOPE" and isinstance(e.get("id"), str):
            g = e["id"].split("-")[1]
            out[g] = out.get(g, 0) + 1
    return out


def run(root, test_dirs, manifest_path, plan_path, out=sys.stdout):
    root = Path(root).resolve()
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for d in test_dirs:
        p = (root / d)
        if not p.is_dir():
            print(f"gate: test directory {d} does not exist", file=out)
            return 1
        added = str(p)
        if added not in sys.path:
            sys.path.insert(0, added)
        suite.addTests(loader.discover(added, top_level_dir=added))
    runner = unittest.TextTestRunner(stream=out, verbosity=1, resultclass=Recorder)
    result = runner.run(suite)
    problems = []
    if result.testsRun == 0:
        problems.append("no tests were discovered")
    ids = result.ran
    if len(ids) != len(set(ids)):
        problems.append("a test id was discovered more than once (module name clash between test directories)")
    if result.skipped_ids:
        problems.append(f"{len(result.skipped_ids)} test(s) were skipped; the gate allows no skips")
    if not result.wasSuccessful() or result.bad:
        problems.append("tests failed")
    mp, pp = root / manifest_path, root / plan_path
    counts, manifest = {}, {}
    if not mp.is_file():
        problems.append(f"manifest {manifest_path} does not exist")
    elif not pp.is_file():
        problems.append(f"plan {plan_path} does not exist")
    else:
        try:
            manifest = json.loads(mp.read_text(encoding="utf-8"))
        except ValueError as exc:
            problems.append(f"manifest is not valid JSON: {exc}")
        else:
            passed = set(ids) - result.bad - result.skipped_ids
            mprob, counts = check_manifest(manifest, pp, passed, set(ids))
            problems += mprob
    if counts:
        print(evidence_line(counts, result.testsRun), file=out)
        print(f"in-scope by group: {group_counts(manifest)}; deferred and out-of-scope IDs are not counted as passed", file=out)
    for p in problems:
        print(f"GATE FAIL: {p}", file=out)
    print("gate: FAIL" if problems else "gate: ok", file=out)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--test-dir", action="append", dest="test_dirs", help="relative test directory; repeatable")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--plan", default=PLAN)
    a = ap.parse_args(argv)
    return run(a.root, a.test_dirs or UNIT_TEST_DIRS, a.manifest, a.plan)


if __name__ == "__main__":
    sys.exit(main())
