# Contributing to kritva-motion

1. Work from a task in [planning/TASKS.md](planning/TASKS.md). If there is none, propose one first.
2. Branch from `main` and open a pull request; do not push to `main`.
3. Commit format: `type(scope): summary` plus one `Task:` or `Tasks:` footer (`Tasks: None (reason)` on a docs or chore commit that implements no task). PRs use `.github/PULL_REQUEST_TEMPLATE.md`; the merge method is a merge commit. See [AGENTS.md](AGENTS.md).
4. Run `make check` and the test targets that apply; report results in the PR.
5. Add or update the changelog ([planning/CHANGELOG.md](planning/CHANGELOG.md)) and, for a closing milestone, a `COMPLETION_RECORD.md`.
6. Required checks: secret-scan, commit-message-check and pr-acceptance-gate (D-061). Review by the Code Owner (see `.github/CODEOWNERS`).

Do not commit secrets, generated session metadata or empty placeholder folders.
