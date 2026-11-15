#!/usr/bin/env python3
"""Rewrite the golden traces of the regression gate (KOS-MOTION-004 PR-06). The only command that changes them.

Runs every integration scenario on the scripted S1 simulator and writes tests/regression/golden/<scenario>.json in
canonical JSON, removing files of scenarios that no longer exist. Review the diff in the pull request: a golden
trace that changes is a change of public behaviour. Standard library only; offline; deterministic."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def update(root=ROOT, out=sys.stdout):
    sys.path.insert(0, str(Path(root) / "tests" / "regression"))
    import golden_support as G
    golden = Path(root) / "tests" / "regression" / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    written, names = [], G.names()
    for name in names:
        text = G.render(name)
        p = golden / f"{name}.json"
        if not p.is_file() or p.read_text(encoding="ascii") != text:
            p.write_text(text, encoding="ascii", newline="\n")
            written.append(name)
    removed = [p.stem for p in golden.glob("*.json") if p.stem not in names]
    for stem in removed:
        (golden / f"{stem}.json").unlink()
    print(f"regression_update: {len(names)} scenarios, written or changed: {written or 'none'}, removed: {removed or 'none'}", file=out)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)
    return update()


if __name__ == "__main__":
    sys.exit(main())
