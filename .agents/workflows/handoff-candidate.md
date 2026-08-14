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

Search the changed owner and directly coupled call sites for the relevant class. Examples include duplicated readiness,
manual refresh, direct/private mutation, async stale callbacks, label/event variants, figure/thread
cleanup, and repeated layout components. A match blocks only when it can reproduce the same defect,
break the declared contract, create direct safety/data loss, or invalidate the handoff evidence.
Keep independent matches as advisory follow-up. Add a source guard only for a stable static rule.

## 4. Happy path and edges

Exercise one user-like path and the adjacent failures/cancellation/repeat behavior for the changed
area. Select commands from `docs/validation/README.md`; executable handoff gates come only from
`scripts/dev/handoff_gate_spec.py` via its canonical runner.

- Visible UI: behavior test plus screenshot/walkthrough.
- Data/import/label/epoch/training/evaluation/visualization: required source-diverse dataset gate.
- Backend/ApplicationService: focused command test plus architecture/source guard.
- Async/resource: lifecycle, stale-callback, cleanup, and bounded-time evidence.
- Docs-only/guidance-only: focused contract tests, source audit, diff check, and MkDocs strict build.
- MCP: only when the user explicitly requested MCP scope.

If a required gate is too slow or unavailable, return a checkpoint; do not silently reduce it.

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
