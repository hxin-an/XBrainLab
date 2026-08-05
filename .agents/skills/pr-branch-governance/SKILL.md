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
- Before creating another task branch, dispose of the current branch by merging it,
  closing it, or explicitly recording it as a retained checkpoint. Do not stack a
  new branch on an unmerged task branch unless an integration stack was explicitly
  agreed in advance.

Recommended branch names:

- `ux/data-import-label-flow` for Load Labels / Match Labels UX.
- `fix/<area>-<bug>` for narrow user-visible bug fixes.
- `test/<area>-coverage` for test protection work.
- `refactor/<area>-hygiene` for clean-code/backend cleanup.
- `docs/<area>` for docs-only work.
- `wip/<area>` for checkpoints not ready for PR.

## Current Delivery Flow

The current product baseline is `main`. Teacher-facing fixes and bounded product
work use short branches and return through one explicit PR flow:

```text
main
  -> one short task branch
      focused regression + same-class sweep + relevant gate
  -> pushed exact commit + PR
  -> exact-head CI completed/success
  -> user acceptance or explicitly agreed merge gate
  -> merge to main
  -> fetch + fast-forward local main + verify remote containment
```

Rules:

- Confirm the branch and worktree from Git before acting; do not copy branch
  inventory from records or old plans.
- A task branch owns one primary objective. A merge-blocking CI compatibility fix
  may join the same PR only when it is the minimum change required to execute that
  PR's required gate, and must be called out in the PR.
- Do not start another task branch from an unmerged task branch. Return to updated
  `main` first, unless an explicit integration stack records the dependency and
  merge order.
- A validated checkpoint is pushed and opened as a PR; `push` alone is not merge.
- `main` receives the PR only after user acceptance or an explicitly agreed merge
  gate and the exact-head CI rule below.
- If a change cannot be kept reviewable, split it before implementation or
  report it as a checkpoint with explicit remaining risk.

## Exact-Head PR Merge Gate

Before merging a PR:

1. Read the PR head SHA and base branch; the base must be the intended `main`.
2. Find the latest `CI` workflow run whose `headSha` exactly equals the PR head.
3. Require that run to be `completed` with conclusion `success`.
4. Require every reported non-skipped PR check to be completed and successful.
5. If CI is pending, wait. If it failed, inspect and fix it. If infrastructure
   failed, rerun it and still require the rerun to pass.
6. Merge through the PR, then fetch, switch to local `main`, fast-forward only,
   and verify that `origin/main` contains the PR head SHA.

Fail closed when an exact-head CI run is absent, pending, cancelled, stale, or
failed. Do not use `gh pr merge --auto`: without protected required checks GitHub
can merge immediately while CI is still pending. Do not bypass this rule because
local tests passed.

## Long-Running Closure Checkpoints

Important progress must not stay local-only during long-running closure work. After
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

Recommended minimum before presenting the integration branch as a handoff candidate:

- app launches through the intended launcher or `run.py`;
- `MainWindow` is visible;
- representative Data Import can scan, preview, and apply one fixture or agreed
  local sample;
- local LLM unavailable state is visible and non-crashing;
- handoff quality dashboard is rebuilt from the same clean exact commit;
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
- assistant behavior
- explicitly requested, opt-in MCP work
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
