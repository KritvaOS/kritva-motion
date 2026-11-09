#!/usr/bin/env python3
"""Print the transition matrix of the lifecycle engine from the code, and check it against the tables of
tasks/KOS-MOTION-003/LIFECYCLE.md (KOS-MOTION-003).

  lifecycle_matrix.py            print the matrix (Markdown), from src/kritva_motion/lifecycle/model.py
  lifecycle_matrix.py --check    compare it with LIFECYCLE.md; exit 1 on a missing, extra or duplicated row

Three tables: T (command states, contract 7.5), C (joint control state, 13.3) and H (joint health, 13.3). A row
is (label, from, to). The comparison is by row, not by count, so one transition replaced by another fails.
Standard library only; reads two files and writes nothing.
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "tasks" / "KOS-MOTION-003" / "LIFECYCLE.md"
sys.path.insert(0, str(ROOT / "src"))
from kritva_motion.lifecycle import model  # noqa: E402

ADMISSION = "(admission)"


def generated():
    """The rows of the three tables as the code defines them: {"T": [...], "C": [...], "H": [...]}."""
    t = sorted(((label, ADMISSION if f is None else f, to) for (f, to), label in model.TRANSITIONS.items()),
               key=lambda r: int(r[0][1:]))
    c = [(f"C{i}", f, to) for i, (f, to) in enumerate(model.CONTROL_TRANSITIONS, 1)]
    h = [(f"H{i}", f, to) for i, (f, to) in enumerate(model.HEALTH_TRANSITIONS, 1)]
    return {"T": t, "C": c, "H": h}


def triggers():
    return {"C": list(model.CONTROL_TRANSITIONS.values()), "H": list(model.HEALTH_TRANSITIONS.values())}


def render():
    g, trig = generated(), triggers()
    out = ["| # | From | To |", "|---|---|---|"]
    out += [f"| {a} | {'`'+b+'`' if b != ADMISSION else b} | `{c}` |" for a, b, c in g["T"]]
    for key, name in (("C", "control"), ("H", "health")):
        out += ["", f"| # | From ({name}) | To ({name}) | Trigger (13.3) |", "|---|---|---|---|"]
        out += [f"| {a} | `{b}` | `{c}` | {t} |" for (a, b, c), t in zip(g[key], trig[key])]
    return "\n".join(out)


_ROW = re.compile(r"^\| ([TCH]\d+) \| ([^|]*) \| ([^|]*) \|")


def _cell(text):
    m = re.search(r"`([^`]+)`", text)
    return m.group(1) if m else text.strip()


def documented(text):
    """Every row of the three tables as written in LIFECYCLE.md, in document order (duplicates kept)."""
    out = {"T": [], "C": [], "H": []}
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            out[m.group(1)[0]].append((m.group(1), _cell(m.group(2)), _cell(m.group(3))))
    return out


def compare(gen, doc):
    """Problems found, as readable strings: [] means the document and the code agree row for row."""
    problems = []
    for key in "TCH":
        g, d = Counter(gen[key]), Counter(doc[key])
        problems += [f"{key}: in the code but not in LIFECYCLE.md: {r}" for r in sorted((g - d).elements())]
        problems += [f"{key}: in LIFECYCLE.md but not in the code: {r}" for r in sorted((d - g).elements())]
        problems += [f"{key}: duplicated in LIFECYCLE.md: {r}" for r, n in sorted(d.items()) if n > 1]
    return problems


def main(argv):
    if "--check" in argv:
        problems = compare(generated(), documented(DOC.read_text(encoding="utf-8")))
        for p in problems:
            print(p)
        print(f"lifecycle_matrix: {'FAIL' if problems else 'PASS'} ({len(problems)} problem(s))")
        return 1 if problems else 0
    print(render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
