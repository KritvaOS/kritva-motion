#!/usr/bin/env python3
"""Check the V2 commit format (D-044, aligned with the raas rules in D-053): Conventional Commits header plus one Task footer.

  header   type(scope): summary [TASK-ID]
           type in feat fix docs refactor test build ci chore perf revert security; summary up to 90 chars;
           the trailing [TASK-ID] is optional, and if present it must be one of the footer IDs
  footer   Task: <TASK-ID>  or  Tasks: <ID>, <ID>   exactly one footer line; IDs are upper-case segments joined by hyphens
           Tasks: None (reason)   for a docs or chore commit that implements no task (record corrections)
  rejects  missing, malformed or duplicated Task/Tasks lines, AI session trailers (Claude-Session, session links)
  allows   ordinary Git metadata, Acceptance/Tests/Security-Gates/Evidence trailers, Co-Authored-By and Signed-off-by,
           and merge commits ("Merge ...")

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

TYPES = "feat|fix|docs|refactor|test|build|ci|chore|perf|revert|security"
ID = r"[A-Z0-9]+(?:-[A-Z0-9]+)+"
HEADER = re.compile(rf"^({TYPES})(\([a-z0-9][a-z0-9._/-]*\))?: \S.{{0,89}}$")
SUFFIX = re.compile(rf"\s\[({ID})\]$")
FOOTER = re.compile(rf"^Tasks?: ({ID}(?:, ?{ID})*)$")
NONE = re.compile(r"^Tasks?: None \(\S.*\)$")
TASKISH = re.compile(r"^\s*tasks?\s*:", re.IGNORECASE)
TASK = FOOTER  # kept for callers that match a single footer line
NONE_TYPES = ("docs", "chore")
SESSION = (re.compile(r"^\s*claude-session\s*:", re.IGNORECASE | re.MULTILINE), re.compile(r"claude\.ai/code/session", re.IGNORECASE))


def _footer_lines(message):
    return [ln for ln in message.rstrip("\n").split("\n")[1:] if TASKISH.match(ln)]


def task_ids(message):
    """Task IDs named by the footer (empty for a None footer or no footer)."""
    for ln in _footer_lines(message):
        m = FOOTER.match(ln)
        if m:
            return [x.strip() for x in m.group(1).split(",")]
    return []


def declares_none(message):
    return any(NONE.match(ln) for ln in _footer_lines(message))


def problems(message, registry=None):
    lines = message.rstrip("\n").split("\n")
    if lines and lines[0].startswith("Merge "):
        return []
    out = []
    head = lines[0] if lines else ""
    sfx = SUFFIX.search(head)
    core = head[:sfx.start()] if sfx else head
    if not HEADER.match(core):
        out.append("header must be type(scope): summary [optional TASK-ID] (types: feat fix docs refactor test build ci chore perf revert security; summary at most 90 characters)")
    footers = _footer_lines(message)
    bad = [ln for ln in footers if not FOOTER.match(ln) and not NONE.match(ln)]
    if bad:
        out.append(f"malformed Task footer: {bad[0]!r}")
    if not footers:
        out.append("missing Task: footer (use 'Tasks: None (reason)' on a docs or chore commit that implements no task)")
    if len(footers) > 1:
        out.append("more than one Task: footer")
    ids = task_ids(message)
    if declares_none(message):
        mt = re.match(r"^([a-z]+)", core)
        if not mt or mt.group(1) not in NONE_TYPES:
            out.append("'Tasks: None' is only for docs or chore commits")
        if sfx:
            out.append("a subject [TASK-ID] cannot go with 'Tasks: None'")
    if sfx and ids and sfx.group(1) not in ids:
        out.append(f"subject task {sfx.group(1)} is not in the footer")
    if registry is not None:
        for t in ids:
            if t not in registry:
                out.append(f"unknown task ID {t}")
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
