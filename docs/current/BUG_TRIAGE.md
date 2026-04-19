# XBrainLab Bug Triage

This document is the live intake structure for stabilization work on the PyQt application.

It exists to prevent bug fixing from turning into unsorted chaos.

## Triage Principles

- describe the user-visible problem first
- separate reproduction from speculation
- record impact before discussing solutions
- classify whether the issue is UI-only, workflow-level, or structural
- prefer a narrow failing test or observable signal whenever possible

## Priority Scale

### P0

App cannot launch, data can be corrupted, or a core workflow is blocked for most users.

### P1

A major panel or dialog is unreliable, misleading, or functionally broken.

### P2

A workflow is degraded but has a workaround, or the issue is localized and non-destructive.

### P3

Low-impact polish issue, non-critical layout inconsistency, or maintenance debt without an urgent user-facing failure.

## Issue Template

Use this template for every newly confirmed issue:

```md
## [BUG-XXX] Short title

- Priority:
- Area:
- Type:
- Status:
- Source:

### Symptom

### Reproduction

### Expected

### Actual

### Impact

### Suspected scope

### Evidence

### Test coverage

### Notes
```

## Classification

### Area

- Startup
- Dataset
- Preprocess
- Training
- Evaluation
- Visualization
- Agent
- Shared UI
- Backend integration
- Test infrastructure

### Type

- Crash
- Incorrect state
- Broken interaction
- Data sync issue
- Rendering/layout
- Performance
- Architecture/coupling
- Missing observability

### Status

- New
- Confirmed
- In progress
- Blocked
- Fixed
- Needs verification

### Source

- User report
- Manual exploration
- Test failure
- Runtime log
- Code review

## Initial Queue

This queue will be filled as takeover work continues.

### Confirmed environment-level notes

#### [BUG-ENV-001] Visualization-related tests are unstable in headless mode

- Priority: P2
- Area: Visualization
- Type: Test infrastructure
- Status: Confirmed
- Source: Test failure/skips

### Symptom

Some visualization and main-window tests are intentionally skipped in headless runs because VTK/Qt interaction is unstable.

### Reproduction

Run:

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/ui -q
```

### Expected

Visualization-related tests should either run reliably or be explicitly isolated with known limitations.

### Actual

The suite currently passes with `15 skipped`, including skips tied to VTK/Qt behavior in headless environments.

### Impact

This limits confidence for visualization-heavy changes and means layout/rendering regressions may escape the normal fast suite.

### Suspected scope

- `tests/unit/ui/test_visualization.py`
- `tests/unit/ui/test_visualization_panel_redesign.py`
- `tests/unit/ui/test_main_window.py`
- visualization widgets and VTK/PyVista integration

### Evidence

Observed locally in WSL2 on `2026-04-18`: `718 passed, 15 skipped`.

### Test coverage

Behavioral coverage exists, but full rendering confidence does not.

### Notes

This is not a release blocker by itself, but it is a standing risk area for future fixes.

#### [BUG-ENV-002] Baseline screenshot capture currently produces an all-black image

- Priority: P1
- Area: Test infrastructure
- Type: Missing observability
- Status: Fixed
- Source: Manual exploration

### Symptom

The current baseline capture helper successfully writes an image file, but the resulting screenshot is effectively all black and therefore not useful for UI review.

### Reproduction

Run:

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
```

Then inspect:

```text
artifacts/ui/main-window-initial.png
```

### Expected

The saved screenshot should show the XBrainLab main window shell clearly enough to assess layout structure.

### Actual

The image file is created, but the captured content is black.

### Impact

This blocks trustworthy visual baseline capture and weakens our ability to review UI layout changes asynchronously.

### Suspected scope

- `scripts/dev/capture_ui_baseline.py`
- `xvfb-run` screenshot timing or window targeting
- display/render synchronization under headless capture

### Evidence

Observed locally on `2026-04-18` after generating `artifacts/ui/main-window-initial.png`.

Repaired and re-verified on `2026-04-19` with:

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run python scripts/dev/capture_ui_baseline.py
```

### Test coverage

- `tests/unit/scripts/test_capture_ui_baseline.py`
- runtime validation of `artifacts/ui/main-window-initial.png`

### Notes

The helper now captures the rendered Qt main window directly, which makes the baseline artifact usable again. The remaining follow-up is expanding baseline coverage beyond the initial shell capture.

#### [BUG-ENV-003] Default pytest capture fails in the current `/mnt/d` Codex workspace

- Priority: P1
- Area: Test infrastructure
- Type: Broken interaction
- Status: Confirmed
- Source: Manual exploration

### Symptom

Running `pytest` with its default capture mode in the current `/mnt/d/repos/XBrainLab` Codex workspace fails during teardown with `FileNotFoundError` inside `_pytest/capture.py`.

### Reproduction

Run:

```bash
/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q
```

### Expected

The test should complete normally under the default project pytest settings.

### Actual

Pytest reports `no tests ran` and then fails while unconfiguring global capture:

```text
FileNotFoundError: [Errno 2] No such file or directory
```

The same targeted slices succeed when re-run with `-s`.

### Impact

This makes the default fast validation commands unreliable for unattended local work in the current workspace and weakens confidence in automation loops that assume normal pytest capture.

### Suspected scope

- current `/mnt/d/repos/XBrainLab` Codex desktop workspace
- `pytest` default capture teardown
- local temp-file or mount-path interaction under WSL/Codex local execution

### Evidence

Observed locally on `2026-04-19`:

- failing command:
  `/home/administrator/.local/bin/poetry run pytest tests/unit/backend/training/test_option.py -q`
- passing workaround:
  `/home/administrator/.local/bin/poetry run pytest -s tests/unit/backend/training/test_option.py -q`

### Test coverage

Coverage exists for the targeted slices themselves, but the default capture-based command path is currently not trustworthy in this workspace.

### Notes

Treat `-s` as the temporary local validation workaround until this is repaired or explained.

#### [BUG-AGENT-001] AI assistant local initialization fails when `accelerate` is unavailable

- Priority: P1
- Area: Agent
- Type: Broken interaction
- Status: Confirmed
- Source: Runtime log

### Symptom

Opening the AI assistant can expose the dock, but the backend initialization fails with a local-model load error when `accelerate` is not installed in the current environment.

### Reproduction

Run:

```bash
xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q
```

The `TestAIAssistantDock.test_toggle_ai_dock` path triggers first-open initialization and emits the failure.

### Expected

Opening the AI assistant should either initialize successfully or fail gracefully with a clear, front-loaded dependency check before the dock presents itself as usable.

### Actual

The dock toggle path reaches local-model startup and logs:

```text
Model Load Error: ... requires `accelerate`
```

while the overall UI integration slice still passes.

### Impact

The AI assistant can look available in the shell while the underlying agent backend is unusable, which makes the panel misleading and fragile for both manual use and automated baseline checks.

### Suspected scope

- `XBrainLab/ui/components/agent_manager.py`
- `XBrainLab/ui/dialogs/model_settings_dialog.py`
- `XBrainLab/llm/core/backends/local.py`
- local dependency/readiness checks for the AI assistant stack

### Evidence

Observed locally on `2026-04-19` during:

- `xvfb-run -a /home/administrator/.local/bin/poetry run pytest -s tests/integration/ui/test_e2e_qtbot.py -q`

The slice finished with `20 passed`, but the log also included:

```text
ValueError: ... requires `accelerate`
```

### Test coverage

- `tests/integration/ui/test_e2e_qtbot.py`

### Notes

This is now a confirmed AI-shell/runtime issue. The user has also explicitly approved intentional redesign of the AI assistant panel, so the eventual fix is allowed to include product-level UI changes instead of being limited to a narrow patch.

Additional triage finding on `2026-04-19`:

- `pyproject.toml` already declares `accelerate`, but only inside the optional Poetry `llm` group
- that means the current failure is likely a mismatch between the active local environment and the UI's assumption that local-model startup is ready
- the likely fix surface is therefore not just dependency installation; it also includes preflight checks and clearer fallback behavior before the AI dock presents local inference as usable

#### [BUG-DATASET-001] Sequence label import assumed numeric-only label codes

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### Symptom

Importing sequence-style labels from CSV/TSV could fail when the label values were categorical strings rather than integers.

### Reproduction

Before the fix, a sequence label flow like this would fail:

```python
loader.label_list = ["left", "right"]
loader.create_event({"left": "Left", "right": "Right"})
```

The dialog path also attempted `int(code_text)` when reading mapping rows.

### Expected

String or categorical sequence labels should stay usable through the mapping dialog and be converted into stable integer event IDs when applied to MNE events.

### Actual

The UI and backend both assumed numeric label codes, causing `ValueError` or preventing mapping extraction.

### Impact

This could make external label import appear dataset-specific even when the underlying issue was simply a categorical label format.

### Suspected scope

- `XBrainLab/ui/dialogs/dataset/import_label_dialog.py`
- `XBrainLab/backend/load_data/event_loader.py`
- `XBrainLab/backend/services/label_import_service.py`

### Evidence

Observed locally on `2026-04-18`; `EventLoader.create_event()` raised `ValueError: invalid literal for int() with base 10: 'left'` for string sequence labels before the fix.

### Test coverage

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/backend/load_data/test_event_loader_strict.py`
- `tests/unit/ui/test_ui_misc.py`

### Notes

The repaired path now supports categorical string labels and preserves quoted numeric strings such as `"769"` as original event codes.

#### [BUG-DATASET-002] Label import keyed files by basename only

- Priority: P1
- Area: Dataset
- Type: Data sync issue
- Status: Fixed
- Source: Code review

### Symptom

Importing two label files with the same filename from different folders could silently drop one of them before the mapping step.

### Reproduction

Before the fix, selecting both of these in the label import dialog would treat the second file as a duplicate:

```text
/tmp/sub01/labels.txt
/tmp/sub02/labels.txt
```

### Expected

Label files should be tracked by their full path so same-named files from different folders can coexist and be mapped correctly.

### Actual

`ImportLabelDialog` used `os.path.basename(path)` as the storage key, so only one `labels.txt` entry could survive.

### Impact

This could break batch label import for perfectly normal dataset layouts where each subject/session folder contains a label file with the same name.

### Suspected scope

- `XBrainLab/ui/dialogs/dataset/import_label_dialog.py`
- `XBrainLab/ui/dialogs/dataset/label_mapping_dialog.py`

### Evidence

Confirmed locally on `2026-04-18` by reviewing the dialog code path and adding a regression test for same-basename files from different directories.

### Test coverage

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/ui/test_ui_misc.py`

### Notes

The dialog now keys files by full path and exposes that path via item tooltip without changing layout structure.

#### [BUG-DATASET-003] Event filter remembered stale selections across unrelated datasets

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### Symptom

The event filter dialog could open with every event unchecked when the last saved selection came from a different dataset with different event names.

### Reproduction

1. Save a previous filter selection such as `["Left"]`.
2. Open the dialog for a dataset whose available events are `["769", "770"]`.

### Expected

If the saved history does not overlap the current dataset at all, the dialog should default to all events checked.

### Actual

Because the history was non-empty, every current event could render unchecked, making synchronization fail unless the user noticed and reselected events manually.

### Impact

This made label import look broken or dataset-specific even though the issue was a stale UI memory artifact.

### Suspected scope

- `XBrainLab/ui/dialogs/dataset/event_filter_dialog.py`
- dataset label import flow that depends on selected event names

### Evidence

Confirmed locally on `2026-04-18` through dialog code review and regression tests covering stale saved selections plus empty-selection handling.

### Test coverage

- `tests/unit/ui/dataset/test_import_label.py`
- `tests/unit/ui/test_ui_misc.py`

### Notes

The dialog now falls back to all checked when saved history has no overlap and refuses to accept an empty keep-list.

#### [BUG-DATASET-004] Batch label import inferred batch mode from only the first label file

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### Symptom

Batch label import used the first loaded label file to decide whether the whole import was timestamp-mode or sequence-mode and what event-count hint to use.

### Reproduction

Before the fix:

- mixed timestamp and sequence label batches could be misclassified by whichever file appeared first
- inconsistent sequence-label lengths could still drive smart-filter suggestions from the first file only

### Expected

Mode detection and smart-filter hints should be derived from the whole imported label set, not one arbitrary file.

### Actual

`DatasetActionHandler.import_label()` used `next(iter(label_map.values()))` to classify the whole batch.

### Impact

This made multi-file label import brittle and could produce misleading filtering suggestions or incorrect mode handling for real datasets.

### Suspected scope

- `XBrainLab/ui/panels/dataset/actions.py`

### Evidence

Confirmed locally on `2026-04-18` during import workflow review; repaired with tests covering mixed-mode rejection and inconsistent sequence-length batches.

### Test coverage

- `tests/unit/ui/test_ui_misc.py`

### Notes

The handler now analyzes the whole label map, rejects mixed mode explicitly, and only provides a target-count hint when the batch is internally consistent.

#### [BUG-DATASET-005] Raw-data factory rejected `.fif.gz` and epoch-style `.fif` imports

- Priority: P1
- Area: Dataset
- Type: Broken interaction
- Status: Fixed
- Source: Code review

### Symptom

Some valid MNE files could fail import because `.fif.gz` was treated as `.gz`, and `.fif` imports assumed raw-only files.

### Reproduction

- `RawDataLoaderFactory.get_loader("subject01-epo.fif.gz")`
- `load_fif_file("epochs.fif")` where raw loading fails but epoch loading would succeed

### Expected

Compressed `.fif.gz` files should resolve to the FIF loader, and `.fif` imports should try an epochs fallback when the raw reader cannot load the file.

### Actual

The factory used `os.path.splitext()` on the last suffix only, and the FIF loader had no epoch fallback.

### Impact

This could make valid MNE datasets look unsupported or corrupted depending on how they were saved.

### Suspected scope

- `XBrainLab/backend/load_data/factory.py`
- `XBrainLab/backend/load_data/raw_data_loader.py`

### Evidence

Confirmed locally on `2026-04-18` by code review and repaired with regression coverage for `.fif.gz` lookup plus `.fif` epochs fallback.

### Test coverage

- `tests/unit/backend/load_data/test_factory.py`
- `tests/unit/backend/load_data/test_raw_data_loader_coverage.py`
- `tests/unit/backend/load_data/test_loaders.py`

### Notes

The factory now selects the longest registered suffix match, and FIF loading now falls back to `mne.read_epochs()` before declaring corruption.

#### [BUG-DATASET-006] Event-filter suggestions depended on the first raw file only

- Priority: P2
- Area: Dataset
- Type: Incorrect state
- Status: Fixed
- Source: Code review

### Symptom

When importing labels across multiple raw files, the default event-filter suggestion could be biased by only the first file's event map.

### Reproduction

Open label import for multiple raw files whose event-name maps are not identical, then rely on the suggested selection in the event filter dialog.

### Expected

Suggestions should reflect all target raw files that will be synchronized, not just the first one.

### Actual

`DatasetActionHandler._filter_events_for_import()` previously called smart-filter suggestion on `raw_files[0]` only.

### Impact

Suggested default selections could be misleading, making batch import feel unreliable even when a correct cross-file selection existed.

### Suspected scope

- `XBrainLab/ui/panels/dataset/actions.py`

### Evidence

Confirmed locally on `2026-04-18` during workflow review and repaired with regression coverage for multi-file suggestion aggregation.

### Test coverage

- `tests/unit/ui/test_ui_misc.py`

### Notes

The dialog now aggregates suggested event names from all candidate raw files before pre-selecting them.

#### [BUG-TRAINING-001] CUDA-capable detection could route training onto an unusable GPU

- Priority: P1
- Area: Training
- Type: Crash
- Status: Fixed
- Source: Test failure

### Symptom

Training could fail immediately on machines where `torch.cuda.is_available()` returned `True` but the installed PyTorch build could not actually execute kernels on the detected GPU.

### Reproduction

- Run `tests/integration/pipeline/test_pipeline_integration.py` on this WSL host.
- Or construct `TrainingOption(use_cpu=False, gpu_idx=0, ...)` and start training on the current RTX 5070 Ti environment.

### Expected

If the requested CUDA device cannot actually execute work, training should degrade safely to CPU instead of crashing mid-run.

### Actual

The training path trusted availability checks alone, then crashed with `CUDA error: no kernel image is available for execution on the device`.

### Impact

Training was effectively blocked on this machine whenever GPU mode was selected implicitly, even for otherwise valid workflows.

### Suspected scope

- `XBrainLab/backend/training/option.py`
- `XBrainLab/backend/training/training_plan.py`
- training flows that derive device choice from `torch.cuda.is_available()`

### Evidence

Confirmed locally on `2026-04-19` by a failing `tests/integration/pipeline/test_pipeline_integration.py` run and by a direct `TrainingOption` smoke check on the current WSL host.

### Test coverage

- `tests/unit/backend/training/test_option.py`
- `tests/integration/pipeline/test_pipeline_integration.py`

### Notes

`TrainingOption` now probes the requested CUDA device and falls back to CPU with a warning when the device is present but unusable.

#### [BUG-ENV-003] Two real-data integration tests pointed at a non-existent fixture directory

- Priority: P2
- Area: Test infrastructure
- Type: Missing observability
- Status: Fixed
- Source: Test failure

### Symptom

Some integration tests intended to exercise real EEG files were silently skipped because they looked under `tests/integration/data/` even though the repo stores the real fixtures under `tests/data/`.

### Reproduction

- Run `tests/integration/pipeline/test_real_data_pipeline.py`
- Run `tests/integration/io/test_io_integration.py`

### Expected

Both tests should consume the checked-in real GDF fixtures and provide real-data signal about import and pipeline behavior.

### Actual

Both tests skipped with "test data not found" until the path was corrected.

### Impact

This reduced real-data coverage and made the stabilization loop look healthier than it actually was because two useful checks were never executing.

### Suspected scope

- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`

### Evidence

Confirmed locally on `2026-04-19` when both tests skipped before the fix and passed once the fixture path was updated to `tests/data/`.

### Test coverage

- `tests/integration/pipeline/test_real_data_pipeline.py`
- `tests/integration/io/test_io_integration.py`

### Notes

The repo already carries three checked-in real GDF fixtures plus label files, totaling roughly 98 MB, which is still small enough to keep as a practical real-data baseline.

#### [BUG-DATASET-007] Real GDF imports still rely on duplicate EEG channel names being auto-renamed by MNE

- Priority: P2
- Area: Dataset
- Type: Incorrect state
- Status: Confirmed
- Source: Runtime log

### Symptom

Importing the checked-in BCI Competition GDF fixtures emits MNE warnings because many channels arrive with the same generic name (`EEG`), forcing MNE to auto-rename them to generated names such as `EEG-0`, `EEG-1`, and so on.

### Reproduction

Run any real-data import flow using `tests/data/A01T.gdf`, for example:

```bash
/home/administrator/.local/bin/poetry run pytest tests/integration/io/test_io_integration.py -q
```

### Expected

Real imports should either normalize channel names intentionally or surface the duplicate-name condition in a way that downstream channel selection, montage logic, and diagnostics can rely on.

### Actual

The import succeeds, but MNE emits duplicate-name warnings and silently generates replacement names.

### Impact

This is not an immediate crash, but it can distort cross-file channel matching and make later workflow failures around selection, montage, or mismatch diagnostics harder to reason about.

### Suspected scope

- `XBrainLab/backend/load_data/raw_data_loader.py`
- `XBrainLab/backend/load_data/raw.py`
- channel-name-sensitive preprocess and dataset workflows

### Evidence

Observed locally on `2026-04-19` across GDF real-data imports and real-data integration tests while building the new multi-extension fixture baseline.

### Test coverage

- `tests/integration/io/test_io_integration.py`
- `tests/integration/controller/test_preprocess_controller.py`
- `tests/integration/pipeline/test_all_real_tools.py`

### Notes

This is a good next target because it shows up in real workflows repeatedly and may explain some dataset-specific behavior that is otherwise easy to misattribute.
