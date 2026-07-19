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

## Desktop MVP Delivery Flow

During Desktop MVP stabilization, branch governance and handoff governance are one
flow. Do not treat them as separate checklists.

```text
stabilize/desktop-mvp
  -> fix/<one-blocker> | test/<one-gap> | refactor/<one-boundary>
      task-branch gate
  -> merge back into stabilize/desktop-mvp
      stabilization handoff gate
  -> user manual acceptance
      main merge gate
  -> main
```

Rules:

- `stabilize/desktop-mvp` is the current integration line, not a scratch branch.
- Before the first repair branch for a product area, run a Desktop MVP audit
  pass from the stabilization line. The audit must look for product bugs, code
  quality risks, architecture drift, weak tests, stale artifacts, and obvious UI
  regressions across adjacent workflow areas; do not wait for the user to report
  each bug one by one.
- Product-code changes must normally happen on a short-lived task branch from
  `stabilize/desktop-mvp`.
- One task branch owns one blocker, one evidence gap, or one boundary cleanup.
- A task branch may be merged back only after focused regression, same-class
  sweep, relevant tests/artifacts, clean worktree, commit, and push.
- A task branch being merged back does not mean the product is ready for the
  user to test.
- "Ready for manual test" can only be said from the stabilization line after
  the handoff candidate gate passes.
- `main` receives the stabilization line only after user acceptance or an
  explicitly agreed release-candidate gate.
- If a fix cannot be kept small, split it before implementation or mark the
  branch as WIP/checkpoint rather than pretending it is reviewable.
- If the audit finds multiple blocking issues, create separate task branches or
  an explicit ordered blocker queue; do not hide known blockers behind a narrow
  "fixed the reported bug" claim.

This flow intentionally follows short-lived branch practice: small batches,
frequent integration, automated checks before merge, and visible product evidence
before human acceptance.

## Long-Running MVP Checkpoints

Important progress must not stay local-only during long-running MVP work. After
each validated checkpoint:

1. Run `git status --short --branch`.
2. Confirm no unrelated local files are staged. Repo-root `settings.json` is protected
   user-local LLM/runtime configuration: never stage, commit, revert, overwrite, or hide
   it with skip-worktree. It may remain as the sole explicitly reported dirty path.
3. Commit the checkpoint with a focused message.
4. Push the current branch to `origin`.
5. If the branch has no upstream, use `git push -u origin <branch-name>`.

Do not push directly to `main` unless the user explicitly approves it.

A checkpoint report should include:

- branch name
- commit hash
- validation commands and results
- remaining dirty files
- whether the branch was pushed

Local commit is not enough for important work. A checkpoint is only backed up
when it is pushed.

Recommended minimum before merging a stabilization branch to `main`:

- app launches through the intended launcher or `run.py`;
- `MainWindow` is visible;
- representative Data Import can scan, preview, and apply one fixture or agreed
  local sample;
- local LLM unavailable state is visible and non-crashing;
- fast quality dashboard is `PASS`;
- `mkdocs build --strict` is `PASS`;
- worktree is clean and remaining risks are documented.

## Manual-Test Candidate Rules

Do not tell the user a branch is ready for manual testing unless it has passed a
handoff candidate gate. A handoff candidate is stronger than a validated
checkpoint: it proves the fix did not only address the first visible symptom.

Before saying "ready to test" or "handoff-ready", complete and report:

- bug reproduction or focused regression coverage for the user-reported issue;
- same-class sweep for similar call sites, screens, command paths, or data flows;
- a happy-path product route, preferably through an automated UI walkthrough or
  screenshot-producing script when UI is involved;
- edge/regression coverage for the changed class of behavior;
- screenshot or walkthrough artifact review for visible UI changes;
- required multi-dataset gate for data/import/label/epoch/training/evaluation/
  visualization handoffs, unless the change is explicitly docs-only;
- clean or explained worktree, focused commit, and pushed branch;
- claim boundary: what this still does not prove.

If any required gate is skipped, the branch may be a checkpoint but is not a
manual-test candidate. State the blocker instead of asking the user to find the
next obvious bug.

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
