#!/usr/bin/env python3
"""Check the V2 commit format (D-044, proposed): Conventional Commits header plus exactly one Task footer.

  header   type(scope): summary      type in feat fix docs refactor test build ci chore perf revert; summary up to 72 chars
  footer   Task: <TASK-ID>           exactly one, e.g. Task: KOS-SENSE-001 ; ID is upper-case segments joined by hyphens
  rejects  missing, malformed or duplicated Task lines, AI session trailers (Claude-Session, session links)
  allows   ordinary Git metadata, Co-Authored-By and Signed-off-by trailers, and merge commits ("Merge ...")

  --range BASE..HEAD   every non-merge commit in the range
  --file PATH          one message file (commit-msg hook)
  --registry PATH      optional file with one known task ID per line (or a JSON list); unknown IDs are rejected
Enforce only after dry runs (ChatGPT advice 2026-10-18); existing history is never checked or rewritten.
Exit 1 on problems, 2 on usage or git errors.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HEADER = re.compile(r"^(feat|fix|docs|refactor|test|build|ci|chore|perf|revert)(\([a-z0-9][a-z0-9._/-]*\))?: \S.{0,71}$")
TASK = re.compile(r"^Task: [A-Z0-9]+(?:-[A-Z0-9]+)+$")
TASKISH = re.compile(r"^\s*task\s*:", re.IGNORECASE)
SESSION = (re.compile(r"^\s*claude-session\s*:", re.IGNORECASE | re.MULTILINE), re.compile(r"claude\.ai/code/session", re.IGNORECASE))


def problems(message, registry=None):
    lines = message.rstrip("\n").split("\n")
    if lines and lines[0].startswith("Merge "):
        return []
    out = []
    if not HEADER.match(lines[0] if lines else ""):
        out.append("header must be type(scope): summary (types: feat fix docs refactor test build ci chore perf revert; summary at most 72 characters)")
    taskish = [ln for ln in lines[1:] if TASKISH.match(ln)]
    good = [ln for ln in taskish if TASK.match(ln)]
    bad = [ln for ln in taskish if not TASK.match(ln)]
    if bad:
        out.append(f"malformed Task footer: {bad[0]!r}")
    if not taskish:
        out.append("missing Task: footer")
    if len(good) > 1:
        out.append("more than one Task: footer")
    if registry is not None:
        for ln in good:
            if ln.split(": ", 1)[1] not in registry:
                out.append(f"unknown task ID {ln.split(': ', 1)[1]}")
    if any(rx.search(message) for rx in SESSION):
        out.append("AI session trailer or link")
    return out


def load_registry(path):
    t = Path(path).read_text(encoding="utf-8")
    try:
        v = json.loads(t)
        return set(v) if isinstance(v, list) else set()
    except ValueError:
        return {ln.strip() for ln in t.splitlines() if ln.strip() and not ln.startswith("#")}


def commits(rev_range):
    r = subprocess.run(["git", "log", "--no-merges", "--format=%H%x00%B%x01", rev_range], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr, file=sys.stderr)
        sys.exit(2)
    return [tuple(c.lstrip("\n").split("\x00", 1)) for c in r.stdout.split("\x01") if c.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--range")
    g.add_argument("--file")
    ap.add_argument("--registry")
    a = ap.parse_args(argv)
    reg = load_registry(a.registry) if a.registry else None
    bad = 0
    items = [("message", Path(a.file).read_text(encoding="utf-8"))] if a.file else [(h[:10], m) for h, m in commits(a.range)]
    for name, msg in items:
        for p in problems(msg, reg):
            print(f"{name}: {p}", file=sys.stderr)
            bad += 1
    if bad:
        return 1
    print(f"commit format ok ({len(items)} message(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
