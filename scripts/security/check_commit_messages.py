#!/usr/bin/env python3
"""Reject commit messages that carry AI-session metadata.

Security control from kritva-program decision D-032 (follow-up).

Forbidden in any commit message: a 'Claude-Session:' trailer and any claude.ai/code/session link.
Modes:
  --range BASE..HEAD   check every commit in the range (used by CI on pull requests)
  --file PATH          check one message file (used by the commit-msg hook)
Existing history is not checked or rewritten; this only guards new commits.
Exit code 1 when a forbidden pattern is found, 2 on usage or git errors.
"""

import argparse
import re
import subprocess
import sys

FORBIDDEN = (
    (re.compile(r"^\s*claude-session\s*:", re.IGNORECASE | re.MULTILINE), "Claude-Session trailer"),
    (re.compile(r"claude\.ai/code/session", re.IGNORECASE), "claude.ai session link"),
)


def problems(message):
    return [name for rx, name in FORBIDDEN if rx.search(message)]


def commits_in_range(rev_range):
    out = subprocess.run(["git", "log", "--format=%H%x00%B%x01", rev_range],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "git log failed")
    for chunk in out.stdout.split("\x01"):
        chunk = chunk.strip("\n")
        if chunk:
            sha, _, body = chunk.partition("\x00")
            yield sha.strip(), body


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--range")
    g.add_argument("--file")
    a = ap.parse_args(argv)
    bad = []
    try:
        if a.file:
            with open(a.file, encoding="utf-8") as fh:
                found = problems(fh.read())
            if found:
                bad.append(("commit message", found))
        else:
            for sha, body in commits_in_range(a.range):
                found = problems(body)
                if found:
                    bad.append((sha[:12], found))
    except (OSError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    for who, found in bad:
        print(f"REJECTED {who}: {', '.join(found)}", file=sys.stderr)
    if bad:
        print("Remove the session trailer or link from the commit message and amend the commit.", file=sys.stderr)
        return 1
    print("commit messages ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
