# Review Checklist: kritva-motion

- [ ] Task ID and acceptance criteria exist and are unchanged by this PR (or changed under change control).
- [ ] Commit headers follow `type(scope): summary` and each has exactly one `Task:` footer.
- [ ] No AI-session trailer, link, secret or production data.
- [ ] Required checks passed on the exact PR head: secret-scan, commit-message-check, plus the test gates that apply.
- [ ] No unimplemented gate is reported as a pass.
- [ ] Interfaces are versioned; a breaking change has a MAJOR bump, changelog entry and approved decision.
- [ ] Dependencies are used through versioned contracts, not internals.
- [ ] Changelog and documentation updated; evidence references are commit SHAs and CI run IDs.
- [ ] Approvals match the required roles in kritva-program `v2/planning/repo-pipeline.json` and were given on the current head.
