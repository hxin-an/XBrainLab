# Workflow: Handoff Candidate

最後更新：`2026-08-11`

Use before telling the user a branch is ready for manual testing. The goal is to keep the user from
being first-line QA, not to replace native human acceptance.

## Classification

- `checkpoint`: a bounded slice is validated but one or more handoff gates remain.
- `handoff-ready`: every applicable section below passed on one clean/explained exact commit.
- `blocked`: completion needs an external environment, user decision, or unavailable evidence.

## 1. Identity and scope

Record branch, HEAD, upstream, `git status --short --branch`, generated worktree inventory, scope,
non-goals, and preserved dirty files. Do not infer any value from old docs or records.

## 2. Focused protection

Reproduce the reported bug with a failing test or observable artifact. For behavior-preserving
refactors, establish a passing characterization baseline instead. Re-run the same protection after
the change.

## 3. Same-class sweep

Search the relevant class across call sites and workflows. Examples include duplicated readiness,
manual refresh, direct/private mutation, async stale callbacks, label/event variants, figure/thread
cleanup, and repeated layout components. Add a source guard when a stable static rule can prevent
recurrence. Fix blocking matches or report `blocked`.

## 4. Happy path and edges

Exercise one user-like path and the adjacent failures/cancellation/repeat behavior for the changed
area. Declare the intended claim and scope, generate the source-bound validation plan, execute it,
persist its receipt, then run the independent `verify` subcommand through
`scripts/dev/run_validation_control_plane.py`. Reuse the same authorized target SHA at plan, run,
and verify. A receipt-level result from `run` alone is not a handoff verdict. Executable gate policy
comes only from `scripts/dev/handoff_gate_spec.py`; do not select or copy leaf commands from
documentation.

- Visible UI: behavior test plus screenshot/walkthrough.
- Data/import/label/epoch/training/evaluation/visualization: required source-diverse dataset gate.
- Backend/ApplicationService: focused command test plus architecture/source guard.
- Async/resource: lifecycle, stale-callback, cleanup, and bounded-time evidence.
- Docs-only/guidance-only: focused contract tests, source audit, diff check, and MkDocs strict build.
- MCP: only when the user explicitly requested MCP scope.

If a required gate is too slow or unavailable, return a checkpoint; do not silently reduce it.
The legacy-named `run_handoff_validation_manifest.py` entrypoint may be used for the full handoff
inventory only because it delegates to the same plan/receipt/dossier/verdict path.
Its `--target-sha` must be the immutable authorized target tip, normally the `origin/main` SHA after
an explicit fetch from the reviewed remote; a mutable or merely local ref name alone cannot
authorize a claim-bearing comparison base. Pass the current candidate branch explicitly with
`--expected-branch`; no historical branch default is valid.

## 5. Artifact review

The primary agent must inspect artifacts, not only trust a script verdict. For UI check hierarchy,
contrast, wrapping, clipping, primary action, scroll, dialog geometry, empty/loading/error/blocked
states, and relevant DPI/widths. Offscreen evidence does not replace Windows native acceptance.

## 6. Branch and CI

Require a focused commit, pushed exact SHA, PR to the intended `main`, and CI whose head SHA exactly
matches the PR head. CI and every non-skipped reported check must be completed/successful. Missing,
pending, stale, cancelled, or failed evidence fails closed; do not use auto-merge as a substitute.

## 7. Final report

Report branch/SHA/upstream, scope/non-goals, focused result, same-class sweep/guard, happy path,
edge/regression, artifacts reviewed, dirty-state explanation, CI status, and claim boundary. End
with exactly one label: `handoff-ready`, `checkpoint`, or `blocked`.

Final totals or PASS claims must come from the same exact commit and canonical evidence identity,
never from chat notes, stale dashboards, different SHAs, hidden skips, or reduced denominators.
