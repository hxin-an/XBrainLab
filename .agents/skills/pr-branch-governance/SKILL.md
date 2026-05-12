---
name: pr-branch-governance
description: Apply XBrainLab branch, pull request, dirty-worktree, scope ownership, and parallel-agent governance. Use before creating branches, preparing PRs, committing, pushing, splitting work across subagents, doing background engineering cleanup, test cleanup, clean-code refactors, or separating UX work from backend/test work.
---

# PR Branch Governance

## Purpose

Use this skill to keep XBrainLab work reviewable when multiple threads, branches,
agents, or PRs are active.

The goal is not process ceremony. The goal is to prevent UX work, backend refactor,
test cleanup, and legacy fallback changes from collapsing into one unreviewable diff.

## Start Gate

Before editing, run:

```bash
git status --short
git branch --show-current
```

Then state:

- current branch
- intended branch / PR scope
- files or areas intentionally not touched
- dirty files that are unrelated and must be preserved

Do not use `git reset --hard`, `git checkout --`, or destructive cleanup unless the
user explicitly asks for that operation.

## Branch Rules

- Do not do feature/refactor work directly on `main`.
- One branch should have one main objective.
- UX exploration and backend/test hygiene must be separate branches.
- If a task would touch two product areas, split it unless the same validation proves
  both together.
- If the worktree is already dirty, work with existing changes; do not overwrite or
  normalize unrelated files.

Recommended branch names:

- `ux/data-import-label-flow` for Load Labels / Match Labels UX.
- `fix/<area>-<bug>` for narrow user-visible bug fixes.
- `test/<area>-coverage` for test protection work.
- `refactor/<area>-hygiene` for clean-code/backend cleanup.
- `docs/<area>` for docs-only work.
- `wip/<area>` for checkpoints not ready for PR.

## MVP Stabilization Branch Strategy

When the product is not yet runnable or MVP-stable, do not merge the unstable
state into `main`. Use a stabilization branch as the integration line:

```text
main
  |
  +-- codex/stabilization-autopilot or stabilize/<mvp-area>
        |
        +-- fix/<one-blocker>
        +-- test/<one-evidence-gap>
        +-- refactor/<one-boundary>
```

Rules for this mode:

- `main` should only receive states that are runnable and validated enough to be
  better than the previous baseline.
- The stabilization branch may hold the MVP integration state, but do not keep
  piling unrelated work directly onto it.
- Create small branches from the stabilization branch for one blocker, one test
  gap, or one boundary cleanup; merge them back into the stabilization branch
  after focused validation.
- Merge the stabilization branch into `main` only after the agreed MVP minimum
  works end to end and the required dashboard / docs / smoke gates pass.
- If a branch cannot start the app, complete the representative product flow, or
  explain its known blockers, it may be a draft integration branch but it is not
  ready for `main`.

Recommended minimum before merging a stabilization branch to `main`:

- app launches through the intended launcher or `run.py`;
- `MainWindow` is visible;
- representative Data Import can scan, preview, and apply one fixture or agreed
  local sample;
- local LLM unavailable state is visible and non-crashing;
- fast quality dashboard is `PASS`;
- `mkdocs build --strict` is `PASS`;
- worktree is clean and remaining risks are documented.

## Scope Separation

Keep these apart unless the user explicitly asks to combine them:

- UX layout/copy/design
- backend command/API behavior
- test inventory or obsolete test deletion
- clean-code refactor
- agent/MCP behavior
- docs-only sync

For Data Import specifically:

- Do not redesign `Load Labels` / `Match Labels` from a backend/test cleanup branch.
- Do not make large layout/copy changes in `data_interpretation_preview_dialog.py`
  unless the branch is explicitly a UX branch.
- Backend/test branches may fix bugs or add protection tests for Data Import, but must
  preserve the current UX contract.

## PR Rules

A PR-ready summary must include:

- scope
- intentionally not touched
- files / areas changed
- tests added, changed, or removed
- validation commands and results
- remaining risks / what cannot be claimed complete

Do not open or describe a PR as ready if:

- it mixes unrelated UX and backend refactor work
- it deletes tests without stronger replacement coverage
- it leaves command/API parity unvalidated after touching backend workflow
- it relies on dashboard PASS alone as product evidence
- it changes visible UI without screenshot/artifact evidence

## Test Cleanup Rules

Test cleanup is allowed only when it improves protection.

- Classify tests before deleting: strong, mock-heavy, implementation-detail, obsolete,
  duplicated, missing-coverage marker.
- Replace weak tests with stronger behavior/state/recipe/action-result assertions before
  deleting them.
- Prefer tests that validate state deltas, command results, recipe traces, UI-visible
  behavior, or real side effects.
- Do not keep a mock-heavy test just because it passes if it no longer protects a real
  product path; either replace it or mark the remaining risk.

## Parallel Agent Rules

When using subagents:

- Give each subagent a disjoint ownership area.
- Tell workers they are not alone in the codebase and must not revert others' work.
- Do not assign UX redesign to backend/test cleanup workers.
- Main agent must review diffs and run validation; worker completion is not evidence.
- If a worker hits a UX/product decision, stop that part and return it to the main
  conversation instead of guessing.

Suggested split for background engineering:

- Backend boundary audit
- Test inventory
- Validation coverage
- Clean-code refactor

## Validation Gate

Choose validation based on touched areas:

- Backend/command: focused backend unit tests plus command/service parity tests.
- UI route or dialog: focused UI tests with `QT_QPA_PLATFORM=offscreen`.
- Docs: `mkdocs build --strict`.
- Refactor: original focused tests plus at least one workflow-level guard.
- PR candidate: lint/type checks plus the smallest meaningful integration smoke.

Always report validation that was not run and why.
