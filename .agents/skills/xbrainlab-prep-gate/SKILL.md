---
name: xbrainlab-prep-gate
description: Use when continuing XBrainLab's stabilization prep gate before normal bug-fixing. Trigger for prompts like continue stabilization, continue autopilot, finish the prep gate, verify workflows, audit dialogs, widen refresh coverage, or triage current runtime signals. Do not trigger for unrelated OpenAI product questions or for confirmed repair-loop work after prep is complete.
---

# XBrainLab Prep Gate

Use this skill for the repeated pre-bugfix stabilization loop in this repository.

## Read First

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/PLAN.md`
7. `docs/STATUS_REPORT.md`
8. `docs/BUG_TRIAGE.md`
9. `docs/SESSION_LOG.md`

Open deeper docs only when the current queue item needs them.

## Scope

Stay within prep-gate work:

- workflow baseline verification
- high-risk dialog acceptance checks
- refresh and navigation smoke protection
- runtime-signal triage
- validation harness and documentation hardening
- local development and Codex setup clarification

Do not jump into broad repair-loop work unless the queue explicitly says prep is complete.

## Working Pattern

1. Choose the top eligible prep-gate item from `.agents/runbooks/active-queue.md`.
2. Reproduce the issue or gather runtime evidence first.
3. Add the narrowest useful test when practical.
4. Make the smallest effective fix or supporting refactor.
5. Run the smallest relevant validation slice.
6. If shared UI plumbing changed, re-run `tests/unit/ui -q` with the current workspace workaround.
7. Update:
   - `.agents/runbooks/active-queue.md`
   - `docs/STATUS_REPORT.md`
   - `docs/SESSION_LOG.md`
   - `docs/BUG_TRIAGE.md`
   - `docs/BACKLOG.md`

## Validation Notes

- In this workspace, local pytest runs should currently use `-s` until the capture teardown issue is resolved.
- For UI baseline capture, use `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`.
- For real-data IO coverage, use `/home/administrator/.local/bin/poetry run pytest -s tests/integration/io/test_io_integration.py -q`.

## Evidence Standard

Do not mark progress as done without at least one of:

- a passing targeted test
- a passing smoke run
- a concrete runtime-log improvement
- a documented manual validation result

## Communication Rule

Keep `docs/STATUS_REPORT.md` aligned to the four-part human plan:

1. Baseline And Checkpoint
2. Codex Harness And Always-On Loop
3. Prep Gate Before Stable Bug Fixing
4. Repair Loop
