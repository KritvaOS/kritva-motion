#!/usr/bin/env python3
"""Check README.md against the Kritva README standard (kritva-program D-055).

  check_readme.py README.md [--root DIR]

Implemented checks, and nothing more: the metadata table has every required
field and none is empty; every topic of the standard appears as a heading
(matched by keyword, so a broad match can pass); every relative Markdown link
[text](path) points to an existing file or directory (the #fragment is not
checked; image links and absolute URLs are skipped); no placeholder text is
left outside code (fenced blocks, inline code and lines indented by four
spaces or a tab are code; links are still checked on indented lines).
A PASS does not show that content is accurate, a command works, an external
URL is reachable, an anchor exists or anything is approved; that is review
work (v2/planning/standards/README_REVIEW_CHECKLIST.md in kritva-program).
Exit 0 if it passes, 1 if not. Stdlib only.
"""
import argparse
import re
import sys
from pathlib import Path

FIELDS = ["Project", "Repository", "Repository Type", "Visibility Class", "GitHub Setting", "Lifecycle Status",
          "Repository Owner", "Architecture", "Milestones", "Tasks", "Acceptance Criteria", "Status Reporting", "License"]

# topic -> regex matched against the heading text (case-insensitive)
TOPICS = {
    "purpose and scope": r"purpose|scope",
    "position in the ecosystem": r"ecosystem|position|context",
    "architecture": r"architecture",
    "documents to read": r"documents?|index|read first|where to start",
    "repository structure": r"structure|layout|responsibilit",
    "tool and development workflow": r"tool|workflow|toolchain|getting started",
    "dependencies": r"dependenc|interfaces",
    "milestones": r"milestone|roadmap|implementation plan|planning",
    "tasks and acceptance": r"acceptance|tasks",
    "status reporting": r"status",
    "validation": r"validation|regression|test",
    "git workflow": r"git|contribut",
    "safety and security": r"safety|security",
    "release and versioning": r"release|version",
    "ownership": r"owner|support|governance",
    "related repositories": r"related|references|ecosystem overview",
    "license": r"licen[cs]e",
}
PLACEHOLDER = re.compile(r"<(?:[A-Za-z][A-Za-z /|_.-]*)>|\bTODO\b|\bTBD\b|<YYYY")
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def strip_code(text):
    """Blank fenced code blocks and inline code so links and placeholders in examples are ignored."""
    text = re.sub(r"^(```|~~~).*?^\1[^\n]*$", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "``", text)


def metadata(text):
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if m and not set(m.group(1)) <= set("-: "):
            rows.setdefault(m.group(1), m.group(2))
    return rows


def check(readme: Path, root: Path):
    raw = readme.read_text(encoding="utf-8")
    text = strip_code(raw)
    problems = []
    rows = metadata(text)
    for f in FIELDS:
        if f not in rows:
            problems.append(f"metadata field missing: {f}")
        elif not rows[f] or re.fullmatch(r"[-.]*", rows[f]):
            problems.append(f"metadata field empty: {f}")
    heads = [m.group(2).strip() for m in re.finditer(r"^(#{1,3})\s+(.*)$", text, re.M)]
    for topic, rx in TOPICS.items():
        if not any(re.search(rx, h, re.I) for h in heads):
            problems.append(f"no heading for: {topic}")
    for n, line in enumerate(text.splitlines(), 1):
        indented = line.startswith(("    ", "\t"))  # an indented code block may show a template on purpose
        for m in ([] if indented else PLACEHOLDER.finditer(line)):
            problems.append(f"line {n}: placeholder left: {m.group(0)}")
        for m in LINK.finditer(line):
            target = m.group(1)
            if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if path and not (readme.parent / path).resolve().exists():
                problems.append(f"line {n}: link does not resolve: {target}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("readme", nargs="?", default="README.md")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    readme = Path(a.readme)
    if not readme.is_file():
        print(f"check_readme: {readme} not found")
        return 1
    problems = check(readme, Path(a.root))
    for p in problems:
        print(f"FAIL {p}")
    print(f"check_readme: {'FAIL' if problems else 'PASS'} ({readme}, {len(problems)} problem(s))")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
