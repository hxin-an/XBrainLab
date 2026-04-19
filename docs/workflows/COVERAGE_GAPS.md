# XBrainLab Coverage Gaps

This document summarizes where the current test suite gives us confidence and where important blind spots remain.

It is written for stabilization planning, not for reporting total coverage numbers.

## Key Observation

The project already has broad UI test volume, but confidence is uneven.

In practice:

- many dialogs and panels have unit coverage
- shared refresh logic has some integration coverage
- visualization remains less trustworthy in headless mode
- modal workflow realism is still limited because dialogs are widely mocked

## Current Stronger Areas

These areas appear to have meaningful existing coverage:

- dataset label-import related logic
- label mapping and event filtering acceptance paths
- smart parser dialog flows
- epoching dialog acceptance path
- training setting and model selection dialogs
- montage picker and saliency settings dialogs
- panel structure and sidebar behaviors
- UI refresh integration tests
- shared event-bridge propagation into downstream panels

Representative files:

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/integration/ui/test_dialog_acceptance.py`
- `tests/unit/ui/dataset/test_smart_parser.py`
- `tests/unit/ui/training/test_training_setting.py`
- `tests/unit/ui/training/test_model_selection.py`
- `tests/unit/ui/test_main_window_sync.py`
- `tests/unit/ui/test_panel_event_bridges.py`
- `tests/unit/ui/dialogs/test_montage_picker.py`
- `tests/unit/ui/dialogs/test_saliency_setting.py`
- `tests/integration/ui/test_ui_refresh.py`

## Important Blind Spots

### 1. Real modal behavior

Why it matters:

- `QDialog.exec` is globally patched in the unit harness
- this reduces hanging, but also reduces confidence in true modal interaction behavior

Risk:

- acceptance/cancel paths may look correct in tests while real dialog interaction still misbehaves

Current state:

- the four prep-gate priority dialogs now have button-driven headless acceptance coverage in `tests/integration/ui/test_dialog_acceptance.py`
- the remaining realism gap is mostly around dialogs that still depend on `exec()`-heavy entry flows or full manual desktop behavior

### 2. Visual correctness

Why it matters:

- current test strategy is stronger on behavior than on layout
- the first screenshot baseline attempt currently produces black images

Risk:

- clipping, overlap, unreadable labels, or empty panes may slip through

### 3. Visualization runtime confidence

Why it matters:

- visualization is already known to be fragile in headless mode
- some tests are skipped because of VTK/Qt instability

Risk:

- rendering regressions are easier to miss than logic regressions

### 4. Cross-workflow state propagation

Why it matters:

- training completion affects Training, Evaluation, and Visualization
- dataset and preprocess changes affect readiness and downstream controls

Risk:

- local tests can pass while downstream panels fail to refresh coherently

Current state:

- `tests/unit/ui/test_panel_event_bridges.py` now covers the highest-value propagation paths from dataset/training events into downstream panels
- the remaining gap is broader workflow coherence across multi-step user actions, not the basic observer-bridge wiring itself

## Dialog Review Status

### Higher confidence dialogs

- `smart_parser_dialog.py`
- `import_label_dialog.py`
- `model_selection_dialog.py`
- `training_setting_dialog.py`
- `montage_picker_dialog.py`
- `saliency_setting_dialog.py`

These appear to have at least some targeted tests, though not necessarily live modal validation.

### Still deserving explicit review

- `export_saliency_dialog.py`
- `data_splitting_dialog.py`
- `manual_split_dialog.py`

These matter because they mutate or gate important workflow state.

## Most Valuable Next Test Investments

1. one real workflow validation pass per major panel
2. improved screenshot capture that produces usable UI evidence
3. runtime-signal triage for AI shell initialization and pytest capture teardown
4. focused end-to-end checks for multi-step training/evaluation/visualization coherence

## Related Docs

- `docs/history/BACKLOG.md`
- `docs/current/BUG_TRIAGE.md`
- `docs/workflows/DIALOG_MATRIX.md`
- `docs/workflows/TESTING_STRATEGY.md`
