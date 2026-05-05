# XBrainLab Product Completion Continuation - 2026-05-06 UI Table / Eval Gate

Use this as the next-run handoff for the active product-completion goal. Do not
mark Goal 1 product-complete while the blockers below remain.

## Current Repo / Branch

- Repo: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- Branch: `codex/stabilization-autopilot`
- Do not push.
- Do not touch / stage / revert `.vscode/settings.json`, root `settings.json`, or the user-added
  `.agents/skills/*` changes unless the user explicitly asks.

Expected dirty files after this handoff:

```text
 M .agents/skills/README.md
 M .vscode/settings.json
 M settings.json
?? .agents/skills/clean-code-reviewer/
?? .agents/skills/data-interpretation-reviewer/
?? .agents/skills/mcp-adapter-reviewer/
?? .agents/skills/performance-resource-reviewer/
?? .agents/skills/release-packaging-reviewer/
?? .agents/skills/security-privacy-reviewer/
?? .agents/skills/thesis-evidence-reviewer/
?? .agents/skills/ui-product-reviewer/
```

## Latest Validated Commits

```text
435d9a9 llm: clean up model downloader lifecycle
51a6149 ui: clean up split preview worker
9816f85 docs: refresh handoff after split context query
4ddfa92 ui: source split dialog context from service
c21d7eb ui: export saliency from service trainers
338a763 docs: refresh handoff after training history query
e067e73 ui: render training history from state query
f2ccf95 ui: render visualization from service payload
a00a5d5 ui: render evaluation from service payload
c6c7e5b ui: query channel selection data
0cea91e docs: refresh handoff after label target cleanup
4f96005 ui: select label targets from dataset table
876c154 docs: refresh handoff after dataset render query
3f63592 ui: render dataset table from state query
3766764 docs: refresh handoff after aggregate info query
272dc5e ui: keep aggregate info on query truth
5e9e351 docs: refresh handoff after preprocess render query
feb9f88 ui: render preprocess panel from state query
29137da docs: refresh handoff after preprocess query guard
ebbdcfd ui: query epoching data through command spine
bb005ab ui: render preprocess sidebar from capabilities
7ab9501 ui: load training settings from state snapshot
7978c54 docs: refresh handoff after query-truth slices
d0a66b2 ui: use state query for smart parse files
d2e5b73 ui: use state query for montage channels
7b3c3e7 ui: use command query for saliency settings
f0ce929 docs: clarify local eval gate policy
c370929 docs: refresh handoff after saliency export gate
9327a4d ui: gate saliency export with query result
af9048f docs: refresh handoff after visualization query gate
25022fe ui: gate visualization display with query result
f845829 docs: refresh handoff after evaluation query gate
699e829 ui: gate evaluation display with query result
c4dc092 docs: refresh handoff after dataset sidebar audit
0c3de01 ui: render dataset sidebar from capabilities
b0b7b09 docs: refresh handoff after readiness echo guard
e309996 test: guard training readiness controller echoes
a6a6ba1 docs: refresh handoff after epoch gate audit
a7b7222 ui: gate epoching with create capability
343f8f9 docs: refresh handoff after readiness guard
d5388e7 test: guard capability-gated controller readiness
57b5d9c docs: refresh handoff after train gate audit
82576f5 ui: prefer train capability over stale controller
7a59e39 docs: refresh handoff after split audit
bb57beb ui: use backend truth for split replacement
```

## What Was Closed In This Slice

- Data Interpretation wizard selector visible text:
  - label carrier selectors show user-facing labels such as `Trial type` / `Onset`.
  - backend recipe choices still preserve raw values such as `trial_type`.
- Review Summary contrast:
  - alternate row color lowered to `#232323`, avoiding harsh black/white striping.
- Label/Event review table readability:
  - label-carrier `Format` column widened so `BIDS events` remains visible in product-width dialog.
- Dataset loaded table artifact:
  - `artifacts/ui/data-interpretation-applied.png` shows loaded rows filling to the sidebar.
  - `Labels (4)` is muted text, not success-green.
- Automated geometry guard:
  - `table_state()` now records `widget_width`, `panel_width`, `table_right_x`,
    `right_boundary_x`, and `right_gap_to_boundary`.
  - `build_table_geometry_review()` now fails if a table fills only its own viewport but leaves a
    visible gap before the content boundary.
  - Latest `artifacts/ui/data-interpretation-replay.json` records
    `widget_width=1020`, `table_right_x=1020`, `right_boundary_x=1020`,
    `right_gap_to_boundary=0` for the 1280px loaded Dataset capture.
- Visualization sidebar `Set Montage` missing-result handling:
  - no longer silently returns when `execute_application_command()` unexpectedly returns `None`.
  - mock / legacy contexts use `run_legacy_controller_fallback()`; real `Study` contexts refuse
    controller fallback.
- Dataset file import boundary:
  - if `scan_source` capability exists but Data Interpretation command sequencing is unavailable,
    the UI shows `Interpretation unavailable`.
  - it does not fall through to `LoadDataCommand` or `DatasetController.import_files()`.
- Training model selection command truth:
  - service-success path now trusts `ConfigureTrainingCommand` and the selected model holder.
  - it no longer re-reads stale `TrainingController.get_model_holder()` before showing success.
  - architecture compliance now guards this controller echo pattern.
- Training split replacement command truth:
  - real `Study` path uses backend `generate_dataset` / `clear_datasets` capability truth to decide
    whether existing generated datasets / trainer must be cleared before a new split.
  - stale `TrainingController.has_datasets()` / `get_trainer()` no longer skips confirmation and
    `ClearDatasetsCommand`.
- Start Training command truth:
  - real command-capable path uses backend `train` capability truth to decide whether to dispatch
    `TrainCommand`.
  - stale `TrainingController.is_training()` no longer silently skips an enabled backend train
    command.
- Capability-gated readiness architecture guard:
  - `tests/architecture_compliance.py` now flags `controller.is_training()`,
    `controller.has_datasets()`, and `controller.get_trainer()` in command paths that already have
    backend capability truth.
  - Such reads must live in explicit `capability is None` legacy branches.
- Training readiness controller echo guard:
  - The same architecture guard now covers `validate_ready()`, `has_model()`, and
    `has_training_option()` controller reads.
  - `TrainingSidebar.check_ready_to_train()` uses an explicit service-capability branch versus
    no-capability legacy branch.
- Dataset sidebar capability-first render:
  - The architecture guard now also covers `DatasetController.is_locked()` and `has_data()` reads
    in capability-backed UI paths.
  - `DatasetSidebar.update_sidebar()` no longer reads stale lock/data controller state when backend
    command capabilities are present.
  - Those controller reads remain only in explicit no-capability legacy branches.
- Evaluation panel query display gate:
  - A real `Study` Evaluation panel now uses the readonly `EvaluateCommand` result as the display
    gate.
  - If ApplicationService reports evaluation blocked or unavailable, the panel clears to
    `No Data Available` instead of reading stale injected controller plans.
- Evaluation panel object-payload render source:
  - `EvaluateCommand(include_objects=True)` now returns UI-only plan objects, pooled evaluation
    results, and model summaries for service-backed rendering.
  - A real `Study` Evaluation panel uses that service payload for plan list, average metrics, and
    summary text before falling back to controller reads.
  - Automation / MCP `evaluate` schemas hide and reject `include_objects`, keeping external
    clients on the serializable query contract.
  - `.basedpyright/baseline.json` dropped by 3 suppressed optional-controller errors.
- Visualization panel query display gate:
  - A real `Study` Visualization panel now uses readonly `VisualizeCommand` results as the
    controls/render gate.
  - If ApplicationService reports visualization blocked or unavailable, the panel clears plan/run
    controls and shows a user-facing readiness message before reading injected controller trainers.
  - The basedpyright baseline dropped from 115 to 112 suppressed errors after replacing dynamic
    `show_error` calls with a typed helper.
- Visualization panel object-payload render source:
  - `VisualizeCommand(include_objects=True)` now returns UI-only trainer objects and averaged
    records for service-backed rendering.
  - A real `Study` Visualization panel uses that service payload for plan controls and average-run
    rendering before falling back to controller reads.
  - Automation / MCP `visualize` schemas hide and reject `include_objects`, keeping external
    clients on the serializable query contract.
  - `.basedpyright/baseline.json` dropped by 2 more suppressed errors.
- Saliency export query gate:
  - `Export Saliency` now checks readonly `SaliencyCommand` readiness before reading trainer lists
    or opening the export dialog.
  - If saliency output is unavailable, the sidebar shows `Export Saliency Blocked`.
- Saliency settings query defaults:
  - `Saliency Settings` now checks readonly `SaliencyCommand` summary diagnostics before opening
    the settings dialog.
  - `VisualizationController.get_saliency_params()` is only used through the mock / legacy query
    fallback helper when ApplicationService query result is unavailable.
- Montage channel query defaults:
  - `Set Montage` now checks `QueryStateCommand(query="state")` for `state.epoch.channel_names`
    before opening the montage picker.
  - `VisualizationController.get_channel_names()` is only used through the mock / legacy query
    fallback helper when ApplicationService query result is unavailable.
- Dataset smart-parse query defaults:
  - `Smart Parse Metadata` now checks `QueryStateCommand(query="state")` for `state.raw.files`
    before opening the parser dialog.
  - `DatasetController.get_filenames()` is only used through the mock / legacy query fallback
    helper when ApplicationService query result is unavailable.
- Training settings state snapshot defaults:
  - `Training Settings` now checks `QueryStateCommand(query="state")` for
    `state.training.training_option` before opening the settings dialog.
  - `TrainingController.get_training_option()` is only used in mock / legacy query fallback.
- Training history query render source:
  - `QueryStateCommand(query="training_history", include_objects=True)` now returns service-backed
    training history rows for table rendering and plot selection.
  - A real `Study` Training panel uses that payload before falling back to
    `TrainingController.get_formatted_history()`.
  - The query returns serializable row summaries by default and plan/record objects only for
    `include_objects=True`.
- Visualization export trainer render source:
  - `Export Saliency` still uses readonly `SaliencyCommand` as the export readiness gate.
  - When export is ready, it now opens the export dialog from
    `VisualizeCommand(view="summary", include_objects=True)` `trainer_objects`.
  - `panel.get_trainers()` / `VisualizationController.get_trainers()` remain only for
    query-unavailable mock / legacy fallback.
- Training split dialog context query:
  - `QueryStateCommand(query="dataset_generation_context", include_objects=True)` now returns the
    epoch data and current dataset generator needed by `DataSplittingDialog`.
  - A real `Study` Training sidebar passes that service-backed context into the dialog.
  - `TrainingController.get_epoch_data()` / `get_dataset_generator()` remain only for
    query-unavailable mock / legacy dialog fallback.
- Data Splitting preview worker cleanup:
  - `DataSplittingPreviewDialog.preview()` interrupts and short-joins the previous preview worker
    before starting a new `DatasetGenerator`.
  - `DataSplittingPreviewDialog.closeEvent()` stops the timer, interrupts the generator, and
    short-joins the worker before Qt close handling.
  - This is focused lifecycle coverage, not a long-running dataset-generation soak test.
- Local model downloader lifecycle cleanup:
  - `DownloadWorker.run()` now reaps the subprocess after terminal queue messages and closes the
    multiprocessing queue after the worker loop exits.
  - cancel uses bounded terminate / kill joins instead of an unbounded process join.
  - `ModelDownloader.shutdown()` cancels the worker, requests `QThread.quit()`, then bounded-waits
    for thread cleanup.
  - `ModelSettingsDialog.reject()` / `closeEvent()` now use that shutdown path while suppressing
    teardown cleanup popups.
  - This is focused lifecycle coverage, not a long-running local model soak or Windows desktop
    acceptance.
- Preprocess epoch command truth:
  - `open_epoching()` uses backend `create_epoch` capability as the authoritative UI gate.
  - An enabled `create_epoch` capability is no longer vetoed by the separate `preprocess`
    capability through `check_lock()` / `check_data_loaded()`.
  - Legacy controller lock/data checks remain only for no-capability mock / legacy contexts.
- Preprocess sidebar capability-first render:
  - `update_sidebar()` no longer reads stale `PreprocessController.get_preprocessed_data_list()`
    when `preprocess` / `create_epoch` capabilities are visible.
  - The architecture guard now flags `get_preprocessed_data_list()` in capability-backed UI paths.
- Epoching dialog query data source:
  - command-capable `open_epoching()` now gets preprocessed dialog data through
    `QueryStateCommand(query="data_lists", include_objects=True)`.
  - `PreprocessController.get_preprocessed_data_list()` remains only for no-capability mock /
    legacy dialog population.
- Preprocess panel state-query render:
  - `PreprocessPanel.update_panel()` and `update_plot_only()` now query
    `QueryStateCommand(query="data_lists", include_objects=True)` in real `Study` contexts.
  - The panel passes queried preprocessed / original objects into `PreprocessPlotter`, so history,
    preview controls, and plot refresh do not start from stale controller list reads.
  - `PreviewWidget.request_plot_update` routes through `PreprocessPanel.update_plot_only()` to keep
    user control changes on the same query-backed render source.
  - `.basedpyright/baseline.json` dropped by one suppressed error after touched Preprocess tests
    and panel typing were cleaned up.
- Aggregate info query-failure boundary:
  - real `Study` `InfoPanelService` keeps aggregate info on
    `QueryStateCommand(query="data_lists", include_objects=True)`.
  - if that query fails or raises, the service logs and returns an empty summary instead of falling
    back to dataset / preprocess controller list reads.
  - mock / legacy non-`Study` contexts keep the controller-list compatibility fallback.
- Dataset table state-query render:
  - real `Study` `DatasetPanel.update_panel()` uses
    `QueryStateCommand(query="data_lists", include_objects=True)` for loaded table rows.
  - `DatasetController.get_loaded_data_list()` remains only for no-ApplicationService mock /
    legacy rendering.
  - `.basedpyright/baseline.json` dropped by one more suppressed error after touched Dataset panel
    typing was cleaned up.
- Label import target selection:
  - post-load `Add Labels to Loaded Data` now resolves selected/all-row targets from the Dataset
    table's column-0 `Qt.UserRole` object before opening `ImportLabelDialog`.
  - `DatasetController.get_loaded_data_list()` remains only as a mock / legacy fallback when table
    row objects are unavailable.
- Channel Selection dialog query source:
  - real command-capable `DatasetSidebar.open_channel_selection()` now queries
    `QueryStateCommand(query="data_lists", include_objects=True)` before opening
    `ChannelSelectionDialog`.
  - `DatasetController.get_loaded_data_list()` remains only for no-capability mock / legacy dialog
    population.

## Validation Already Run

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_table_columns_fill_available_width \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_refits_table_after_loaded_rows_settle \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color \
  -q
# 23 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py
# exit 0

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
# exit 0; walkthrough status passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run mkdocs build --strict
poetry run python tests/architecture_compliance.py
# all passed; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_panel_event_bridges.py \
  -q
# 46 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  tests/unit/ui/dataset/test_panel.py \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 89 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 50 passed

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 23 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  tests/unit/ui/preprocess \
  -q
# 61 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
poetry run mkdocs build --strict
# all passed for a7b7222; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 24 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 50 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for e309996; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  tests/unit/ui/dataset/test_dataset_sidebar.py \
  -q
# 16 passed

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 25 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 0c3de01; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_panel_event_bridges.py \
  -q
# 22 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 699e829; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  -q
# 35 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 25022fe; basedpyright baseline refreshed from 115 to 112;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 38 passed

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 9327a4d; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 39 passed for 7b3c3e7

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 40 passed for d2e5b73

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  tests/unit/ui/dataset/test_panel.py::test_dataset_panel_smart_parse \
  -q
# 67 passed for d0a66b2

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 28 passed for d0a66b2

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for the 7b3c3e7 / d2e5b73 / d0a66b2 UI query-truth slices;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/training/test_training_panel.py \
  tests/unit/ui/training/test_training_setting.py \
  -q
# 60 passed for 7ab9501

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar \
  -q
# 23 passed for ebbdcfd

poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q
# 29 passed for ebbdcfd

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for bb005ab / ebbdcfd; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess -q
# 41 passed for feb9f88

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for feb9f88; basedpyright baseline decreased by 1;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/components/test_info_panel_service.py \
  tests/unit/ui/components/test_info_panel.py \
  -q
# 11 passed for 272dc5e

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 272dc5e; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dataset/test_panel.py \
  -q
# 14 passed for 3f63592

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 3f63592; basedpyright baseline decreased by 1;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler \
  -q
# 67 passed for 4f96005

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 4f96005; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar \
  -q
# 11 passed for c6c7e5b

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for c6c7e5b; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 112 passed for a00a5d5

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  -q
# 9 passed for a00a5d5

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for a00a5d5

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for a00a5d5

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for a00a5d5; basedpyright baseline decreased by 3;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 114 passed for f2ccf95

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 28 passed for f2ccf95

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for f2ccf95

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for f2ccf95

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for f2ccf95; basedpyright baseline decreased by 2;
# mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 114 passed for e067e73

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/training/test_training_panel.py \
  -q
# 18 passed for e067e73

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for e067e73

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for e067e73

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for e067e73; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/visualization/test_control_sidebar.py \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_coverage.py \
  -q
# 42 passed for c21d7eb

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_state_service.py \
  tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar \
  tests/unit/ui/test_data_splitting.py \
  tests/unit/ui/dialogs/test_data_splitting.py \
  -q
# 114 passed for 4ddfa92

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q
# 114 passed for 4ddfa92

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for c21d7eb / 4ddfa92

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for c21d7eb / 4ddfa92

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for c21d7eb and 4ddfa92; mkdocs still prints the existing Material advisory

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_data_splitting.py \
  tests/unit/ui/dialogs/test_data_splitting.py \
  tests/unit/ui/dataset/test_data_splitting.py \
  tests/unit/ui/test_panels_and_dialogs.py \
  -q
# 105 passed for 51a6149

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/llm/tools/test_application_surface.py \
  tests/integration/agent/test_tool_call_eval.py \
  -q
# 20 passed for 51a6149

poetry run pytest --capture=sys tests/integration/backend -q
# 7 passed for 51a6149

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 51a6149; mkdocs still prints the existing Material advisory

poetry run pytest --capture=sys \
  tests/unit/llm/core/test_downloader.py \
  tests/unit/llm/test_coverage_boost.py::TestDownloadWorkerRun \
  tests/unit/llm/test_misc_coverage.py::TestModelDownloaderCoverage \
  tests/unit/test_llm_backend.py::TestDownloader \
  -q
# 27 passed for 435d9a9

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/test_model_settings.py \
  tests/unit/ui/test_local_bootstrap_validation.py \
  -q
# 25 passed for 435d9a9

git diff --check
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
# all passed for 435d9a9; mkdocs still prints the existing Material advisory
```

No local LLM eval was run for these UI / architecture / lifecycle guard slices.

## Tool-Call Eval Gate Policy

Do not run full primary/fallback x3 local eval for routine changes.

- Fast dev gate:
  - deterministic eval
  - changed / failed cases only
  - repeat `1`
  - no fallback model
- Candidate gate:
  - primary model only
  - affected case families
  - repeat `1` or `2`
- Release / thesis gate:
  - deterministic full suite
  - primary full suite x3
  - fallback full suite x3
  - dashboard refresh
  - record disk / cache / `nvidia-smi` VRAM used/free, latency, and resource pressure

RTX 5070 Ti 16GB has already shown near-full VRAM pressure on fallback x3. If VRAM is nearly full,
do not start a full fallback x3 run. Use deterministic changed cases or primary subset unless the
work is explicitly a release / thesis evidence gate.

## Still Cannot Claim Product Complete

- UI refresh remains partially mixed:
  - command-result coordinator baseline exists, but observer/manual/tab-switch/event-specific
    refreshes still remain.
- Product runtime controller fallback is still an audit target:
  - controller fallback must stay explicit mock / unit-test / legacy-only, not silent product
    runtime mutation.
- Data Interpretation is stronger but not final:
  - embedded label editor, raw trigger selector, complex GDF/MAT anchor reconciliation, XDF/LSL full
    parser, full real-data manual certification, and recipe diff/review UX remain.
- Human desktop acceptance remains open:
  - Windows launcher click-through, dual monitor / DPI, and long real local-model desktop session
    are not verified.
- Agent / MCP release depth remains open:
  - long autonomous ChatPanel workflow, UI-routing render, full recovery behavior, HTTP MCP
    transport, and long-running MCP job progress/cancel/recovery remain.
- Tool-call benchmark evidence must not be used as UI / launcher / import wizard product evidence.

## Suggested Next Slices

1. Continue `UI Command Refresh Coordinator + Controller Fallback Audit`.
   - Audit remaining `result is None` branches and controller read echoes.
   - Keep product runtime mutations on ApplicationService, with controller fallback only in explicit
     mock / legacy branches.
   - Continue routing post-command refresh through the coordinator.
2. Continue Data Interpretation wizard maturity.
   - Add a small recipe diff/review UX slice or a safer label-carrier edit slice with screenshot
     artifact.
3. Only after product/UI/backend path stabilizes, refresh affected tool-call eval cases using the
   fast/candidate gate. Reserve full primary/fallback x3 for release/thesis evidence.
