# XBrainLab Agent Guide

This file is the short map for any AI coding agent working in this repository.

## Mission

Stabilize the existing PyQt application without making it harder to reason about.

Immediate goals:

- keep the app runnable in a repeatable way
- understand workflows, failure modes, and risk boundaries
- add enough safety rails that bug fixes do not create fresh regressions
- then repair high-value bugs and structural issues incrementally

This is a stabilization project, not a feature-expansion or visual-redesign project.

## Start Here

Read these in order before substantial work:

1. `docs/CODEX_SETUP.md`
2. `docs/AUTOPILOT.md`
3. `docs/ACTIVE_QUEUE.md`
4. `docs/BUG_TRIAGE.md`
5. `docs/SESSION_LOG.md`

Open deeper docs only as needed:

- `docs/TAKEOVER.md`
- `docs/TESTING_STRATEGY.md`
- `docs/UI_BASELINE.md`
- `docs/WORKFLOWS.md`
- `docs/RISK_CLUSTERS.md`
- `docs/DIALOG_MATRIX.md`
- `docs/COVERAGE_GAPS.md`
- `docs/BACKLOG.md`

## Core Rules

1. Understand before editing.
2. Prefer small, verifiable changes over broad refactors unless the queue explicitly calls for deeper work.
3. Do not trust docs blindly; verify against the code and current runtime behavior.
4. Keep UI bugs, workflow bugs, and structural/backend bugs conceptually separate.
5. Preserve headless testability whenever possible.
6. Keep repo-specific operating knowledge in repo docs, not in ad hoc local notes.

## Design Boundaries

Do not proactively redesign layouts the user is already satisfied with.

Functional fixes are allowed. Layout breakage fixes are allowed. Intentional visual or layout redesign requires user discussion first.

Be especially careful in:

- `XBrainLab/ui/main_window.py`
- `XBrainLab/ui/core/*`
- `XBrainLab/backend/study.py`
- `XBrainLab/backend/training_manager.py`
- `tests/conftest.py`

## Validation Rules

For non-trivial changes:

1. identify the affected workflow
2. reproduce the issue or record the failure signal
3. add the narrowest useful test when practical
4. make the fix
5. run the smallest relevant validation slice first
6. re-run `tests/unit/ui` if shared UI plumbing changed
7. update the relevant docs if assumptions changed

Minimum done criteria:

- there is clear evidence of the bug or risk
- at least one focused validation slice passes, or there is a documented reason why not
- shared UI regressions are checked when common UI plumbing changed

## Current Operating Notes

- The active stabilization branch is `codex/stabilization-autopilot`.
- Preserve any existing dirty worktree changes unless they directly conflict with the current task.
- Use official OpenAI/Codex sources first for Codex, MCP, skills, or automation guidance.
- Follow the prep-first queue in `docs/ACTIVE_QUEUE.md` until `Prep Complete` is achieved.
