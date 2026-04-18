---
name: xbrainlab-repair-loop
description: Use when XBrainLab has moved into confirmed repair-loop work, or when the task is a clearly scoped confirmed bug fix, regression test addition, backend/test-infra refactor, or post-prep stabilization item. Do not trigger for initial repo setup or prep-gate verification work unless the queue explicitly says prep is complete.
---

# XBrainLab Repair Loop

Use this skill for steady-state repair work after prep is complete, or for clearly confirmed repair items that already have enough evidence.

## Read First

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/current/PLAN.md`
7. `docs/current/STATUS_REPORT.md`
8. `docs/current/BUG_TRIAGE.md`
9. `docs/history/SESSION_LOG.md`

## Default Order

Unless stronger evidence changes priority, prefer this order:

1. dataset and load-data reliability
2. preprocess readiness and downstream state
3. training state synchronization
4. evaluation consistency
5. visualization stabilization
6. AI shell and local-only cleanup

## Working Pattern

1. Start from a confirmed bug, failure signal, or repair-loop queue item.
2. Reproduce the issue or confirm the broken behavior.
3. Add the narrowest regression test or capture strong evidence.
4. Make the smallest effective fix, or a supporting refactor that stays inside allowed deep-work boundaries.
5. Run the smallest relevant validation slice first.
6. If shared UI plumbing changed, re-run `tests/unit/ui -q` with the current workspace workaround.
7. Update:
   - `.agents/runbooks/active-queue.md`
   - `docs/current/STATUS_REPORT.md`
   - `docs/history/SESSION_LOG.md`
   - `docs/current/BUG_TRIAGE.md`
   - `docs/history/BACKLOG.md`

## Allowed Deep Work

Deep work is allowed in:

- backend state, services, facades, and controller boundaries
- load-data pipeline
- shared non-visual UI plumbing
- test infrastructure, fixtures, and harness

Do not use this skill for intentional layout or visual redesign.
