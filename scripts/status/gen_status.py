#!/usr/bin/env python3
"""Generate and check status/status.json for kritva-motion (schema 2.0).

This repository reports facts only (kritva-program D-011). The program decides
baseline, weights, approvals and credit. The report never says a task is
accepted: execution comes from the status word in planning/TASKS.md, evidence
is a criteria reference (never completion proof), and git_sync is SYNCED only
when git proves it.

  gen_status.py --write            write status/status.json
  gen_status.py --print            print the report, write nothing
  gen_status.py --check            validate status/status.json against the vendored
                                   schema and compare its task facts with planning/TASKS.md

Which tasks are reported is the constant REPORTED_TASKS below. It is empty
until the approved program baseline contains the tasks (program ONBOARDING.md,
D-077, D-100); adding an ID is a reviewed change. A task listed there that is
missing from TASKS.md, a duplicate row or an unrecognised status fails closed.
Stdlib only.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

WORKSTREAM_ID = "MOTION"
REPO = "KritvaOS/kritva-motion"
REPORTED_TASKS = []  # e.g. ["KOS-MOTION-001", "KOS-MOTION-002"] once baselined by the program

# planning/TASKS.md status word -> schema execution value
EXECUTION = {
    "NOT_STARTED": "NOT_STARTED",
    "READY": "NOT_STARTED",
    "IN_PROGRESS": "IN_PROGRESS",
    "IN_REVIEW": "IN_PROGRESS",
    "CHANGES_REQUESTED": "IN_PROGRESS",
    "BLOCKED": "BLOCKED",
    "ACCEPTED": "COMPLETE",
}
ROW = re.compile(r"^\|\s*(KOS-MOTION-\d{3})\s*\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|\s*$")


class StatusError(Exception):
    pass


def parse_tasks(tasks_md: str):
    """Return {task_id: status_word}. Fail closed on duplicates and unknown words."""
    found = {}
    for line in tasks_md.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        tid = m.group(1)
        word = m.group(3).strip().split()[0].strip("(),:;") if m.group(3).strip() else ""
        if tid in found:
            raise StatusError(f"duplicate task row: {tid}")
        found[tid] = word
    return found


def task_record(tid, word):
    if word not in EXECUTION:
        raise StatusError(f"{tid}: unrecognised status {word!r} in planning/TASKS.md")
    execution = EXECUTION[word]
    return {
        "task_id": tid,
        "execution": execution,
        "git_sync": None,  # filled by build()
        "readiness": "PLANNABLE" if execution == "BLOCKED" else "IMPLEMENTABLE",
        "evidence": [{
            "type": "software",
            "uri": "ACCEPTANCE_CRITERIA.md",
            "description": f"Criteria reference only (not completion proof); planning status text: {word!r}",
            "commit": None,
            "ci_run": None,
            "report_sha256": None,
            "result": None,
        }],
    }


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise StatusError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def git_sync_value(root):
    """SYNCED only when the tree is clean and HEAD equals origin/main."""
    if git(root, "status", "--porcelain"):
        return "NOT_COMMITTED"
    try:
        remote = git(root, "rev-parse", "origin/main")
    except StatusError:
        return "NOT_SYNCED"
    return "SYNCED" if git(root, "rev-parse", "HEAD") == remote else "NOT_SYNCED"


def build(root: Path, reported=None):
    root = Path(root)
    reported = REPORTED_TASKS if reported is None else reported
    rows = parse_tasks((root / "planning" / "TASKS.md").read_text(encoding="utf-8"))
    sync = git_sync_value(root)
    tasks = []
    for tid in reported:
        if tid not in rows:
            raise StatusError(f"{tid} is reported but not in planning/TASKS.md")
        rec = task_record(tid, rows[tid])
        rec["git_sync"] = sync
        tasks.append(rec)
    branch = "main"  # the report describes the main line; the commit below is the exact source
    return {
        "schema_version": "2.0",
        "workstream_id": WORKSTREAM_ID,
        "repo": REPO,
        "source": {
            "branch": branch,
            "commit": git(root, "rev-parse", "HEAD"),
            "tag": None,
        },
        "tasks": tasks,
        "updated_at": git(root, "log", "-1", "--format=%cI"),
    }


# --- structural validation mirroring status/status.schema.json (stdlib only) ---
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _only(obj, allowed, where, problems):
    for k in obj:
        if k not in allowed:
            problems.append(f"{where}: unexpected field {k}")


def validate(doc):
    p = []
    if not isinstance(doc, dict):
        return ["report is not an object"]
    top = ["schema_version", "workstream_id", "repo", "source", "tasks", "updated_at"]
    for k in top:
        if k not in doc:
            p.append(f"missing field: {k}")
    _only(doc, top, "report", p)
    if doc.get("schema_version") != "2.0":
        p.append("schema_version must be 2.0")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(doc.get("workstream_id", ""))):
        p.append("workstream_id invalid")
    src = doc.get("source")
    if not isinstance(src, dict) or not HEX40.match(str(src.get("commit", ""))):
        p.append("source.commit must be a full 40-character SHA")
    elif set(src) - {"branch", "commit", "tag"}:
        p.append("source has unexpected fields")
    tasks = doc.get("tasks")
    if not isinstance(tasks, list):
        p.append("tasks must be a list")
        tasks = []
    ids = set()
    for i, t in enumerate(tasks):
        w = f"tasks[{i}]"
        for k in ["task_id", "execution", "git_sync", "readiness", "evidence"]:
            if k not in t:
                p.append(f"{w}: missing {k}")
        _only(t, ["task_id", "execution", "git_sync", "readiness", "evidence"], w, p)
        if t.get("task_id") in ids:
            p.append(f"{w}: duplicate task_id")
        ids.add(t.get("task_id"))
        if t.get("execution") not in ("NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMPLETE"):
            p.append(f"{w}: bad execution")
        if t.get("git_sync") not in ("NOT_COMMITTED", "COMMITTED", "NOT_SYNCED", "SYNCED"):
            p.append(f"{w}: bad git_sync")
        if t.get("readiness") not in ("PLANNABLE", "IMPLEMENTABLE", "HARDWARE-BLOCKED"):
            p.append(f"{w}: bad readiness")
        for j, e in enumerate(t.get("evidence") or []):
            ew = f"{w}.evidence[{j}]"
            if e.get("type") not in ("software", "simulation", "physical"):
                p.append(f"{ew}: bad type")
            if not e.get("uri"):
                p.append(f"{ew}: uri required")
            if "description" not in e:
                p.append(f"{ew}: description required")
            if e.get("commit") is not None and not HEX40.match(str(e["commit"])):
                p.append(f"{ew}: commit must be a full SHA or null")
            if e.get("report_sha256") is not None and not HEX64.match(str(e["report_sha256"])):
                p.append(f"{ew}: report_sha256 invalid")
    if not isinstance(doc.get("updated_at"), str):
        p.append("updated_at must be a string")
    return p


def schema_hash_problem(root: Path):
    schema = root / "status" / "status.schema.json"
    rec = root / "status" / "status.schema.json.sha256"
    if not schema.is_file() or not rec.is_file():
        return "vendored schema or its .sha256 is missing"
    want = rec.read_text().split()[0]
    got = hashlib.sha256(schema.read_bytes()).hexdigest()
    return None if want == got else "status.schema.json does not match its recorded SHA-256"


def check(root: Path):
    root = Path(root)
    problems = []
    h = schema_hash_problem(root)
    if h:
        problems.append(h)
    path = root / "status" / "status.json"
    if not path.is_file():
        return problems + ["status/status.json not found"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    problems += validate(doc)
    if doc.get("workstream_id") != WORKSTREAM_ID or doc.get("repo") != REPO:
        problems.append("workstream_id or repo does not match this repository")
    rows = parse_tasks((root / "planning" / "TASKS.md").read_text(encoding="utf-8"))
    reported = [t.get("task_id") for t in doc.get("tasks", [])]
    if sorted(reported) != sorted(REPORTED_TASKS):
        problems.append(f"reported tasks {sorted(reported)} differ from REPORTED_TASKS {sorted(REPORTED_TASKS)}")
    for t in doc.get("tasks", []):
        tid = t.get("task_id")
        if tid not in rows:
            problems.append(f"{tid}: not in planning/TASKS.md")
        elif rows[tid] not in EXECUTION:
            problems.append(f"{tid}: unrecognised status {rows[tid]!r}")
        elif EXECUTION[rows[tid]] != t.get("execution"):
            problems.append(f"{tid}: execution {t.get('execution')} differs from TASKS.md ({rows[tid]})")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--print", dest="show", action="store_true")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    try:
        if a.check:
            problems = check(root)
            for x in problems:
                print(f"FAIL {x}")
            print(f"gen_status --check: {'FAIL' if problems else 'PASS'} ({len(problems)} problem(s))")
            return 1 if problems else 0
        doc = build(root)
        bad = validate(doc)
        if bad:
            raise StatusError("generated report is invalid: " + "; ".join(bad))
        text = json.dumps(doc, indent=2) + "\n"
        if a.show:
            sys.stdout.write(text)
        else:
            out = root / "status" / "status.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out.relative_to(root)} ({len(doc['tasks'])} task(s) reported)")
        return 0
    except StatusError as e:
        print(f"gen_status: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
