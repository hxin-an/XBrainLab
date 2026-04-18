# XBrainLab Autopilot Mechanism

This document defines how Codex should continue stabilization work in this repository without needing the user to restate the plan every time.

## Core Rule

Keep moving on the highest-value eligible task. Do not stop just because one subtask finished.

The queue has two phases:

1. `Prep Gate`
2. `Repair Loop`

Stay in `Prep Gate` until the prep-complete criteria are met.

## Eligible Work

Autopilot work is allowed when all of the following are true:

- work stays inside the local XBrainLab environment
- work does not intentionally redesign layouts or visual structure
- work does not require missing product judgement from the user
- work is not destructive
- any deep refactor stays inside the allowed backend/test-infra scope

## Prep Gate

`Prep Complete` is achieved only when all of these are true:

- startup and validation commands are trustworthy and documented
- screenshot baseline capture produces usable non-black artifacts
- the six primary workflows have runtime-verified baselines
- high-risk dialogs have at least one live/modal review pass recorded
- refresh and navigation smoke protection is strong enough for shared UI work
- risk clusters have been converted into concrete bug IDs and priorities
- notable runtime signals are fixed or triaged into reproducible issues
- local-only development and Codex operating assumptions are written down clearly

Prep task order:

1. visual baseline reliability
2. workflow baseline verification
3. high-risk dialog acceptance flows
4. refresh and navigation smoke protection
5. remaining runtime-signal triage
6. local-only and Codex operating assumptions

## Repair Loop

After `Prep Complete`, use this default task order unless new evidence changes it:

1. dataset and load-data reliability
2. preprocess readiness and downstream state
3. training state synchronization
4. evaluation consistency
5. visualization stabilization
6. AI shell and local-only cleanup

Allowed deep work:

- backend state, service, facade, and controller boundaries
- load-data pipeline
- shared non-visual UI plumbing
- test infrastructure, fixtures, and harness

Not allowed without user discussion:

- panel composition redesign
- sidebar arrangement redesign
- dialog visual redesign
- other intentional layout changes

## Loop

For each work cycle:

1. read `AGENTS.md`, `.agents/stack.md`, `.agents/runbooks/setup.md`, and `.agents/runbooks/active-queue.md`
2. use `$xbrainlab-prep-gate` while `Prep Gate` is active
3. switch to `$xbrainlab-repair-loop` only after prep is complete or the task is a clearly confirmed repair-loop item
4. reproduce the issue or verify current behavior
5. add the narrowest useful test when practical, or capture strong manual/runtime evidence
6. make the smallest effective fix or supporting refactor
7. run the smallest relevant validation slice
8. re-run broader shared tests if shared UI or shared backend plumbing changed
9. update:
   - `docs/BUG_TRIAGE.md`
   - `docs/BACKLOG.md`
   - `docs/SESSION_LOG.md`
   - `docs/STATUS_REPORT.md`
   - `.agents/runbooks/active-queue.md`
10. continue unless a stop condition is hit

## Required Evidence

Before treating work as complete, collect at least one of:

- a passing targeted test
- a passing smoke test
- a clear runtime log improvement
- a documented manual validation result

## Stop Conditions

Pause and wait for the user when any of these happen:

- a change would intentionally alter layout or visual design
- a change would remove or fundamentally reshape a user-facing workflow
- a large architectural rewrite appears necessary outside the allowed scope
- work needs risky actions outside the repo or local Codex setup
- a bug has multiple plausible product directions and the right one is not obvious

## Recordkeeping

Every meaningful cycle should leave traces in:

- `.agents/runbooks/active-queue.md`
- `docs/SESSION_LOG.md`
- `docs/BUG_TRIAGE.md`
- `docs/BACKLOG.md`
- `docs/STATUS_REPORT.md`

## Current Automation Note

The current thread has a heartbeat automation named `XBrainLab Autopilot` scheduled every 10 minutes. It should follow this document, the active queue, and the user-facing status report.
