# Git Commit Step: kritva-motion

1. `git switch -c <type>/<short-name>` from an up-to-date `main`.
2. Commit with the format below; one task per commit.
3. `make check` (and the applicable test targets), then push the branch and open a PR.
4. Merge after required checks and approvals on the current head (kritva-program `scripts/pipeline/ship-prs.sh --manifest ...` automates the merge and an optional annotated tag).
5. Tag only after the approved merge: `git tag -a vX.Y.Z -m "..."`; a tag does not close a milestone.

```text
type(scope): summary of at most 90 characters [optional KOS-MOTION-NNN]

Task: KOS-MOTION-001
```

Several tasks: `Tasks: KOS-MOTION-001, KOS-MOTION-002`. A docs or chore commit that implements no task: `Tasks: None (reason)`. Merge method: merge commit. Use `.github/PULL_REQUEST_TEMPLATE.md` for the PR text.
