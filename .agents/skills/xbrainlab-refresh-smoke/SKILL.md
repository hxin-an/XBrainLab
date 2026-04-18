---
name: xbrainlab-refresh-smoke
description: Use when changing or auditing XBrainLab refresh, navigation, or cross-panel propagation behavior. Trigger for MainWindow page switching, target-panel refresh rules, shared event propagation, or downstream state refresh regressions.
---

# XBrainLab Refresh Smoke

Use this skill when shared UI plumbing or cross-panel refresh behavior is involved.

## Read First

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/workflows/COVERAGE_GAPS.md`
7. `docs/current/BUG_TRIAGE.md`
8. `docs/history/SESSION_LOG.md`

## Focus Areas

- `MainWindow.switch_page()`
- target-panel-only refresh behavior
- downstream refresh after shared events
- cross-panel propagation risks

## Working Pattern

1. Identify the shared event or navigation path under change.
2. Reproduce the smallest failing or risky propagation path.
3. Prefer narrow smoke tests before broad refactors.
4. Re-run the broader UI slice if common plumbing changed.

## Validation Commands

- `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui/test_main_window_sync.py -q`
- `/home/administrator/.local/bin/poetry run pytest -s tests/unit/ui -q`

## Recordkeeping

After meaningful progress, update:

- `docs/workflows/COVERAGE_GAPS.md`
- `docs/current/BUG_TRIAGE.md`
- `docs/current/STATUS_REPORT.md`
- `docs/history/SESSION_LOG.md`
- `.agents/runbooks/active-queue.md`
