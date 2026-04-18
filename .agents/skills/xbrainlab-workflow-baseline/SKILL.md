---
name: xbrainlab-workflow-baseline
description: Use when mapping, verifying, or refreshing XBrainLab's runtime workflow baseline. Trigger for prompts like verify main workflows, baseline panels, collect headless runtime evidence, update workflow docs, or capture shell and panel happy paths. Do not trigger for narrow bug fixes or backend-only refactors that do not need workflow evidence.
---

# XBrainLab Workflow Baseline

Use this skill when the task is to turn workflow assumptions into observed runtime facts.

## Read First

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/current/PLAN.md`
7. `docs/current/STATUS_REPORT.md`
8. `docs/workflows/WORKFLOWS.md`
9. `docs/workflows/UI_BASELINE.md`
10. `docs/history/SESSION_LOG.md`

## Scope

Focus on:

- main window startup
- Dataset / Preprocess / Training / Evaluation / Visualization panels
- AI assistant shell
- headless happy-path verification
- screenshot baseline collection and refresh

## Working Pattern

1. Confirm which workflow or panel needs evidence.
2. Reproduce the flow in headless mode where possible.
3. Capture artifacts using the repo's capture helper instead of ad hoc screenshots.
4. Record runtime observations, not guesses.
5. Update workflow and baseline docs when the observed behavior changes or becomes clearer.

## Validation Commands

- `timeout 25s xvfb-run -a /home/administrator/.local/bin/poetry run python run.py`
- `xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py`
- `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_main_window_sync.py -q`

## Recordkeeping

After meaningful progress, update:

- `docs/workflows/WORKFLOWS.md`
- `docs/workflows/UI_BASELINE.md`
- `docs/current/STATUS_REPORT.md`
- `docs/history/SESSION_LOG.md`
- `.agents/runbooks/active-queue.md`
