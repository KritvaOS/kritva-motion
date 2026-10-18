# kritva-motion

Kritva Motion: part of Kritva OS V2, planned and tracked from [kritva-program](https://github.com/KritvaOS/kritva-program).

**Status:** planning and governance baseline only. There is no implementation yet; the first task (KOS-MOTION-001, Motion command and state contract) is proposed and not yet approved.

## Scope

Owns: the motion command and state contract: command lifecycle, units, limits, feedback, timeout, cancellation, fault behaviour and the safety boundary of the contract.

Does not own: actuator hardware, firmware and transport (kritva-actuator family, on HOLD), sensing (kritva-sense), skill orchestration (kritva-skill), and any physical safety validation.

Depends on: kritva-core (approved contract), kritvaos-community (public architecture description).

## Layout

| Path | Purpose |
|---|---|
| [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) | Acceptance criteria and test gates |
| [planning/](planning/) | Tasks, milestones, review checklist, commit step, changelog |
| [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) | Rules for contributors, agents and vulnerability reporting |
| [Makefile](Makefile) | Standard check targets (unimplemented gates report NOT_IMPLEMENTED, never pass) |
| `.github/` | CODEOWNERS and the secret-scan and commit-message-check workflows |

Source folders are added only when the first real task needs them.

## Checks

```bash
make check   # planning files present, commit-checker self-test
make test    # reports NOT_IMPLEMENTED (exit 3) until tests exist
```

## Program alignment

Milestones: V2-M0-MOTION-001 (governance baseline), V2-M1-MOTION-001 (contract), V2-M2-MOTION-001 (validation). Dates are proposed in kritva-program `v2/planning/` and are not approved. Nothing in this repository adds baseline weight or credit.
