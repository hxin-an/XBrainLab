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

## Current Product-Quality Closure Flow

The active integration worktree is
`build/worktrees/assistant-product-v1`, on
`stabilize/product-quality-closure`. Branch governance and handoff governance are
one flow:

```text
ux/assistant-product-v1@3869aaef
  baseline only
  -> stabilize/product-quality-closure
      bounded audit slices and checkpoint evidence
  -> one clean pushed exact commit
      handoff candidate gate
  -> user Windows acceptance
      explicitly agreed main merge gate
```

Rules:

- Confirm the branch and worktree from Git before acting; do not copy branch
  inventory from records or old plans.
- Treat `stabilize/product-quality-closure` as the current shared integration
  line. Preserve existing dirty work and use bounded ownership; do not switch
  branches or create a task branch unless the user or main agent requests it.
- A deliberately split task branch owns one finding, one evidence gap, or one
  boundary cleanup. It returns to the integration line only after focused
  regression, same-class sweep, relevant tests/artifacts, commit, and push.
- Current closure authority is
  `docs/agent_goals/product_quality_closure_goal.md` plus
  `docs/records/product_quality_audit_2026-07-30.md`. Do not create a parallel
  `AQ-*`, `Prep Gate`, or `Repair Loop` task system.
- A merged slice or validated checkpoint does not make the product ready for
  manual testing. Only the clean exact integration commit may enter the handoff
  candidate gate.
- `main` receives the integration line only after user acceptance or an
  explicitly agreed release-candidate gate.
- If a change cannot be kept reviewable, split it before implementation or
  report it as a checkpoint with explicit remaining risk.

The former `stabilize/desktop-mvp` flow is superseded history. It may remain in
dated records for provenance, but it is not the current integration branch, task
base, merge destination, or validation authority.

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
