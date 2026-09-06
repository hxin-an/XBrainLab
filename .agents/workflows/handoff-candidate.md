# Workflow: Handoff Candidate

最後更新：`2026-09-06`

Use before telling the user a branch is ready for manual testing; the goal is to keep the user from being first-line QA, not to replace native human acceptance.

An authorized ordinary commit, push, or PR does not claim handoff-ready or require this dossier; it still needs focused validation. Merge approval remains separate.

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

Search the changed owner and directly coupled call sites for duplicated readiness, direct/private
mutation, stale callbacks, label/event variants, cleanup, and repeated layout. A match blocks only
when it reproduces the defect, creates direct safety/data loss, or invalidates handoff evidence.
Keep independent matches as advisory follow-up. Add a source guard only for a stable static rule.

## 4. Happy path and edges

Exercise one user-like path and adjacent failure/cancel/repeat behavior. Select commands from
`docs/validation/README.md`; executable gates come only from `scripts/dev/handoff_gate_spec.py`.

- Visible UI: behavior test plus screenshot/walkthrough.
- Data/import/label/epoch/training/evaluation/visualization: required source-diverse dataset gate.
- Backend/ApplicationService: focused command test plus architecture/source guard.
- Async/resource: lifecycle, stale-callback, cleanup, and bounded-time evidence.
- Docs-only/guidance-only: focused contract tests, source audit, diff check, and MkDocs strict build.
- MCP: executable surface retired; no current handoff gate exists.

If a required gate is too slow or unavailable, return a checkpoint; do not silently reduce it.

## 5. Artifact review

The primary agent must inspect artifacts, not only trust a script verdict. For UI check hierarchy,
contrast, wrapping, clipping, primary action, scroll, dialog geometry, empty/loading/error/blocked
states, and relevant DPI/widths. Offscreen evidence does not replace Windows native acceptance.

## 6. Branch and CI

Require a focused commit, pushed exact SHA, PR to the intended `main`, and CI whose head SHA exactly
matches the PR head. CI and every non-skipped reported check must be completed/successful. Missing,
pending, stale, cancelled, or failed evidence fails closed; do not use auto-merge as a substitute.

Manual-test pass and merge approval are merge prerequisites, not engineering handoff-ready prerequisites.
For product behavior PRs, record date, scope, and source under `Manual acceptance`; later source changes require retest. Automation does not substitute.

## 7. Final report

Report identity, scope, focused/adjacent evidence, sweep/guard, artifacts, dirty state, CI, and claim
boundary. End with exactly one label: `handoff-ready`, `checkpoint`, or `blocked`.

Final totals or PASS claims must come from the same exact commit and canonical evidence identity,
never from chat notes, stale dashboards, different SHAs, hidden skips, or reduced denominators.
