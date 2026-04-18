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
- smart parser dialog flows
- training setting and model selection dialogs
- montage picker and saliency settings dialogs
- panel structure and sidebar behaviors
- UI refresh integration tests

Representative files:

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/ui/dataset/test_smart_parser.py`
- `tests/unit/ui/training/test_training_setting.py`
- `tests/unit/ui/training/test_model_selection.py`
- `tests/unit/ui/test_main_window_sync.py`
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

- `label_mapping_dialog.py`
- `event_filter_dialog.py`
- `epoching_dialog.py`
- `export_saliency_dialog.py`
- `data_splitting_dialog.py`
- `manual_split_dialog.py`

These matter because they mutate or gate important workflow state.

## Most Valuable Next Test Investments

1. refresh and navigation smoke tests around `MainWindow.switch_page()` and panel updates
2. one real workflow validation pass per major panel
3. improved screenshot capture that produces usable UI evidence
4. focused training-to-evaluation and training-to-visualization state propagation checks

## Related Docs

- `docs/BACKLOG.md`
- `docs/BUG_TRIAGE.md`
- `docs/DIALOG_MATRIX.md`
- `docs/TESTING_STRATEGY.md`
