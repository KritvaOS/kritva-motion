#!/usr/bin/env python3
"""docs-check: every relative link in the Markdown files must point at an existing file."""
import re, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
bad = []
for md in sorted(root.rglob("*.md")):
    if ".git" in md.parts:
        continue
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", md.read_text(encoding="utf-8")):
        if re.match(r"^[a-z]+:", target):
            continue
        if not (md.parent / target).exists():
            bad.append(f"{md.relative_to(root)}: broken link {target}")
print("\n".join(bad) or "docs-check ok")
sys.exit(1 if bad else 0)
