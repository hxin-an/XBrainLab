---
name: xbrainlab-dialog-audit
description: Use when auditing high-risk XBrainLab dialog and modal workflows, especially when unit tests mock dialogs and real acceptance behavior needs runtime verification. Trigger for label mapping, event filter, epoching, training setting, or other modal-state-loss investigations.
---

# XBrainLab Dialog Audit

Use this skill for dialog-heavy workflow validation where mocked tests are not enough.

## Read First

1. `AGENTS.md`
2. `.agents/stack.md`
3. `.agents/runbooks/setup.md`
4. `.agents/runbooks/autopilot.md`
5. `.agents/runbooks/active-queue.md`
6. `docs/workflows/DIALOG_MATRIX.md`
7. `docs/workflows/COVERAGE_GAPS.md`
8. `docs/workflows/WORKFLOWS.md`
9. `docs/current/BUG_TRIAGE.md`
10. `docs/history/SESSION_LOG.md`

## Priority Dialogs

- `LabelMappingDialog`
- `EventFilterDialog`
- `EpochingDialog`
- `TrainingSettingDialog`

## Working Pattern

1. Identify the user entrypoint that opens the dialog.
2. Inspect existing tests and note where modal behavior is mocked or bypassed.
3. Reproduce or simulate the narrowest realistic acceptance path.
4. Watch for state loss, wrong defaults, silent rejection, or downstream desynchronization.
5. Add focused regression coverage when practical.
6. Record what is still only partially verified.

## Recordkeeping

After meaningful progress, update:

- `docs/workflows/DIALOG_MATRIX.md`
- `docs/workflows/COVERAGE_GAPS.md`
- `docs/current/BUG_TRIAGE.md`
- `docs/current/STATUS_REPORT.md`
- `docs/history/SESSION_LOG.md`
- `.agents/runbooks/active-queue.md`
