# XBrainLab Worklog

最後更新：`2026-05-06`

## 這份文件的用途

這是流水帳式工作紀錄，用來保留「當天實際做過什麼」。

它和其他文件的分工如下：

| 文件 | 角色 |
| --- | --- |
| `current.md` | 現在真相。只寫目前狀態、blocker、下一步。 |
| `records/implementation_log.md` | 高層狀態快照。只收產品主線完成度、claim boundary、evidence 入口和下一手重點。 |
| `records/worklog.md` | 細節流水帳。記錄實作切片、TDD 紅燈、驗證命令、踩坑、臨時判斷和未整理細節。 |

`records/worklog.md` 可以比較細，但不應該取代 current state 或 architecture。

## 記錄規則

- 新紀錄插在該日期區塊最上方，最新在上。
- 每筆只寫一件事。
- 寫清楚結果，不只寫動作。
- 失敗嘗試也要記，因為它們常常是後面判斷可信度的關鍵。
- 每隔一段時間，把真正重要的產品狀態整理進 `records/implementation_log.md`；不要把每個測試命令和 slice 細節複製過去。

## Entry 格式

```md
### HH:MM 主題

- 做了什麼：
- 結果：
- 證據：
- 接續 / 本輪剩餘：
```

## 2026-05-06

### 08:15 Training history query-none render fallback boundary

- scope：
  - Continue read-side fallback audit for Training panel history render.
  - Prevent real `Study` `QueryStateCommand(query="training_history")` query-none path from
    recovering through stale `TrainingController.get_formatted_history()`.
- red / focused tests：
  - Added `test_training_panel_refuses_real_study_query_none_controller_history`.
  - Red gate failed because `TrainingPanel.update_loop()` called
    `controller.get_formatted_history()` when `execute_application_command()` returned `None`.
- 做了什麼：
  - `TrainingPanel.update_loop()` now routes legacy history rendering through
    `run_legacy_controller_fallback()`.
  - real `Study` fallback refusal clears to empty training display and does not read stale
    controller history.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py::test_training_panel_refuses_real_study_query_none_controller_history -q`
    -> failed on stale `get_formatted_history()`.
  - Focused pass:
    same command -> `1 passed`.
  - Training panel regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py tests/unit/ui/test_panel_event_bridges.py -q`
    -> `33 passed`.
  - Focused lint:
    `poetry run ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py`
    -> pass.
  - Type:
    `poetry run basedpyright XBrainLab/ui/panels/training/panel.py` -> `0 errors, 0 warnings, 0 notes`.
    Direct focused basedpyright on `tests/unit/ui/training/test_training_panel.py` is not a useful
    gate because that existing file has many dynamic Qt/Observable test typing errors unrelated to
    this slice; repo-level `basedpyright` remains the required gate.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is a Training UI render fallback cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete Training UX, long-running training soak, human desktop acceptance, or all
    controller read fallback cleanup.

### 08:00 Visualization query-none render fallback boundary

- scope：
  - Continue read-side fallback audit for Visualization panel render.
  - Prevent real `Study` `VisualizeCommand` query-none path from recovering through stale
    `VisualizationController.get_trainers()`.
- red / focused tests：
  - Added `test_visualization_panel_refuses_real_study_query_none_controller_fallback`.
  - Red gate failed because `VisualizationPanel.refresh_combos()` called
    `controller.get_trainers()` when `execute_application_command()` returned `None`.
- 做了什麼：
  - `VisualizationPanel.get_trainers()` now routes legacy trainer rendering through
    `run_legacy_controller_fallback()`.
  - real `Study` fallback refusal keeps empty plan/run controls and does not read stale controller
    trainers or averaged records.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_refuses_real_study_query_none_controller_fallback -q`
    -> failed on stale `get_trainers()`.
  - Focused pass:
    same command -> `1 passed`.
  - Visualization regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
    -> `65 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
    -> pass.
    `poetry run basedpyright XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is a Visualization UI render fallback cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete Visualization UX, saliency/canvas screenshot acceptance, human desktop
    acceptance, or all controller read fallback cleanup.

### 07:45 Evaluation query-none render fallback boundary

- scope：
  - Continue read-side fallback audit for Evaluation panel render.
  - Prevent real `Study` `EvaluateCommand` query-none path from recovering through stale
    `EvaluationController.get_plans()`.
- red / focused tests：
  - Added `test_evaluation_panel_refuses_real_study_query_none_controller_fallback`.
  - Red gate failed because `EvaluationPanel.update_panel()` called
    `controller.get_plans()` when `execute_application_command()` returned `None`.
- 做了什麼：
  - `EvaluationPanel.update_panel()` now routes legacy plan rendering through
    `run_legacy_controller_fallback()`.
  - real `Study` fallback refusal renders `No Data Available` and does not read stale controller
    plans/summaries.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_refuses_real_study_query_none_controller_fallback -q`
    -> failed on stale `get_plans()`.
  - Focused pass:
    same command -> `1 passed`.
  - Evaluation regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_ui_structure_refactored.py -q`
    -> `12 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py`
    -> pass.
    `poetry run basedpyright XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Architecture:
    `poetry run python tests/architecture_compliance.py` -> pass.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is an Evaluation UI render fallback cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete all Evaluation UX, human desktop acceptance, or all controller read
    fallback cleanup.

### 07:30 Visualization fallback refusal product warning

- scope：
  - Continue UI fallback audit for Visualization setup/export actions.
  - Prevent real `Study` fallback refusal from escaping as `LegacyControllerFallbackUnavailableError`
    in Qt slots.
- red / focused tests：
  - Updated existing montage/saliency real `Study` fallback tests to require user-facing warnings
    instead of `RuntimeError`.
  - Added apply-none cases for Montage and Saliency Settings.
  - Added Export Saliency query-none fallback refusal coverage.
  - Red gates failed because `_montage_channel_names()`, `_saliency_dialog_params()`, and
    `_legacy_export_trainers()` let the fallback exception escape.
- 做了什麼：
  - `Set Montage` catches query-none and apply-none fallback refusal and shows `Montage blocked`
    with the shared safety message.
  - `Saliency Settings` catches query-none and apply-none fallback refusal and shows
    `Saliency blocked` with the shared safety message.
  - `Export Saliency` catches query-none trainer fallback refusal and shows
    `Export Saliency Blocked` with the shared safety message.
- validation：
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_export_saliency_refuses_real_study_query_none_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_apply_none_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_apply_none_refuses_real_study_controller_fallback -q`
    -> `5 passed`.
  - Visualization regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
    -> `64 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> pass.
    `poetry run basedpyright XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is a Visualization UI fallback language cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete visualization UX, 3D desktop acceptance, or all query-unavailable
    fallback cleanup.

### 07:20 Preprocess render query-none fallback boundary

- scope：
  - Continue read-side fallback audit for Preprocess render paths.
  - Prevent real `Study` panel refresh / direct plot calls from recovering query-none state through
    stale `PreprocessController.get_preprocessed_data_list()`.
- red / focused tests：
  - Added `test_update_panel_refuses_real_study_query_none_controller_fallback`.
  - Added `test_plot_sample_data_refuses_real_study_query_none_controller_fallback`.
  - Red gates failed because `PreprocessPanel.update_panel()` and
    `PreprocessPlotter.plot_sample_data()` directly read controller data when the shared query
    helper returned `None`.
- 做了什麼：
  - `PreprocessPanel.update_panel()` now routes query-none render fallback through
    `run_legacy_controller_fallback()` and renders no-data for real `Study` fallback refusal.
  - `PreprocessPlotter.plot_sample_data()` now uses the same guard before legacy controller
    readiness/list reads and skips plotting for real `Study` fallback refusal.
- validation：
  - Red gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_panel_refuses_real_study_query_none_controller_fallback -q`
    -> failed on stale `get_preprocessed_data_list()`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_refuses_real_study_query_none_controller_fallback -q`
    -> failed on stale controller readiness/list reads.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_panel_refuses_real_study_query_none_controller_fallback tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_refuses_real_study_query_none_controller_fallback -q`
    -> `2 passed`.
  - Preprocess regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
    -> `73 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
    -> pass.
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is a Preprocess UI render fallback cleanup under the fast dev gate.
- 不能宣稱：
  - This does not prove long-run plot memory trend, remove observer refresh debt, or complete all
    query-unavailable fallback cleanup.

### 07:10 Dataset/Preprocess query-unavailable fallback boundary

- scope：
  - Continue UI controller fallback audit for dialog source list queries.
  - Prevent real `Study` Channel Selection / Epoching dialog source fallback from reading stale
    controller lists when `QueryStateCommand` unexpectedly returns no result.
- red / focused tests：
  - Added `test_open_channel_selection_refuses_real_study_query_none_controller_fallback`.
  - Added `test_open_epoching_refuses_real_study_query_none_controller_fallback`.
  - Red gates failed because the query-unavailable branches directly called
    `controller.get_loaded_data_list()` and `controller.get_preprocessed_data_list()`.
- 做了什麼：
  - Dataset Channel Selection source fallback now uses `run_legacy_controller_fallback()`; real
    `Study` fallback refusal shows `Channel Selection Blocked` with the shared safety message and
    does not open the dialog.
  - Preprocess epoch dialog source fallback now uses the same helper; real `Study` fallback refusal
    shows the shared safety message and does not open `EpochingDialog`.
- validation：
  - Red gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_refuses_real_study_query_none_controller_fallback -q`
    -> failed on stale `get_preprocessed_data_list()`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_refuses_real_study_query_none_controller_fallback -q`
    -> failed on stale `get_loaded_data_list()`.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_refuses_real_study_query_none_controller_fallback tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_refuses_real_study_query_none_controller_fallback -q`
    -> `2 passed`.
  - Sidebar regressions:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
    -> `37 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/preprocess/test_preprocess_plotter.py tests/unit/ui/preprocess/test_data_query.py -q`
    -> `31 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is a UI controller fallback boundary cleanup under the fast dev gate; it does not
    justify primary / fallback x3 local eval.
- 不能宣稱：
  - This does not finish command-driven UI refresh, remove all controller reads, or prove long-run
    UI lifecycle / memory behavior.

### 07:00 Dataset label import target fallback boundary

- scope：
  - Continue Dataset compatibility-path fallback audit.
  - Prevent real `Study` post-load label import from recovering missing Dataset table target data
    through stale `DatasetController.get_loaded_data_list()`.
- red / focused tests：
  - Added `test_import_label_real_study_refuses_controller_target_fallback`.
  - Red gate failed because `_get_target_files_for_import()` fell back to
    `controller.get_loaded_data_list()` when selected table rows lacked `UserRole` data.
- 做了什麼：
  - `_get_target_files_for_import()` now uses `run_legacy_controller_fallback()` for the old
    controller loaded-list fallback.
  - Real `Study` contexts catch the fallback refusal, show `Import Label Blocked`, and return no
    target files instead of using stale controller state.
  - Added explicit controller-None handling for the same fallback branch.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_real_study_refuses_controller_target_fallback -q`
    -> failed as expected on stale controller read.
  - Focused pass:
    same command -> `1 passed`.
  - Dataset action / label regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_import_label.py -q`
    -> `105 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`; `.basedpyright/baseline.json` dropped by `1`
    suppressed optional-controller issue.
  - Static / docs / architecture gate:
    `git diff --check` -> pass;
    `poetry run ruff check .` -> pass;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> pass;
    `poetry run mkdocs build --strict` -> pass.
  - Backend / agent regression:
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
- local eval：
  - Not run. This is a Dataset compatibility UI fallback cleanup under the fast dev gate; it does
    not justify full primary / fallback x3 local eval or VRAM-heavy fallback runs.
- 不能宣稱：
  - This does not make post-load label import the primary Data Interpretation workflow or complete
    the embedded label import wizard.

### 06:50 Data Splitting dialog context boundary

- scope：
  - Continue dialog-level controller fallback audit.
  - Prevent real `Study` `DataSplittingDialog` construction from reading stale
    `TrainingController.get_epoch_data()` / `get_dataset_generator()` when the caller forgot to
    pass service-backed context.
- red / focused tests：
  - Added `test_real_study_requires_explicit_service_context`.
  - Red gate failed because dialog construction called `controller.get_epoch_data()` immediately.
- 做了什麼：
  - Added `_is_real_study_context(parent, controller)`.
  - In a real `Study` context, `epoch_data` / `dataset_generator` default to `None` unless explicitly
    provided.
  - Mock / legacy non-`Study` contexts still use controller fallback, preserving existing dialog
    coverage.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_data_splitting.py::TestDataSplittingDialog::test_real_study_requires_explicit_service_context -q`
    -> failed as expected on stale controller read.
  - Focused pass:
    same command -> `1 passed`.
  - Dialog / Training sidebar regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_data_splitting.py tests/unit/ui/test_data_splitting.py tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
    -> `114 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py tests/unit/ui/dialogs/test_data_splitting.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Note:
    A focused `basedpyright` run including `tests/unit/ui/dialogs/test_data_splitting.py` exposes
    existing optional-widget test errors in that file; the newly added `study` attribute issue was
    fixed with a typed `RealStudyParent` helper. Full repo basedpyright remains the authoritative
    type gate for this slice.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- local eval：
  - Not run. This is a Data Splitting UI dialog fallback cleanup under the fast dev gate.
- 不能宣稱：
  - This does not redesign Data Splitting UX, prove long-running dataset-generation behavior, or
    complete Training sidebar fallback closure.

### 06:40 Visualization failed-query trainer fallback cleanup

- scope：
  - Continue read-side command-truth cleanup for Visualization.
  - Prevent `VisualizationPanel.get_trainers()` from rendering stale controller trainers after a
    failed ApplicationService visualization query.
- red / focused tests：
  - Added `test_visualization_get_trainers_does_not_fallback_after_failed_query`.
  - Red gate failed because `get_trainers()` returned stale `controller.get_trainers()` after
    `last_application_query` was a failed `CommandResult`.
- 做了什麼：
  - `VisualizationPanel.get_trainers()` now returns service payload trainers when available.
  - If `last_application_query` exists but has no usable payload, it returns `[]` instead of
    falling back to controller trainers.
  - Controller trainer fallback remains only when no ApplicationService query result exists, which
    preserves mock / legacy panel compatibility.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_get_trainers_does_not_fallback_after_failed_query -q`
    -> failed as expected on stale trainer return.
  - Focused pass:
    same command -> `1 passed`.
  - Visualization regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
    -> `47 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- local eval：
  - Not run. This is a Visualization UI render-source cleanup under the fast dev gate.
- 不能宣稱：
  - This does not prove visualization UX acceptance, post-training desktop walkthrough, interactive
    3D rendering, or human desktop acceptance.

### 06:30 Preprocess plotter render query source

- scope：
  - Continue read-side command-truth cleanup for the Preprocess page.
  - Prevent `PreprocessPlotter.plot_sample_data()` from reading stale controller data lists in a
    real command-capable context when the caller did not pass explicit render lists.
- red / focused tests：
  - Added `test_plot_sample_data_uses_service_query_before_controller`.
  - Red gate failed because `preprocess_plotter.py` had no application query helper and the no-data
    argument path went straight to `controller.has_data()` /
    `controller.get_preprocessed_data_list()`.
- 做了什麼：
  - Added `XBrainLab/ui/panels/preprocess/data_query.py` with
    `query_preprocess_render_lists(context)`.
  - `PreprocessPanel._query_data_lists_for_render()` and
    `PreprocessPlotter.plot_sample_data()` now share this helper.
  - Plotter direct calls use `QueryStateCommand(query="data_lists", include_objects=True)` first;
    controller list reads remain only when the query helper returns `None` for mock / legacy
    contexts.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_uses_service_query_before_controller -q`
    -> failed as expected because the module had no `execute_application_command` / query path.
  - Focused pass:
    same command -> `1 passed`.
  - Helper / plotter regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_data_query.py tests/unit/ui/preprocess/test_preprocess_plotter.py -q`
    -> `25 passed`.
  - Preprocess UI regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
    -> `70 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/preprocess/data_query.py XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_data_query.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/data_query.py XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_data_query.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- local eval：
  - Not run. This is a Preprocess UI render-source cleanup under the fast dev gate.
- 不能宣稱：
  - This does not prove plot visual quality, large-data plotting performance, memory cleanup, full
    preprocessing workflow UX, or human desktop acceptance.

### 04:55 Training force-clean thread handle guard

- 做了什麼：
  - 檢查 training cleanup path，發現 `TrainingManager.clean_trainer(force_update=True)` 可能在
    trainer background job 還活著時把 `trainer` handle 清掉。
  - 先補紅燈 tests：`Trainer.clean(force_update=True)` 應 interrupt 後 bounded join running
    job；若 join 後 thread 仍 alive 應 raise；manager cleanup failure 不應清掉 trainer handle。
  - 實作 `TRAINER_CLEAN_JOIN_TIMEOUT_SEC` 和 `Trainer.clean(..., wait_timeout=...)`，非 job thread
    上的 force cleanup 會 join；若 timeout 仍 alive，回 `RuntimeError`。
- 結果：
  - Focused red tests 已轉綠。
  - Training controller / application / backend integration regression 通過。
  - 這是 thread-handle safety guard，不是 long-running training soak。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/backend/training/test_trainer.py::test_trainer_force_clean_joins_running_job tests/unit/backend/training/test_trainer.py::test_trainer_force_clean_raises_when_job_stays_running -q`
    -> `2 failed`，`join()` 未呼叫且未 raise。
  - Focused pass：
    `poetry run pytest --capture=sys tests/unit/backend/training/test_trainer.py::test_trainer_force_clean_joins_running_job tests/unit/backend/training/test_trainer.py::test_trainer_force_clean_raises_when_job_stays_running tests/unit/backend/test_training_manager.py::TestCleanTrainer::test_force_update_keeps_trainer_when_cleanup_fails -q`
    -> `3 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/unit/backend/training/test_trainer.py tests/unit/backend/test_training_manager.py -q`
    -> `40 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/unit/backend/controller/test_training_controller.py tests/unit/backend/application/test_training_service.py tests/unit/backend/application/test_lifecycle_service.py -q`
    -> `19 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`。
  - Focused lint/type：
    `poetry run ruff check XBrainLab/backend/training/trainer.py tests/unit/backend/training/test_trainer.py tests/unit/backend/test_training_manager.py`
    -> pass。
    `poetry run basedpyright XBrainLab/backend/training/trainer.py tests/unit/backend/training/test_trainer.py tests/unit/backend/test_training_manager.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material advisory。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。未跑 full local LLM primary / fallback x3，因為這不是
    release / thesis evidence closure。

### 04:45 Local runtime shutdown cleanup

- 做了什麼：
  - 檢查 `LocalBackend` / `LLMEngine` / `AgentWorker` / `LLMController.close()` 的 local runtime
    cleanup path。
  - 先補紅燈 tests：`LocalBackend.unload()` 釋放 model / tokenizer 並清 CUDA cache；
    `LLMEngine.close()` unload cached backends；`AgentWorker.shutdown()` bounded wait generation
    thread 並 close engine；`LLMController.close()` 呼叫 worker shutdown。
  - 實作 `LocalBackend.unload()`、`LLMEngine.close()`、stale backend reload 前 unload、
    `AgentWorker.shutdown()`、generation thread active-reference tracking，以及 controller close
    的 bounded worker shutdown / worker-thread wait。
- 結果：
  - Focused red tests 已轉綠。
  - LLM core / worker / controller regression 均通過。
  - 這是 assistant lifecycle resource cleanup；未跑 true local model 或 GPU soak，也未跑
    release / thesis local eval。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py::TestLocalBackendLoad::test_unload_releases_model_and_cuda_cache tests/unit/llm/core/test_engine.py::test_engine_close_unloads_cached_backends -q`
    -> `2 failed`，`unload` / `close` 不存在。
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/llm/test_worker_coverage.py::TestAgentWorkerCleanup::test_shutdown_waits_for_generation_and_closes_engine tests/unit/llm/agent/test_controller.py::TestClose::test_close_stops_thread -q`
    -> `2 failed`，`AgentWorker.shutdown()` 不存在且 controller close 未呼叫它。
  - Focused pass：
    `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py::TestLocalBackendLoad::test_unload_releases_model_and_cuda_cache tests/unit/llm/core/test_engine.py::test_engine_close_unloads_cached_backends tests/unit/llm/test_worker_coverage.py::TestAgentWorkerCleanup::test_shutdown_waits_for_generation_and_closes_engine tests/unit/llm/agent/test_controller.py::TestClose::test_close_stops_thread -q`
    -> `4 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py tests/unit/llm/core/test_backend_local.py tests/unit/llm/core/test_engine_hotswap.py -q`
    -> `37 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/unit/llm/agent/test_worker.py tests/unit/llm/test_worker_coverage.py tests/unit/llm/agent/test_worker_timeout.py -q`
    -> `39 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_controller_cov.py tests/unit/llm/agent/test_controller_integration.py -q`
    -> `99 passed`。
  - Focused lint/type：
    `poetry run ruff check XBrainLab/llm/core/backends/local.py XBrainLab/llm/core/engine.py XBrainLab/llm/agent/worker.py XBrainLab/llm/agent/controller.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py tests/unit/llm/test_worker_coverage.py tests/unit/llm/agent/test_controller.py`
    -> pass。
    `poetry run basedpyright XBrainLab/llm/core/backends/local.py XBrainLab/llm/core/engine.py XBrainLab/llm/agent/worker.py XBrainLab/llm/agent/controller.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py tests/unit/llm/test_worker_coverage.py tests/unit/llm/agent/test_controller.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material advisory。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。未跑 full local LLM primary / fallback x3，因為這不是
    release / thesis evidence closure。

### 04:30 Local model downloader lifecycle cleanup

- 做了什麼：
  - 使用 `tdd-guard` / `performance-resource-reviewer` 檢查 local model downloader QThread /
    subprocess lifecycle。
  - 先補紅燈 tests：`ModelDownloader.shutdown()` 必須 cancel worker 並 bounded wait running
    thread；`DownloadWorker.run()` 收到 `finished` queue message 後仍要 join subprocess；
    `ModelSettingsDialog.reject()` / `closeEvent()` 下載中必須走 downloader shutdown。
  - 實作 `DownloadWorker` terminal cleanup：`finally` 會 reap subprocess 並 close queue；
    cancel path 改成 bounded terminate join，必要時 bounded kill join，避免 unbounded join。
  - 實作 `ModelDownloader.shutdown(wait_ms=...)`，settings dialog teardown 使用它並抑制 close
    teardown 期間的 cleanup popup。
- 結果：
  - Downloader focused lifecycle tests 先紅後綠。
  - local model settings dialog close / reject 不再只是 fire-and-forget cancel。
  - 沒有跑 local LLM eval；依照 current gate policy，這是 downloader lifecycle slice，只需
    fast focused regression。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/llm/core/test_downloader.py::TestModelDownloader::test_shutdown_cancels_worker_and_waits_for_running_thread tests/unit/llm/core/test_downloader.py::TestDownloadWorker::test_run_joins_download_process_after_finished_message -q`
    -> `2 failed`，`shutdown` 不存在、terminal message 後 process 未 join。
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_model_settings.py::TestRejectAndClose::test_reject_while_downloading tests/unit/ui/dialogs/test_model_settings.py::TestRejectAndClose::test_close_event -q`
    -> `2 failed`，dialog teardown 未呼叫 shutdown。
  - Focused pass：
    `poetry run pytest --capture=sys tests/unit/llm/core/test_downloader.py::TestModelDownloader::test_shutdown_cancels_worker_and_waits_for_running_thread tests/unit/llm/core/test_downloader.py::TestDownloadWorker::test_run_joins_download_process_after_finished_message -q`
    -> `2 passed`。
  - Focused pass：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_model_settings.py::TestRejectAndClose::test_reject_while_downloading tests/unit/ui/dialogs/test_model_settings.py::TestRejectAndClose::test_close_event -q`
    -> `2 passed`。
  - Regression:
    `poetry run pytest --capture=sys tests/unit/llm/core/test_downloader.py tests/unit/llm/test_coverage_boost.py::TestDownloadWorkerRun tests/unit/llm/test_misc_coverage.py::TestModelDownloaderCoverage tests/unit/test_llm_backend.py::TestDownloader -q`
    -> `27 passed`。
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_local_bootstrap_validation.py -q`
    -> `25 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material advisory。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。未跑 full local LLM primary / fallback x3，因為這不是
    release / thesis evidence closure。

## 2026-05-05

### 19:04 UI observer refresh architecture guard

- 做了什麼：
  - 在 `tests/architecture_compliance.py` 新增
    `check_ui_observer_direct_update_bridges()`。
  - guard 會掃 `XBrainLab/ui/**/*.py`，若 `_create_bridge()` 第三個參數是
    `self.update_panel` 就 fail，要求 simple observer refresh 改用
    `refresh_from_observer()`。
  - named callback handlers 仍允許，例如 `_on_training_started`，避免把 event-specific behavior
    硬套成 generic refresh。
  - 新增 `tests/unit/test_architecture_compliance.py` cases，覆蓋 direct update violation、
    `refresh_from_observer` allowance 和 callback handler allowance。
- 結果：
  - 目前 real codebase 通過 guard，代表 observer refresh coordinator boundary 沒有直接回退。
  - 這是防回歸 guard，不代表 callback-specific observer path 已全部分類完成。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_flags_direct_update_panel tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_allows_refresh_from_observer tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_allows_callback_handlers -q`
    -> import error，`check_ui_observer_direct_update_bridges` 尚不存在。
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `7 passed`。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> pass。
  - `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。下一步仍是 callback-specific observer / manual refresh 分類。

### 18:56 UI observer refresh coordinator slice

- 做了什麼：
  - 新增 `refresh_coordinator.refresh_panel(panel)`，作為單一 panel safe no-arg refresh helper。
  - `refresh_after_command()` 和 `refresh_after_navigation()` 也改用 `refresh_panel()`，避免各自
    直接呼叫 `_call_noarg(..., "update_panel")`。
  - 在 `BasePanel` 新增 `refresh_from_observer()`，讓 observer event 可以走同一個 coordinator
    boundary。
  - Dataset / Preprocess / Training / Evaluation / Visualization panel 的單純
    `event -> update_panel()` bridge 改成 `event -> refresh_from_observer()`。
  - 保留 callback-specific handlers：Dataset import-finished action handler、TrainingPanel start/stop /
    config / history / live update handlers 等沒有改成 generic refresh。
  - 先補紅燈測試：`refresh_panel` 不存在、`refresh_from_observer` 不存在、Preprocess observer
    event 沒走 `refresh_from_observer()`。
- 結果：
  - Observer event 語意保留，但 simple panel refresh 不再直接散落在各 panel。
  - Command-result refresh、navigation refresh 和 simple observer refresh 現在共用
    `refresh_panel()` 的 safe-call 邊界。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_refresh_panel_uses_safe_noarg_update_call tests/unit/ui/core/test_base_panel.py::test_refresh_from_observer_delegates_to_coordinator tests/unit/ui/test_panel_event_bridges.py::test_preprocess_panel_observer_events_use_refresh_coordinator -q`
    -> import error，`refresh_panel` 尚不存在。
  - Focused tests：
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py tests/unit/ui/test_panel_event_bridges.py -q`
    -> `27 passed`。
  - Focused lint/type：
    `poetry run ruff check XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/core/base_panel.py XBrainLab/ui/panels/dataset/panel.py XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/training/panel.py XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py tests/unit/ui/test_panel_event_bridges.py`
    -> pass。
    `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/core/base_panel.py XBrainLab/ui/panels/dataset/panel.py XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/training/panel.py XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py tests/unit/ui/test_panel_event_bridges.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Source scan:
    `rg -n "self\\.update_panel" XBrainLab/ui/panels -S` -> remaining direct calls are Dataset
    panel internal fallback/failure refreshes, not `_create_bridge(..., self.update_panel)` handlers.
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `929 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。這不代表 observer/callback refresh 全部 closure。

### 18:46 Data Interpretation confirmation copy polish

- 做了什麼：
  - 檢查最新 `artifacts/ui/data-interpretation-preview.png` /
    `data-interpretation-applied.png`：Dataset table 已填滿主 panel，`Events` / `Labels` 不再用綠色
    success 語意，wizard tables 沒有水平外溢，`Review Summary` alternate rows 已降對比。
  - 發現 preview dialog 底部仍會把 required confirmations 串成長句，重複 `Review Summary`，且把
    raw filenames 放到底部提示。
  - 先改 dialog test 建立紅燈，要求 bottom confirmation copy 是短 action cue，詳細項目留在
    `Review Summary`。
  - 更新 `_confirmation_text()`：`needs_confirmation` 時固定顯示
    `Review the items marked Needs confirmation, then confirm and apply.`
  - 刷新 `scripts/dev/capture_data_interpretation_replay.py` 產生的 screenshot / JSON artifact。
- 結果：
  - `artifacts/ui/data-interpretation-preview.png` 底部已不再顯示 raw confirmation dump。
  - `artifacts/ui/data-interpretation-replay.json` 的 dialog visible text 最後一行為短 action cue；
    `review_summary_rows` 仍保留具體 metadata / label carrier confirmation。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_renders_payload -q`
    -> failed，底部仍是 `Confirmation required: Confirm session metadata.`
  - Focused tests：
    `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `16 passed`。
  - Focused lint/type：
    `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
    -> pass。
    `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Artifact refresh：
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`，refreshed `artifacts/ui/data-interpretation-preview.png` /
    `artifacts/ui/data-interpretation-replay.json`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。這不是完整 mature import wizard closure。

### 18:36 UI tab-switch refresh coordinator slice

- 做了什麼：
  - 新增 `refresh_after_navigation(main_window, index)`，把 Dataset / Preprocess / Training /
    Evaluation / Visualization navigation index 到 panel refresh 的 mapping 放進
    `XBrainLab.ui.refresh_coordinator`。
  - `MainWindow.switch_page()` 現在只負責切換 `QStackedWidget` 和 navigation button checked state，
    然後委派 `refresh_after_navigation()`。
  - 先補 tests 建立紅燈：`refresh_after_navigation` 尚不存在時，coordinator / delegation tests
    import failure。
  - 順手修正 touched test 內既有 `MainWindow.dataset_panel = QWidget()` 的 basedpyright 型別問題，
    用 `cast(Any, window)` 保留 runtime 測試語意。
- 結果：
  - Tab-switch refresh scope 不再 hard-code 在 `MainWindow` 裡；command-result refresh 和
    navigation refresh 都由 `refresh_coordinator` 定義。
  - 行為保持不變：切換頁面只刷新目標 panel，未知 index 不刷新。
  - 這仍不是 observer / callback refresh closure。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_navigation_refreshes_only_selected_panel tests/unit/ui/test_refresh_coordinator.py::test_navigation_refresh_ignores_unknown_panel_index tests/unit/ui/test_main_window_sync.py::test_switch_page_delegates_navigation_refresh -q`
    -> import error，`refresh_after_navigation` 尚不存在。
  - Focused pass：
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_main_window_sync.py -q`
    -> `15 passed`。
  - Focused lint/type：
    `poetry run ruff check XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/main_window.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_main_window_sync.py`
    -> pass。
    `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/main_window.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_main_window_sync.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - Broader UI regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `926 passed`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。下一步可分類 observer bridge / callback refresh path。

### 18:29 UI post-command refresh architecture guard

- 做了什麼：
  - 在 `tests/architecture_compliance.py` 新增 post-command local refresh guard。
  - guard 會掃 `XBrainLab/ui/**/*.py`：service-backed `execute_application_command()` 之後若同一
    statement block 直接呼叫 `update_panel()`、`check_ready_to_train()`、`notify_update()`、
    `on_update()`、`update_info_panel()` 或 `refresh_backend_status()` 會 fail。
  - explicit `refresh=False` query path、failure / `None` guard branch 和 legacy fallback branch 允許
    保留 local refresh。
  - 新增 `tests/unit/test_architecture_compliance.py` 覆蓋 direct local refresh violation、
    legacy helper allowance、`not result.failed` success-branch violation 和 `refresh=False` query
    allowance。
- 結果：
  - 目前 real codebase 通過 guard，代表剛完成的 service-success refresh cleanup 沒有直接回流。
  - 這只保護 post-command local refresh boundary；observer / callback / tab-switch refresh 仍是
    後續 cleanup，不可宣稱 UI refresh target closure。
- 證據：
  - `git diff --check` -> pass。
  - `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> pass。
  - `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `4 passed`。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run ruff check .` -> pass。
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點；下一步仍是分類 observer / callback refresh path，以及把 remaining
    manual refresh 納入 coordinator 或明確保留為 event bridge。

### 18:15 Visualization control refresh coordinator slice

- 做了什麼：
  - 在 `ControlSidebar` 新增 `_on_update_after_legacy_result()`。
  - montage (`ApplyMontageCommand`) 與 saliency (`SaliencyCommand`) service-success path 不再直接
    `panel.on_update()`。
  - 先改 montage 既有測試並新增 saliency service-success test 建立紅燈。
  - 結果：
  - Visualization control service-success path 交給 command refresh coordinator。
  - saliency mock / legacy `None` fallback 仍保留手動 `on_update()`。
  - 因為這個 slice 直接碰 `tests/unit/ui/visualization/test_control_sidebar.py`，也修掉該檔既有
    Qt dynamic `study` attribute type issue，讓 direct basedpyright on touched files 可通過。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_service_success_uses_coordinator_refresh -q`
    -> `2 failed`，兩者都是 `panel.on_update()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_service_success_uses_coordinator_refresh tests/unit/ui/test_dialogs_extra.py::TestControlSidebar::test_set_saliency -q`
    -> `3 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_dialogs_extra.py::TestControlSidebar -q`
    -> `13 passed`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `923 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。

### 18:06 Preprocess sidebar refresh coordinator slice

- 做了什麼：
  - 在 `PreprocessSidebar` 新增 `_notify_update_after_legacy_result()` 和
    `_update_main_info_after_legacy_result()`。
  - filter / resample / rereference / normalize / epoch / reset service-success path 不再直接
    `notify_update()` 或 `update_info_panel()`。
  - 先改 service-backed normalize 與 reset tests 建立紅燈，要求成功 command 不直接刷新 panel。
- 結果：
  - Preprocess sidebar mutating service-success path 交給 command refresh coordinator。
  - mock / legacy `None` fallback 仍保留手動 panel / main info refresh。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_normalize_service_success_uses_coordinator_refresh tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_service_success_does_not_fallback_to_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_uses_reset_capability_when_preprocess_locked -q`
    -> `3 failed`，皆為 `panel.update_panel()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_normalize_service_success_uses_coordinator_refresh tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_normalize_accepted tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_service_success_does_not_fallback_to_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_uses_reset_capability_when_preprocess_locked tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess -q`
    -> `5 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/preprocess/test_preprocess_panel_normalize.py -q`
    -> `67 passed`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `922 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。

### 17:59 Dataset inline metadata refresh coordinator slice

- 做了什麼：
  - 在 `DatasetPanel` 新增 `_update_panel_after_legacy_result()`。
  - subject/session inline metadata edit 成功執行 `UpdateMetadataCommand` 後，不再直接
    `update_panel()`。
  - 先新增 focused red test：service-backed inline subject edit 不應呼叫 controller fallback，也不應
    在 panel 內直接刷新。
  - 結果：
  - inline metadata service-success path 交給 command refresh coordinator。
  - mock / legacy `None` fallback 仍保留手動 refresh；failure / blocked path 仍刷新以還原 UI。
  - 由於這個 slice 直接碰 `tests/unit/ui/dataset/test_panel.py`，也順手修正該檔既有 Qt dynamic
    attribute / nullable item type issue，讓 direct basedpyright on touched files 可通過。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_service_success_uses_coordinator_refresh -q`
    -> failed；`update_panel()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_service_success_uses_coordinator_refresh tests/unit/ui/dataset/test_panel.py::test_dataset_panel_on_item_changed tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_cells_use_backend_update_capability -q`
    -> `3 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py -q`
    -> `11 passed`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `921 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。

### 17:53 Dataset sidebar refresh coordinator slice

- 做了什麼：
  - 在 `DatasetSidebar` 新增 `_update_panel_after_legacy_result()`。
  - channel selection (`PreprocessCommand(SELECT_CHANNELS)`) 與 clear dataset
    (`ResetSessionCommand`) service-success path 不再直接呼叫 `panel.update_panel()`。
  - 先改兩個既有測試建立紅燈：service-backed channel selection / clear dataset 成功後不應在
    sidebar 直接刷新 Dataset panel。
- 結果：
  - Dataset sidebar mutating service-success path 交給 command refresh coordinator。
  - mock / legacy `None` fallback 仍保留手動 refresh。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_uses_reset_session_capability_before_confirm -q`
    -> `2 failed`，兩者都是 `panel.update_panel()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_accepted tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_uses_reset_session_capability_before_confirm tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset -q`
    -> `4 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q`
    -> `64 passed`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `920 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。

### 17:47 Direct load compatibility refresh coordinator slice

- 做了什麼：
  - 把 Data Interpretation unavailable / not-handled 時的 `LoadDataCommand` service-success
    `panel.update_panel()` 移除。
  - 先改既有 direct-load compatibility 測試建立紅燈：service-backed `LoadDataCommand` 成功後不應
    fallback controller，也不應在 action handler 直接刷新 Dataset panel。
- 結果：
  - direct file load compatibility service-success path 交給 command refresh coordinator。
  - controller `import_files` fallback 仍只在 command helper 回 `None` 時透過 explicit
    mock / legacy-only helper 觸發。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_service_load_success_does_not_fallback_to_controller -q`
    -> failed；`panel.update_panel()` 被呼叫。
  - 修正後 focused tests：
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_service_load_success_does_not_fallback_to_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_success -q`
    -> `2 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py -q`
    -> `127 passed`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `920 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。
  - 這不把 direct `LoadDataCommand` 升格成 product data-entry model；Data Interpretation 仍是資料入口主線。

### 17:42 Post-load label compatibility refresh coordinator slice

- 做了什麼：
  - 把 `ImportLabelsCommand` service-success path 的 `panel.update_panel()` 改成
    `_update_panel_after_legacy_result(result)`。
  - 先在 recipe-update label import 測試加紅燈：service-backed label import 成功並保存 recipe
    時，action handler 不應直接刷新 Dataset panel。
- 結果：
  - service-backed post-load label compatibility 成功 path 交給 command refresh coordinator。
  - mock / legacy `None` fallback path 仍保留手動 refresh。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe -q`
    -> failed；`panel.update_panel()` 被呼叫。
  - 修正後 focused tests：
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_single_same_length tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_batch tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_timestamp -q`
    -> `4 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py -q`
    -> `127 passed`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `920 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。
  - 這不改變舊 label import 是 compatibility path 的定位；Data Interpretation wizard 仍需
    mature embedded label editor。

### 17:34 Data Interpretation apply refresh coordinator slice

- 做了什麼：
  - 延續 command-driven refresh cleanup，把 Data Interpretation EEG file / folder-BIDS import
    apply 和 saved recipe reload apply 後的 `panel.update_panel()` 移除。
  - 這些 service-success path 現在依 `execute_application_command()` 的
    `refresh_after_command()`，用 `ApplyInterpretationCommand.changed_state` 刷新 Dataset panel。
  - 先改測試建立紅燈：Data Interpretation command chain 成功後，action handler 不應直接呼叫
    `panel.update_panel()`。
- 結果：
  - file import、folder/BIDS import、recipe reload、recipe reload label-carrier remap、recipe reload
    EEG-file remap 五條成功 apply path 都不再重複手動刷新 Dataset panel。
  - import-label compatibility 和 inline metadata table refresh 尚未納入這個 slice。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py -q`
    -> `5 failed, 122 passed`，五個 failure 都是 `panel.update_panel()` 被呼叫。
  - 修正後：
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py -q`
    -> `127 passed`。
  - Slice gates：
    `git diff --check` -> pass；
    `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass；
    `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`；
    `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - Broader gates：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `920 passed`；
    `poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 此 slice 已達可提交點。
  - 下一步可處理 import-label compatibility / inline metadata refresh 或轉回成熟 import wizard
    UI polish。

### 17:28 Dataset action refresh coordinator slice

- 做了什麼：
  - 延續 command-driven refresh cleanup，把 Dataset action handler 的 smart parse、batch metadata
    和 remove files post-command `panel.update_panel()` 改成 legacy fallback-only。
  - 新增 `_update_panel_after_legacy_result()`，只有 `execute_application_command()` 回 `None`
    的 mock / legacy fallback 才手動刷新；real `Study` service success 交給
    `refresh_after_command()`。
  - 先加紅燈：`RemoveFilesCommand` service success 後不應在 action handler 直接呼叫
    `panel.update_panel()`。
- 結果：
  - Dataset action handler 的三條常見 mutating path 不再在 service success path 重複刷新
    Dataset panel。
  - 這不涵蓋 Data Interpretation apply / import label / inline metadata table 的所有 manual refresh。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_service_success_uses_coordinator_refresh -q`
    -> failed；`panel.update_panel()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_service_success_uses_coordinator_refresh tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_session tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_success -q`
    -> `4 passed`。
  - Focused ruff / basedpyright on touched files -> pass / `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 跑 broader UI/docs/static gates 後提交；下一步可處理 Data Interpretation apply 或 Dataset inline
    metadata table 的 manual refresh。

### 17:22 Training readiness refresh coordinator slice

- 做了什麼：
  - 在 Training sidebar 先收斂 post-command manual refresh：generate dataset、select model、
    training settings、start training 和 clear history 的 service-backed success path 不再直接呼叫
    `check_ready_to_train()`。
  - 新增 `_check_ready_after_legacy_result()`，只有 mock / legacy fallback (`result is None`) 才手動
    refresh readiness；real `Study` success path 由 `refresh_after_command()` / `training_panel.update_panel()`
    觸發 readiness refresh。
  - 先加紅燈：`TrainCommand` service success 後不應在 same action handler 直接呼叫
    `check_ready_to_train()`。
- 結果：
  - Training sidebar 是第一條從 command success local refresh 轉向 coordinator-owned refresh 的 UI
    workflow。
  - 這不代表 Dataset / Preprocess / other panels 的 manual `update_panel()` 已全部收斂。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_uses_coordinator_for_readiness -q`
    -> failed；`check_ready_to_train()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_uses_coordinator_for_readiness tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_ui_action tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_accepted tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_accepted tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history -q`
    -> `5 passed`。
  - Focused ruff / basedpyright on touched files -> pass / `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 跑 broader UI/docs/static gates 後提交；下一步可把同樣模式推到 Dataset / Preprocess manual
    `update_panel()` calls。

### 17:14 UI fallback architecture guard

- 做了什麼：
  - 在 `tests/architecture_compliance.py` 新增 UI fallback static guard。
  - Guard 會掃 `XBrainLab/ui/**/*.py` 的 `result is None` / `*_result is None` branch；若 branch
    直接呼叫 controller mutation 方法，且不是透過 `run_legacy_controller_fallback()`，就 fail。
- 結果：
  - 目前 UI fallback audit 的成果被 architecture gate 保護，後續新增 silent controller fallback
    會被 `poetry run python tests/architecture_compliance.py` 擋下。
  - 這只守 controller fallback boundary；不代表 observer/manual refresh cleanup 已完成。
- 證據：
  - `poetry run ruff check tests/architecture_compliance.py` -> pass。
  - `poetry run basedpyright tests/architecture_compliance.py` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 跑 full docs/static gates 後提交；下一步回到 command-driven refresh coordinator 的剩餘
    observer/manual refresh cleanup 或 Data Interpretation mature wizard。

### 17:07 Visualization / AgentManager fallback boundary

- 做了什麼：
  - 延續 controller fallback audit，把 Visualization control sidebar 的 saliency settings fallback
    和 AgentManager montage confirmation fallback 改成 `run_legacy_controller_fallback()`。
  - 先加紅燈：
    - real `Study` + missing `CommandResult` 時，saliency settings 不可呼叫
      `controller.set_saliency_params()`。
    - real `Study` + missing `CommandResult` 時，assistant montage confirmation 不可呼叫
      `preprocess_controller.apply_montage()`。
- 結果：
  - Visualization / AgentManager 的剩餘 controller mutation fallback 已顯式限制為 mock /
    legacy non-`Study`。
  - `rg` 剩餘 `result is None` 命中主要是 service-unavailable critical / false returns，或已用 helper
    包住的 compatibility fallback。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_refuses_real_study_controller_fallback tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback -q`
    -> failed；兩者都未 raise。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_refuses_real_study_controller_fallback tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep::test_open_montage_accepted tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_blocked_by_backend_capability -q`
    -> `4 passed`。
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_agent_manager_coverage.py -q`
    -> `28 passed`。
  - Source focused basedpyright:
    `poetry run basedpyright XBrainLab/ui/panels/visualization/control_sidebar.py XBrainLab/ui/components/agent_manager.py`
    -> `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 跑 broader UI/docs/full static gates 後提交；下一步可 audit remaining `result is None` branches
    是否全部是 non-controller service-unavailable handling，並回到 manual refresh cleanup。

### 17:01 Dataset fallback boundary

- 做了什麼：
  - 延續 controller fallback audit，把 Dataset panel / sidebar / action handler 的 metadata edit /
    batch metadata、smart parse、remove files、direct file import、clear dataset、channel selection
    和 post-load label compatibility fallback 改成 `run_legacy_controller_fallback()`。
  - 先加紅燈：real `Study` + `execute_application_command()` 意外回 `None` 時，remove files
    不可呼叫 `controller.remove_files()`。
- 結果：
  - Dataset product runtime 不會在 missing CommandResult 時 silent fallback 到 dataset controller
    mutation；mock / legacy non-`Study` tests 仍保留相容 fallback。
  - Data Interpretation service-unavailable branches 保持原本 critical / false behavior，不混進
    controller fallback helper。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_refuses_real_study_controller_fallback -q`
    -> failed；`controller.remove_files()` 仍被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_refuses_real_study_controller_fallback tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_session tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_success tests/unit/ui/dataset/test_panel.py::test_dataset_panel_on_item_changed -q`
    -> `5 passed`。
  - Focused ruff / basedpyright on touched files -> pass / `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 跑 broader UI/docs/static gates 後提交；Visualization / AgentManager fallback 還未完成。

### 16:56 Preprocess sidebar fallback boundary

- 做了什麼：
  - 延續 Training sidebar fallback boundary，把 Preprocess sidebar 的 filter / resample /
    rereference / normalize / epoch / reset `result is None` fallback 改成
    `run_legacy_controller_fallback()`。
  - 先加紅燈：real `Study` + `execute_application_command()` 意外回 `None` 時，reset preprocess
    不可呼叫 `controller.reset_preprocess()`。
- 結果：
  - Mock / legacy non-`Study` UI tests 仍可走既有 controller compatibility fallback。
  - Real `Study` product runtime 不會在 missing CommandResult 時 silent fallback 到 preprocess
    controller；reset path 會顯示 command unavailable / refusing fallback 的錯誤。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_refuses_real_study_controller_fallback -q`
    -> failed；`controller.reset_preprocess()` 被呼叫。
  - 修正後 focused tests：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_refuses_real_study_controller_fallback tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_filtering_accepted tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_accepted tests/unit/ui/preprocess/test_preprocess_panel.py::TestPreprocessSidebarOps::test_rereference_success -q`
    -> `4 passed`。
  - Focused ruff / basedpyright on touched files -> pass / `0 errors, 0 warnings, 0 notes`。
- 接續 / 本輪剩餘：
  - 跑 UI regression / docs / full static gates 後提交；剩餘 Dataset / Visualization /
    AgentManager fallback 仍未完成。

### 16:51 Training sidebar fallback boundary

- 做了什麼：
  - 針對 `UI Command Refresh Coordinator + Controller Fallback Audit` 的下一個切片，先把
    Training sidebar controller fallback 明確收斂成 mock / legacy-only boundary。
  - 新增 `run_legacy_controller_fallback()`；real `Study` context 若 command helper 意外回
    `None`，會拒絕 controller fallback，而不是 silent mutation。
  - Training sidebar 的 split cleanup / generate dataset、model selection、training settings、
    start / stop training 和 clear history fallback 全部改用這個 helper。
- 結果：
  - Legacy MagicMock / non-Study UI tests 仍可走 controller compatibility fallback。
  - Real `Study` path 的 command helper contract 有可測 guard：如果失去 `CommandResult`，不會
    靜默改走 training controller。
- 證據：
  - 初始紅燈：
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_application_capabilities.py::test_legacy_controller_fallback_refuses_real_study tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_refuses_real_study_controller_fallback -q`
    -> import / behavior failed before helper existed。
  - 修正後同一指令 -> `2 passed`。
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_application_capabilities.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `88 passed`。
  - Focused ruff / basedpyright on touched files -> pass / `0 errors, 0 warnings, 0 notes`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 把同一 helper pattern 推到 Dataset / Preprocess / Visualization / AgentManager 剩餘
    `result is None` fallback；不要把 Training sidebar slice 說成 full fallback audit。

### 16:45 UI command refresh coordinator first slice

- 做了什麼：
  - 先用 failing import test 確認尚無 centralized UI refresh helper，再新增
    `XBrainLab.ui.refresh_coordinator.refresh_after_command()`。
  - `execute_application_command()` 在 real `Study` path 執行 `ApplicationService.execute()`
    後，會依 `CommandResult.changed_state` 刷新 Dataset / Preprocess / Training /
    Evaluation / Visualization panels、main info panel 和 Assistant backend status。
  - Evaluation / Visualization panel 的 query-only refresh 改用 `refresh=False`，避免 panel
    update 內的 query command 再觸發二次 refresh；coordinator 也加 re-entrancy guard，防止同一
    main window refresh 自我遞迴。
- 結果：
  - 這是 `UI Command Refresh Coordinator + Controller Fallback Audit` 的 first slice；它建立
    command-result-driven refresh 基礎，但仍不能宣稱 UI refresh target closure。
  - 後續仍要盤點 observer/manual/tab-switch refresh 與剩餘 product runtime controller fallback。
- 證據：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_application_capabilities.py -q`
    -> `8 passed`。
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_application_capabilities.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_ui_misc.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `242 passed`。
  - `poetry run ruff check XBrainLab/ui/application_capabilities.py XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_application_capabilities.py tests/unit/ui/test_refresh_coordinator.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/ui/application_capabilities.py XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_application_capabilities.py tests/unit/ui/test_refresh_coordinator.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 跑 docs validation / architecture smoke 後提交本地 commit；不要把這個 first slice 說成
    full controller fallback audit。

### 16:25 Local tool-call 121-case primary / fallback rerun

- 做了什麼：
  - 接續 remap-expanded deterministic `121` cases，跑 primary / fallback 真 local model x3。
  - Primary rerun 先完成 `121 / 121`。
  - Fallback 首輪正式 artifact 是 `115 / 121`，失敗集中在可安全修復的 output variants：
    missing `test_ratio`、string-shaped `metadata_overrides`、unrequested label-review fields、
    generated `task_` / `run` prefixes，以及 bandpass frequency aliases。
  - 先加紅燈 unit/scorer tests，再修 `tool_call_normalizer` / verifier / local eval prompt-scorer。
  - 用同一批 fallback raw outputs rescore 為 `121 / 121` 後，重跑正式 fallback local eval 寫出 artifact。
- 結果：
  - `artifacts/agent_evals/dashboard.md` 顯示 deterministic / primary
    `microsoft/Phi-4-mini-instruct` / fallback `microsoft/Phi-3.5-mini-instruct` 都是
    `121 / 121`，local repeat count `3`，stability `100%`。
  - resource boundary：primary / fallback 都使用已存在 cache，`HF_HUB_OFFLINE=1` /
    `TRANSFORMERS_OFFLINE=1`；未下載新模型。
- 證據：
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json` /
    `.md` -> `121 / 121`。
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json` /
    `.md` -> `121 / 121`。
  - `artifacts/agent_evals/dashboard.md` -> deterministic / primary / fallback same-suite
    comparison。
  - Focused red-to-green tests：
    `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py::test_normalizes_bandpass_frequency_alias_arguments tests/unit/llm/agent/test_tool_call_normalizer.py::test_generate_dataset_extracts_missing_test_ratio_from_user_text tests/unit/llm/agent/test_tool_call_normalizer.py::test_preview_drops_unrequested_label_review_choices_from_metadata_turn tests/unit/llm/agent/test_tool_call_normalizer.py::test_preview_simplifies_string_metadata_overrides tests/unit/llm/agent/test_tool_call_normalizer.py::test_preview_normalizes_task_run_values_from_latest_text tests/unit/scripts/test_run_local_tool_call_eval.py::test_scores_generate_dataset_missing_test_ratio_from_latest_text tests/unit/scripts/test_run_local_tool_call_eval.py::test_scores_preview_metadata_overrides_string_map_as_choices tests/unit/scripts/test_run_local_tool_call_eval.py::test_scores_preview_unrequested_label_review_noise_as_metadata_choice tests/unit/scripts/test_run_local_tool_call_eval.py::test_scores_preview_task_run_with_generated_prefix_noise -q`
    -> `9 passed`。
  - Focused final gate:
    `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `134 passed`。
  - Broad LLM / agent gate:
    `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent -q`
    -> `529 passed`。
  - Quality gates:
    `git diff --check` -> pass；
    `timeout 300s poetry run ruff check .` -> pass；
    `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - Commit 本輪 tool-call hardening + documentation update；不要標記 product complete。

### 15:45 UI refresh / controller fallback reviewer finding captured

- 做了什麼：
  - 在目前 local fallback eval 繼續跑的同時，先把 reviewer finding 轉成文件 truth，不中斷
    validation runner。
  - 更新 `docs/current.md`、`docs/planning/now.md`、`docs/planning/roadmap.md` 和
    `docs/records/implementation_log.md`，加入 `UI Command Refresh Coordinator + Controller
    Fallback Audit` follow-up milestone。
- 結果：
  - 文件現在明確說明 backend command spine 已大幅改善，但 UI refresh 仍是 observer /
    manual refresh / command-result local refresh / ChatPanel signal 的混合模式。
  - 文件也明確標記 product runtime mutating path 不應 silent fallback 到 controller mutation；
    fallback 只能留在 explicit mock / unit-test compatibility 或 isolated legacy adapter。
  - Data Interpretation 仍是 baseline wizard，不是 final import system；embedded label editor、
    raw trigger selector、complex GDF / MAT anchor reconciliation、XDF / LSL parser 和 full real-data
    manual certification 仍是 follow-up。
- 證據：
  - Docs pending validation：`docs/current.md`、`docs/planning/now.md`、
    `docs/planning/roadmap.md`、`docs/records/implementation_log.md`。
- 接續 / 本輪剩餘：
  - 等目前 fallback local eval 正式 artifact 寫完後，再跑 mkdocs / lint / targeted tests 並 commit
    本輪 tool-call hardening + documentation slice。

### 12:36 Recipe reload backend label-carrier remap

- 做了什麼：
  - 在 missing label-carrier blocker 後補 backend remap path，讓 UI / headless 後續可以明確把
    saved carrier 映射到 current scan 的 replacement carrier。
  - 先加紅燈：
    - candidate builder 收到 `label_carrier_remap={old: new}` 時，不應再因 old carrier
      missing 而 blocked。
    - saved `label_carrier_choices` 應套到 remapped current carrier，而不是遺失。
    - integration flow 先 reload blocked recipe，再用 `PreviewInterpretationCommand` 提供
      remap choices，validation 應回到 `needs_confirmation`。
  - `build_interpretation_candidate()` 現在會 normalize `label_carrier_remap`，用 exact path 或
    basename 匹配 old carrier，並把 saved choices 改掛到 remapped target carrier。
  - `required_label_carriers` 也會經 remap 後再與 scan result 比對。
- 結果：
  - explicit remap 可以清掉 missing-carrier blocker，且 replacement carrier 保留原 recipe 的
    label field、anchor、time model、granularity 和 role。
  - recipe trace 新增 `choices:label_carrier_remap`。
- 證據：
  - 初始紅燈：
    `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py::test_build_interpretation_candidate_remaps_saved_label_carrier_choices tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_label_carrier_remap -q`
    -> failed；blocked reason 仍包含 old carrier，integration validation 仍是 `blocked`。
  - 修正後同一指令 -> `2 passed`。
  - Post-change gates：
    `git diff --check` -> pass；
    `timeout 300s poetry run ruff check .` -> pass；
    `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `108 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `6 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`。
- 接續 / 本輪剩餘：
  - 當下只支撐 backend/headless remap truth；後續 UI slice 已接上 wizard selector，但仍不能
    宣稱完整 recipe conflict editor。

### 12:25 Recipe reload missing label-carrier blocker

- 做了什麼：
  - 延續 missing selected EEG blocker，補上 saved label/event carrier 消失時的 validation
    boundary。recipe replay 不應靜默丟失 external labels。
  - 先加三個紅燈：
    - `choices_from_import_recipe()` 要把 recipe 的 `label_carriers` 帶成
      `required_label_carriers`。
    - `build_interpretation_candidate()` 要對 missing required label carrier 產生 blocked reason。
    - `ReloadInterpretationRecipeCommand` 載入含 missing label carrier 的 recipe 時，validation
      decision 要是 `blocked`。
  - `choices_from_import_recipe()` 現在會從 `recipe.label_carriers` 和
    `recipe.label_carrier_plan[].path` 建立 `required_label_carriers`。
  - candidate builder 會用 exact path 或 basename 比對 required carriers 與 scan result；找不到
    時加入 `Saved label/event carrier(s) were not found in the current scan: ...`，並在 recipe trace
    保留 `choices:label_carriers`。
- 結果：
  - 初始紅燈：missing label carrier 不會 block，reload validation 還是
    `needs_confirmation`。
  - 現在 saved label/event carrier missing from rescan 會在 apply 前 blocked。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_recipe.py::test_choices_from_import_recipe_recreates_review_choices tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_blocks_missing_saved_label_carrier -q`
    -> `6 passed`。
  - Post-change gates：
    `git diff --check` -> pass；
    `timeout 300s poetry run ruff check .` -> pass；
    `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `107 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `5 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`。
- 接續 / 本輪剩餘：
  - 這處理 missing label carrier，不是完整 remap UI；renamed carrier ambiguity、manual remap 和
    anchor reconciliation 仍需要 mature import wizard conflict editor。

### 12:17 Recipe reload missing-file blocker

- 做了什麼：
  - 在 recipe reload diff 之後補一個 safety boundary：若 saved recipe 的 selected EEG file
    不在 current scan 裡，不能等到 apply/import runtime 才失敗。
  - 先加紅燈 unit test，要求 `build_interpretation_candidate()` 對 missing selected EEG file
    產生 blocked reason。
  - `data_interpretation_candidate.py` 現在會用 exact path 或 basename 比對 selected files
    與 scanned files；找不到的 saved selection 會加入
    `Selected EEG file(s) were not found in the current scan: ...`。
  - 加 integration test：手寫含 missing selected EEG 的 recipe，`ReloadInterpretationRecipeCommand`
    會成功產生 preview，但 validation decision 是 `blocked`，state snapshot 也記錄 blocked。
- 結果：
  - 初始紅燈：missing selected EEG file 沒有 blocked reason。
  - 現在 reload candidate 在 apply 前就被 validation layer 擋下。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py::test_build_interpretation_candidate_blocks_selected_files_missing_from_scan -q`
    -> 初始紅燈，後續通過。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_blocks_missing_saved_eeg_file -q`
    -> `4 passed`。
  - `poetry run basedpyright XBrainLab/backend/application/data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_candidate.py tests/integration/backend/test_application_service_workflow.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run ruff check XBrainLab/backend/application/data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_candidate.py tests/integration/backend/test_application_service_workflow.py`
    -> pass。
  - Post-change gates：
    `git diff --check` -> pass；
    `timeout 300s poetry run ruff check .` -> pass；
    `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `106 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `4 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`。
- 接續 / 本輪剩餘：
  - 這只處理 selected EEG missing。Label carrier conflict / remap、renamed source root 和
    anchor reconciliation 仍需要 mature import wizard conflict UI。

### 12:08 Recipe reload comparison rows

- 做了什麼：
  - 用 `data-interpretation-reviewer` / `ui-product-reviewer` 檢查 roadmap gap：recipe reload
    已會 rehydrate saved choices，但 UI 只顯示 generic `Reloaded recipe / Reapplied`，沒有讓
    使用者看到 saved recipe 與重新 scan 的差異。
  - 先加紅燈測試，要求 backend preview payload 在 reload 時產生 `EEG files`、`Label carriers`
    和 `Saved choices` diff rows；UI dialog 要把 `diff_rows` 顯示進 `Review Summary`。
  - `build_interpretation_preview()` 新增 optional `scan` / `recipe` context；reload handler 會
    傳入 recipe + rescan result，normal preview 仍只用 candidate。
  - `recipe_reload_summary` 現在包含 `status` 和 `diff_rows`，會用 filename/carrier basename 比對
    saved recipe selections 與 current scan，標出 `Matched` 或 `Changed`。
  - `DataInterpretationPreviewDialog` 會把 `recipe_reload_summary.diff_rows` 轉成人話 review rows，
    不顯示 raw JSON。
  - 刷新 consolidated human-like walkthrough artifact。
- 結果：
  - 紅燈已確認：
    - backend test 初始失敗：`build_interpretation_preview()` 不接受 `recipe` keyword。
    - UI test 初始失敗：Review Summary 沒有 `EEG files` row。
  - 新 artifact `artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png` 可見
    `Reloaded recipe`、`EEG files`、`Label carriers`、`Saved choices` rows。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py::test_build_interpretation_preview_summarizes_recipe_reload_diff -q`
    -> 初始紅燈，後續與 UI focused gate 一起通過。
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_shows_recipe_reload_diff -q`
    -> 初始紅燈，後續與 backend focused gate 一起通過。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `16 passed`。
  - `poetry run basedpyright XBrainLab/backend/application/data_interpretation_review.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/backend/application/test_data_interpretation_review.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/backend/test_application_service_workflow.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run ruff check XBrainLab/backend/application/data_interpretation_review.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/backend/application/test_data_interpretation_review.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/backend/test_application_service_workflow.py`
    -> pass。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`，refreshed human-like walkthrough JSON / Markdown / screenshots。
  - Post-change gates：
    `git diff --check` -> pass；
    `timeout 300s poetry run ruff check .` -> pass；
    `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `105 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `3 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `12 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`。
- 接續 / 本輪剩餘：
  - 這支撐 recipe reload comparison visibility，不是完整 recipe diff editor、complex conflict
    resolver 或 Windows human desktop acceptance。

### 11:55 Data-entry routing and Dataset table fit

- 做了什麼：
  - 把一般使用者資料入口語句從 legacy `load_data` 轉到 Data Interpretation
    `scan_source`：例如 `Load /path/file.gdf`、`Import my EEG folder ...` 會進 scan /
    preview / validate 主線；只有明確說 legacy / direct compatibility 的語句才保留
    `load_data`。
  - 修正 BIDS source hint normalization：path 或最新 prompt 提到 BIDS 時，`scan_source`
    argument 會收斂成 `source_hint=bids`。
  - 刷新 deterministic / local primary / local fallback tool-call eval artifacts；local models
    使用已存在 cache，未下載新模型。
  - 依使用者截圖修正 Data Interpretation preview dialog：label carrier、events、recipe trace
    tables 使用 stretch + elide，避免超出欄框；`Review Summary` 使用較低對比 dark
    alternating row。
  - 修正 Dataset panel table：第一輪先讓 `File` 欄填滿主 panel，其餘欄依內容收斂；
    `Events` 欄改成 `Events (n)` / `Labels (n)`。
  - `capture_data_interpretation_replay.py` 現在保存 Dataset table headers、rows、resize modes
    和 column widths，讓 replay artifact 能直接驗證主 panel 是否被欄位填滿。
- 結果：
  - Focused UI replay JSON 顯示 Dataset table rows 為 `Events (6)` / `Labels (4)`；後續 table
    fill slice 已把實作收斂成 interactive columns + File 欄承接剩餘寬度。
  - Local tool-call dashboard 顯示 deterministic / primary / fallback 都為 `118 / 118`；
    primary / fallback 各重跑 `3` 次。
  - 初次 broad gate 發現兩個需要收斂的問題：`basedpyright` 對 `QTreeWidget.header()` optional
    access 報錯；agent controller test 還期待舊 `file path` wording。已修成 header guard 與
    Data Interpretation `source path` expectation。
- 證據：
  - Resource preflight：
    `poetry run python scripts/dev/inspect_local_assistant_runtime.py`
    -> primary / fallback cached、runtime `gpu-ready`、cache usage `15.34 GB`、no download。
  - Deterministic eval：
    `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals/deterministic --repeat-count 3`
    -> `118 / 118`；root latest artifacts copied from deterministic output。
  - Local primary：
    `poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --output-dir artifacts/agent_evals/local_primary`
    -> final rerun `118 / 118`。
  - Local fallback：
    `poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --output-dir artifacts/agent_evals/local_fallback`
    -> `118 / 118`。
  - Dashboard：
    `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals --output artifacts/agent_evals/dashboard.md`
    -> refreshed `artifacts/agent_evals/dashboard.md`。
  - Focused UI gate：
    `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py -q`
    -> `23 passed`。
  - Focused agent gate：
    `poetry run pytest --capture=sys tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py -q`
    -> `42 passed`。
  - Replay artifact：
    `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`，刷新 `artifacts/ui/data-interpretation-preview.png`、
    `artifacts/ui/data-interpretation-applied.png` 和
    `artifacts/ui/data-interpretation-replay.json`。
  - Post-change gates：
    `git diff --check` -> pass；
    `timeout 300s poetry run ruff check .` -> pass；
    `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning；
    `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `3 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`；
    `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`。
- 接續 / 本輪剩餘：
  - 這支撐 Data Interpretation-first data-entry routing、Dataset table fill behavior 和 focused
    import UI table polish；仍不是 Windows human desktop acceptance、完整 mature import wizard、
    長時間 ChatPanel workflow 或 MCP HTTP / long-running automation closure。

### 08:20 Backend train confirmation command gate

- 做了什麼：
  - 使用 `architecture-reviewer` / `refactor-slicer` / `tdd-guard` 檢查 backend command gate，
    發現 `train` capability 已標成 long-running / `requires_confirmation=True`，但
    backend-ready `ApplicationService.execute(TrainCommand())` 仍會直接啟動 training；confirmation
    主要只靠 UI / agent 外層。
  - 先加紅燈測試：
    `test_train_command_requires_confirmation_before_long_running_start`，確認未 confirmed 的
    backend-ready training request 目前會錯誤成功並呼叫 `start_training()`。
  - 新增 `XBrainLab/backend/application/command_gate.py`，讓 `ApplicationService` 委派 focused
    gate：先檢查 capability enabled / blocked reason，再檢查
    `confirmation_required` / `requires_confirmation` 和 command 的 `confirmed` 欄位。
  - `TrainCommand` 新增 `confirmed` 欄位；Training sidebar、agent confirmation resume、
    application tool surface 和 real training facade 會在人類確認後傳 `confirmed=True`。
  - 同步修正 agent `clear_dataset` confirmation resume，不再依賴 application surface 無條件
    `ResetSessionCommand(confirmed=True)` 的隱性旁路。
- 結果：
  - Unready `train` 仍回 precondition blocked reason，例如 `Generate datasets before training`。
  - Backend-ready 但未 confirmed 的 `train` 會回 `confirmation_required`，且不呼叫 training
    controller。
  - Backend-ready 且 confirmed 的 `train` 才會執行。
- 證據：
  - Red test：
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_train_command_requires_confirmation_before_long_running_start -q`
    -> failed because `TrainCommand()` returned ok and called training start。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_train_command_blocked_until_backend_ready tests/unit/backend/application/test_application_service.py::test_train_command_requires_confirmation_before_long_running_start -q`
    -> `2 passed`。
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py::test_start_training_surface_preserves_backend_confirmation_boundary tests/unit/llm/agent/test_controller.py::TestOnUserConfirmed::test_approved_executes_and_finalises tests/unit/llm/agent/test_controller.py::TestOnUserConfirmed::test_approved_failure_triggers_retry tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_does_not_fallback_to_controller -q`
    -> `4 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `102 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `42 passed`。
  - Focused `basedpyright` on touched backend / agent / UI files -> `0 errors, 0 warnings, 0 notes`。
  - `git diff --check` -> pass。
  - `timeout 300s poetry run ruff check .` -> pass。
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - MCP long-running job / progress / cancel / recovery 仍未完成；這個 slice 只修 Command API
    confirmation enforcement。

### 08:06 RAG legacy data-entry example filter

- 做了什麼：
  - 檢查 RAG gold-set / retriever，發現 bundled `gold_set.json` 仍有大量
    `load_data` / `attach_labels` examples；即使 stage prompt 已降權 legacy tools，RAG few-shot
    context 仍可能把舊資料入口工具重新注入 local LLM prompt。
  - 新增 `XBrainLab/llm/rag/example_policy.py`，定義 primary RAG examples 不得包含
    `load_data`、`attach_labels`、`import_labels`。
  - `RAGIndexer.load_gold_set()` 和 `BM25Index.build_from_json()` 會跳過 legacy compatibility
    examples。
  - `RAGRetriever.get_similar_examples()` 在 dense candidates 和 final ranking 都會套同一 policy，
    保護已存在的舊 Qdrant collection；policy 會辨識 list / dict / `tool` / `command` /
    OpenAI-style `function.name` metadata 形狀。
  - 補 unit tests 覆蓋 policy、bundled gold set BM25 build、以及 old vector store 回傳 legacy
    top candidate 時 retriever 仍只格式化 primary `scan_source` example。
- 結果：
  - RAG prompt context 不再把 legacy data-entry examples 放進 local LLM prompt。
  - `gold_set.json` 暫未全面改寫；historical examples 仍留在檔案中，但 ingestion / retrieval
    boundary 會排除它們。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/llm/rag/test_example_policy.py -q`
    -> `5 passed`。
  - `poetry run pytest --capture=sys tests/unit/llm/rag/test_example_policy.py tests/unit/test_llm_backend.py tests/unit/llm/agent/test_assembler_stage.py -q`
    -> `31 passed`。
  - `poetry run ruff check XBrainLab/llm/rag tests/unit/llm/rag/test_example_policy.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/llm/rag tests/unit/llm/rag/test_example_policy.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `git diff --check` -> pass。
  - `timeout 300s poetry run ruff check .` -> pass。
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 後續應把 old gold-set content 逐步改成 Data Interpretation positive / blocked /
    recovery examples；目前這個 slice 先確保舊 examples 不再污染 prompt。

### 07:55 ChatPanel next-step legacy status cleanup

- 做了什麼：
  - 使用 `clean-code-reviewer` / `ui-product-reviewer` 檢查 UI / agent visible status，發現
    `AgentManager._product_next_steps()` 在空狀態仍回 `load_data`，raw-loaded 狀態仍把
    `attach_labels` 當成 next step；ChatPanel 會把這些 compatibility commands 顯示成
    `Load EEG data` / `Attach labels`。
  - 先補 tests，要求 empty-state next step 使用 `scan_source`，raw-loaded next step 不顯示
    `attach_labels`，ChatPanel status rendering 過濾 `load_data` / `attach_labels`。
  - `AgentManager._product_next_steps()` 改為 empty state 推 `scan_source`、raw-loaded state 只推
    `preprocess`；ChatPanel status rendering 層新增 legacy command filter，避免 mock / compatibility
    path 把 legacy command 重新帶回可見主 UI。
  - 追加清理 assistant tool-result fallback label：legacy `load_data` / `attach_labels` 不再顯示成
    `Load EEG data` / `Attach labels`，改成較中性的 `Import data` / `Add labels to loaded data`。
  - 刷新 consolidated human-like walkthrough artifact。
- 結果：
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` visible text 只看到
    `Scan data source`，沒有 `Load EEG data`、`Attach labels`、`load_data` 或 `attach_labels`。
  - 最新 walkthrough 仍通過：status `passed`、`26 / 26` phases、`20` screenshots、resource smoke
    `passed=True`，RSS growth `231628 KB` / limit `600000 KB`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py::TestAgentManagerProductChatFlow::test_product_next_steps_use_data_interpretation_in_empty_state tests/unit/ui/components/test_agent_manager.py::TestAgentManagerProductChatFlow::test_product_next_steps_hide_legacy_label_tool_after_raw_load -q`
    -> 初始紅燈：steps 仍是 `load_data` / `attach_labels`。
  - `poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py::TestAgentManagerProductChatFlow::test_product_next_steps_use_data_interpretation_in_empty_state tests/unit/ui/components/test_agent_manager.py::TestAgentManagerProductChatFlow::test_product_next_steps_hide_legacy_label_tool_after_raw_load -q`
    -> `2 passed`。
  - `poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py::TestChatPanelCallbacks::test_product_status_updates_empty_state_and_chips -q`
    -> `1 passed`。
  - `poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `75 passed`。
  - `poetry run ruff check XBrainLab/ui/chat/panel.py XBrainLab/ui/components/agent_manager.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/ui/chat/panel.py XBrainLab/ui/components/agent_manager.py tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_legacy_load_summary_uses_neutral_product_language tests/unit/ui/chat/test_chat_panel.py::TestChatPanelCallbacks::test_product_status_updates_empty_state_and_chips tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q`
    -> `3 passed`。
  - `poetry run ruff check XBrainLab/llm/agent/controller.py XBrainLab/ui/product_language.py XBrainLab/ui/chat/panel.py tests/unit/llm/agent/test_controller.py tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/llm/agent/controller.py XBrainLab/ui/product_language.py XBrainLab/ui/chat/panel.py tests/unit/llm/agent/test_controller.py tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - neutral-label follow-up 後重跑 `git diff --check`、full `ruff check .`、full
    `basedpyright`、`mkdocs build --strict` 和 `architecture_compliance.py` -> pass /
    `0 errors` / `Architecture compliant!`。
  - Focused basedpyright on the full legacy `tests/unit/ui/components/test_agent_manager.py` file
    still reports pre-existing mock/QMainWindow typing debt; full project basedpyright remains the
    authoritative gate。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`，refreshed consolidated walkthrough artifacts。
  - `git diff --check` -> pass。
  - `timeout 300s poetry run ruff check .` -> pass。
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 這清的是 ChatPanel / AgentManager visible product language；legacy compatibility commands 仍存在於
    compatibility service / parser / tests，後續還要繼續清理 old RAG gold set 和 legacy real-tool
    expectations 的 claim boundary。

### 07:45 Human-like walkthrough resource smoke gate

- 做了什麼：
  - 使用 `performance-resource-reviewer` 檢查 consolidated automated walkthrough，發現 script
    已保存 `start` / `before_close` / `after_close` resource notes，但 pass/fail summary 沒有把
    thread / Qt pool / RSS evidence 當成 gate。
  - 先補 unit test：建構 `after_close` Python threads 上升、Qt active thread pool 未清、RSS
    high-water delta 過大的 fake artifact，要求 `build_pass_fail_summary()` fail。
  - 新增 `build_resource_smoke_summary()`，把 close 後 Python thread count、Qt active thread count
    和 `ru_maxrss` high-water delta 納入 pass/fail；Markdown report 也顯示 resource smoke
    passed、RSS growth 和 smoke boundary。
  - 刷新 consolidated human-like walkthrough artifact。
- 結果：
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` 現在有
    `pass_fail_summary.resource_smoke`。
  - 最新 offscreen artifact status `passed`、`26 / 26` required phases、`20` screenshots、
    resource smoke `passed=True`。
  - 最新 resource smoke：RSS growth `231628 KB` / limit `600000 KB`，after-close Qt active
    threads `0`；這是 coarse smoke，不是 leak-proof soak。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py::test_build_pass_fail_summary_flags_unsettled_threads -q`
    -> 初始紅燈：`build_pass_fail_summary()` 尚不接受 `resource_notes`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py::test_build_pass_fail_summary_flags_unsettled_threads -q`
    -> `1 passed`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `11 passed`。
  - `poetry run ruff check scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> pass。
  - `poetry run basedpyright scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`，refreshed consolidated walkthrough artifacts。
  - `git diff --check` -> pass。
  - `timeout 300s poetry run ruff check .` -> pass。
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
- 接續 / 本輪剩餘：
  - 這只會抓 obvious cleanup regression；仍需要長時間 ChatPanel/local-model/training soak、
    Windows launcher真人 click-through、雙螢幕 / DPI 和更多 lifecycle / stop-cleanup checks。

### 07:23 Data Interpretation recipe reload rehydration

- 做了什麼：
  - 盤點 roadmap 的 recipe reload gap，發現 `ReloadInterpretationRecipeCommand` 雖然會重新
    scan / preview / validate，但只把 `recipe_id` 傳給 candidate builder，saved metadata /
    label carrier / event role / class map choices 都會流失。
  - 先改 non-mocked backend workflow：保存含 metadata override、event role、class map 的
    recipe，reload 後要求 candidate choices / event roles / class map / recipe trace 都保留。
    測試先紅燈，確認舊 reload 只剩 `recipe_id`。
  - 新增 `choices_from_import_recipe()`，把 saved selected EEG files、metadata overrides、
    label carrier choices、event roles 和 class map rehydrated 回 candidate choices。
  - `ReloadInterpretationRecipeCommand` 改用 rehydrated choices 後再 build candidate /
    preview / validation。
  - Preview payload 新增 `recipe_reload_summary`，Data Interpretation Review Summary 會顯示
    `Reloaded recipe / Reapplied`。
  - Human-like walkthrough 的 `recipe_reloaded` screenshot 改為 reload preview dialog，phase notes
    保存 reload review rows。
  - 補 `ImportRecipe.write_json()` trailing newline，避免 regenerated recipe artifact 只有 EOF diff。
  - 刷新 consolidated human-like walkthrough artifact。
- 結果：
  - Human-like walkthrough reload command result 現在可見 `metadata_overrides`、
    `label_carrier_choices`、`event_roles` 和 `selected_eeg_files`。
  - Reload candidate recipe trace 現在含 `choices:metadata_overrides`、
    `choices:event_roles` 和 `choices:label_carriers`。
  - `artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png` 是 reload preview dialog，notes
    第一列是 `Reloaded recipe / Reapplied`。
  - consolidated human-like walkthrough offscreen rerun 通過：`26 / 26` required phases、`20`
    screenshots、`human_desktop_acceptance=not performed`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py::test_choices_from_import_recipe_recreates_review_choices -q`
    -> 初始紅燈：`choices_from_import_recipe` 尚不存在。
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> 初始紅燈：reload candidate 沒有 `metadata_overrides`。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py::test_build_import_recipe_preserves_applied_trace_and_writes_json -q`
    -> 初始紅燈：recipe JSON 沒有 trailing newline。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py -q`
    -> `4 passed`。
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `1 passed`。
  - focused `ruff check` / `basedpyright` for recipe/service/workflow files -> pass / `0 errors`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`，refreshed consolidated walkthrough artifacts。
- 接續 / 本輪剩餘：
  - 這是 backend recipe rehydration，不是 user-facing recipe diff UI；完整 diff / conflict
    explanation、raw trigger selector、complex anchor reconciliation 和 Windows human acceptance
    仍未完成。

### 07:07 Data Interpretation event role selector UI

- 做了什麼：
  - 使用 `data-interpretation-reviewer` / `ui-product-reviewer` / `tdd-guard` 檢查 wizard role
    review，發現 event role 雖然可進 recipe choices，但仍是 free-text row edit，不夠像產品級
    import wizard。
  - 先補 dialog unit test：要求 event role row column 2 是 `QComboBox`，且 row 本身不帶
    `ItemIsEditable`。測試先紅燈，確認舊 row 仍可任意編輯。
  - 將 event role rows 改成 selector controls，顯示 `Class cue`、`Time anchor` 等人話選項，
    `get_result()` 仍回 backend recipe values。
  - 檢查 replay artifact 後發現 script 仍用 `item.setText()` 改 event role，沒有真正操作
    selector；補 `apply_replay_review_choices()` helper 和 unit test，並讓 replay JSON 保存
    `event_rows`。
  - 再檢查 consolidated human-like walkthrough recipe，發現它也還在舊 `item.setText()` path；
    補 human-like helper test，並讓 walkthrough 共用 Data Interpretation replay helper。
  - 刷新 `artifacts/ui/data-interpretation-*` 和 consolidated
    `artifacts/ui/human-like-walkthrough/*` artifacts。
- 結果：
  - Data Interpretation replay JSON 現在可見
    `trial_type -> event role -> Class cue`。
  - `review_choices.event_roles.trial_type` 保存為 `class cue`。
  - human-like walkthrough saved recipe 現在也保存 `trial_type: class cue`，recipe trace 含
    `choices:event_roles`。
  - consolidated human-like walkthrough offscreen rerun 通過：`26 / 26` required phases、`20 / 20`
    nonblank screenshots、`human_desktop_acceptance=not performed`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_event_role_review -q`
    -> 初始紅燈：event role row 仍有 `ItemIsEditable`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> 初始紅燈：`apply_replay_review_choices` 尚不存在。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py::test_apply_review_choices_updates_event_role_selector -q`
    -> 初始紅燈：human-like helper 沒有更新 event role selector。
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `23 passed`。
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/scripts/test_capture_data_interpretation_replay.py scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/scripts/test_capture_data_interpretation_replay.py scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`，refreshed `artifacts/ui/data-interpretation-preview.png` /
    `data-interpretation-applied.png` / `data-interpretation-replay.json`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`，refreshed consolidated walkthrough artifacts。
- 接續 / 本輪剩餘：
  - 這是 event role selector polish，不是 mature import wizard completion；raw trigger selector、
    complex anchor reconciliation、XDF/LSL stream selection、real-data manual certification 和
    Windows human acceptance 仍未完成。

### 06:48 MCP stdio adapter session boundary

- 做了什麼：
  - 使用 `mcp-adapter-reviewer` 檢查 stdio MCP baseline 的下一個 boundary gap：`tools/call`
    structured result 有 CommandResult / state snapshot，但沒有明確說明這是 headless
    ApplicationService session，也沒有 UI refresh claim boundary。
  - 先補 unit test，要求同一 `MCPServer` 的多個 tool call 回傳相同 `session_id`，且
    `mode=headless_mcp_stdio`、`transport=stdio`、`ui_refresh.supported=False`。
  - 在 `MCPServer` 建立 per-server stdio session id，`tools/call` structuredContent 追加
    `adapter` metadata。
  - 在 automation output schema 補 optional `adapter` property，讓 MCP tool schema 能說明這個
    envelope。
  - 更新 stdio walkthrough summarizer / Markdown，讓 stdlib-only client artifact 直接呈現
    adapter boundary。
  - 進一步補 `train` over stdio 的 long-running guard：schema valid 後仍不同步執行 enabled
    long-running 任務，而是回 `long_running_job_required` 和 `job_boundary` diagnostics。
    後續 08:36 slice 已修正 precedence，未 ready training 會先回 backend precondition。
- 結果：
  - `artifacts/mcp/stdio-walkthrough.json` / `.md` 已刷新；summary 顯示
    `headless_mcp_stdio`、`transport=stdio`、`session_id_stable=True`、
    `ui_refresh_supported=False`。
  - stdio walkthrough 現在也包含 `train` call；後續刷新後 default unready path 的 error type 是
    `precondition`，只有 backend-ready / enabled train 才會到 `long_running_job_required`。
  - MCP adapter 更清楚地避免「HTTP/headless external client 正在刷新桌面 UI」這種錯誤 claim。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py::test_tools_call_reuses_one_application_service_session -q`
    -> 初始紅燈：缺 `adapter` key。
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py::test_stdio_mcp_blocks_long_running_commands_until_job_api_exists tests/integration/mcp/test_stdio_walkthrough_artifact.py::test_capture_mcp_stdio_walkthrough_writes_client_artifact -q`
    -> 初始紅燈：stdio `train` 只回一般 precondition failure，artifact 沒有 `train` / long-running boundary；實作後 `2 passed`。
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py -q`
    -> `6 passed`。
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
    -> `9 passed`。
  - `poetry run ruff check XBrainLab/mcp/server.py XBrainLab/backend/application/automation.py scripts/dev/capture_mcp_stdio_walkthrough.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/mcp/server.py XBrainLab/backend/application/automation.py scripts/dev/capture_mcp_stdio_walkthrough.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 180s poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp`
    -> refreshed artifact。
  - `git diff --check`
    -> pass。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - 還不能宣稱 MCP HTTP / Streamable HTTP、long-running training job model、progress、cancel 或
    full MCP client certification。

### 06:40 Data Interpretation review summary UI

- 做了什麼：
  - 使用 `ui-product-reviewer` / `data-interpretation-reviewer` / `tdd-guard` 檢查 wizard UX
    gap：warning、confirmation、format capability 和 downstream impact 仍以 plain text review
    dump 呈現，偏工程 artifact，不像成熟 import wizard。
  - 先改 dialog unit test：要求 `review_tree` 存在、`QPlainTextEdit` 不再出現在 dialog，且
    format boundary / downstream impact 能從 structured tree row 被讀到。測試先紅燈，確認舊
    UI 仍只有 `review_text`。
  - 將 `DataInterpretationPreviewDialog` 的 review notes 改為 `Review Summary` table，欄位為
    Item / Status / What it means，承載 warnings、confirmations、blocked reasons、downstream
    impact、recipe trace 和 format capability rows。
  - 將流程提示改成 `Select source | Scan result | Preview | Confirm | Apply | Save recipe`。
  - 更新 `capture_data_interpretation_replay.py`，artifact 改保存 `review_summary_rows`。
  - 刷新 `artifacts/ui/data-interpretation-*` 和 consolidated
    `artifacts/ui/human-like-walkthrough/*` artifacts。
- 結果：
  - Data Interpretation replay JSON 現在有 `review_summary_rows`，不再保存 `review_notes`
    plain text dump。
  - consolidated human-like walkthrough offscreen rerun 通過：`26 / 26` required phases、`20`
    screenshots、`human_desktop_acceptance=not performed`。
  - 第一次 `xvfb-run` rerun 因 WSLg / Wayland maximized-state protocol error 中斷；沒有把這次
    失敗當成 evidence，改用 `QT_QPA_PLATFORM=offscreen` 完成 automated walkthrough。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_renders_payload tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_shows_format_boundaries -q`
    -> 初始紅燈：`DataInterpretationPreviewDialog` 沒有 `review_tree`。
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `9 passed`。
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `21 passed`。
  - `timeout 300s xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`，refreshed `artifacts/ui/data-interpretation-preview.png` /
    `data-interpretation-applied.png` / `data-interpretation-replay.json`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`，`status=passed`、`required_phase_count=26`、`screenshot_count=20`。
  - `git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - 還不能宣稱 mature import wizard complete：raw trigger selector、complex MAT/GDF anchor
    reconciliation、XDF/LSL stream selection 和 real-data manual certification 仍未完成。
  - 這仍不是 Windows / 雙螢幕 / DPI 真人驗收；human desktop acceptance 仍是 blocker。

### 18:40 Tool-call local 118-case scorer hardening

- 做了什麼：
  - 參考 `agent-toolcall-designer`、`thesis-evidence-reviewer`、`docs-curator` 和
    `validation-runner`，檢查第 `118` 個 downstream-locked apply case 是否真的被 local model /
    scorer 證明。
  - 發現舊 local scorer 可能把 fallback 在 blocked apply 情境下改叫 `clear_dataset` 的 unsafe
    substitute 算成 pass；先補 focused tests，把 substitute-tool path 改成 failure。
  - 調整 local eval prompt / scorer：direct command blocked 時隱藏 substitute tools；direct blocked
    command 可轉成 verifier-blocked response；scan / reset / configure 等替代工具保留為 tool call
    並評為 failure。
  - 補 absolute-path 指示，避免 `bad-load-path` 類 prompt 因路徑字面含 `missing` / `bad` /
    `unknown` 被誤判成缺 input。
  - 補 local output normalizer，將 `reset_session` / `clear_session` alias 對齊 registered
    `clear_dataset`。
  - resource preflight 確認 model cache `15.34 GB`、limit `20.00 GB`、free disk 約
    `158.36 GB`、primary / fallback 都已 cached、estimated download `0.00 GB`；full rerun 使用
    `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`。
- 結果：
  - Deterministic、primary、fallback 現在都使用同一 `118` thesis-candidate cases。
  - primary `microsoft/Phi-4-mini-instruct`：`118 / 118` x `3` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`118 / 118` x `3` pass。
  - Dashboard 已刷新：`artifacts/agent_evals/dashboard.md`。
  - apply-lock local raw output 可被 parser 視為 direct blocked `apply_interpretation`，但不會被
    當成執行成功；unsafe substitute tools 不再被 scorer 放過。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py::test_normalizes_workflow_command_aliases_to_registered_tools tests/unit/scripts/test_run_local_tool_call_eval.py::test_blocked_requested_step_substitute_tool_fails_score tests/unit/scripts/test_run_local_tool_call_eval.py::test_blocked_requested_direct_tool_is_scored_as_blocked_response -q`
    -> `3 passed`。
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py tests/unit/llm/agent/test_tool_call_normalizer.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py tests/unit/llm/agent/test_tool_call_normalizer.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 3600s env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 160 --output-dir artifacts/agent_evals/local_primary`
    -> `118 / 118`。
  - `timeout 3600s env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 160 --output-dir artifacts/agent_evals/local_fallback`
    -> `118 / 118`。
  - `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
    -> dashboard refreshed。
  - `git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `100 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py -q`
    -> `530 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - 仍不能宣稱 product-complete：Windows human acceptance、mature import wizard editing、
    ChatPanel 長時間 tool-command chain、MCP HTTP / long-running boundary 仍是 product closure
    gaps。
  - 下一步要跑本 slice 的 focused/full validation 並提交，不包含 protected settings 或新 skill
    檔案。

### 17:05 Tool-call apply-lock wrong-tool coverage

- 做了什麼：
  - 使用 `agent-toolcall-designer` / `thesis-evidence-reviewer` 檢查下一個 eval gap，發現剛補的
    `apply_interpretation` raw-edit blocker 尚未進入 tool-call benchmark。
  - 先在 integration eval test 補 focused assertion，紅燈顯示
    `wrong-tool-temptation-apply-after-epoch` case 不存在。
  - 新增 deterministic state `validated_safe_after_epoch`：Data Interpretation validation 是 safe，
    但 active dataset 已有 raw / preprocessed / epoch 且 locked。
  - 新增中文 / mixed-language wrong-tool temptation case：使用者要求套用新資料解讀，並提示
    blocked 時改 scan 新路徑；expected result 是 `apply_interpretation` blocked / no tool call。
  - 刷新 `artifacts/agent_evals/latest.json` / `.md` 和 `artifacts/agent_evals/dashboard.md`。
- 結果：
  - Deterministic suite 從 `117` cases 變成 `118` cases，新增 downstream-locked Data
    Interpretation apply boundary coverage。
  - Dashboard 現在清楚顯示 deterministic 是 `118` cases；local primary / fallback 仍是上一輪
    `117` cases x `3`，因此不能把第 `118` case 宣稱為真 local model evidence。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py::test_deterministic_tool_call_eval_passes_and_writes_artifacts -q`
    -> 初始紅燈 `apply_lock_case is None`，實作後 `1 passed`。
  - `poetry run ruff check scripts/agent/evals/run_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py`
    -> pass。
  - `poetry run basedpyright scripts/agent/evals/run_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
    -> `artifacts/agent_evals/latest.json` / `.md`，summary `118 / 118`。
  - `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
    -> `artifacts/agent_evals/dashboard.md`。
  - `timeout 120s git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `100 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - 後續要用 same `118` cases rerun local primary / fallback x3，才可把真 local model claim 擴到這個
    apply-lock wrong-tool case。
  - 這不是 product-complete、ChatPanel 長時間真模型 workflow 或 Windows human acceptance。

### 16:35 Recipe reload capability gate

- 做了什麼：
  - 盤點剛新增的 `Reload Import Recipe` UI path，發現它仍共用 `_can_start_interpretation()`
    的 `scan_source` gate。
  - 先新增 focused UI regression，紅燈顯示 `reload_interpretation_recipe` capability disabled 時
    UI 仍進入 file dialog。
  - `_can_start_interpretation()` 現在可接 command name；recipe reload path 讀
    `CommandName.RELOAD_INTERPRETATION_RECIPE`，blocked title / fallback reason 也使用 recipe
    reload 語意。
  - 更新 current / UI architecture / validation / implementation log。
- 結果：
  - Recipe reload UI action 不再依賴 scan-source gate；未來 backend policy 分岔時 UI 會顯示
    正確 blocked reason。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_uses_reload_capability_gate -q`
    -> 初始紅燈進入 file dialog，實作後 pass。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_uses_reload_capability_gate tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_reviews_then_applies -q`
    -> `2 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_dataset_sidebar.py -q`
    -> `58 passed`。
  - `timeout 120s git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - 這支撐 UI capability boundary consistency；不是 full recipe reload semantic acceptance。

### 16:10 Apply interpretation raw-edit capability boundary

- 做了什麼：
  - 盤點剛新增的 Data Interpretation source-entry path 後，發現更大的 backend gap：
    `apply_interpretation` capability 只看 Data Interpretation validation，沒有套用 active
    pipeline 的 raw-edit blockers。
  - 先新增 focused regression，紅燈顯示已有 epoch state 時
    `policy.get(APPLY_INTERPRETATION).available` 仍為 `True`。
  - `build_capability_policy()` 現在把 `_raw_edit_blockers(state)` 加到
    `apply_interpretation` reasons。已有 epoch、dataset、trainer 或 locked raw data 時，apply
    會被 precondition 擋下，且不呼叫 `dataset.import_files()`。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - UI / agent / MCP 共用同一個 apply raw-mutation boundary；不能靠 agent/MCP 繞過 UI lock。
  - 這是 capability/autonomy safety slice，不是 mature import wizard completion。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_blocks_after_epoch_without_import_side_effect -q`
    -> 初始紅燈 `available is True`，實作後 pass。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_blocks_after_epoch_without_import_side_effect tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_preview_validate_requires_confirmation -q`
    -> `2 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/capabilities.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/capabilities.py tests/unit/backend/application/test_application_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 120s git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `100 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - 這支撐 apply mutation safety，不是 product completion。
  - 下一步繼續盤點 mutating commands 是否還有 UI-only blockers 或 weak visible blocked reason。

### 15:05 Dataset source-entry UI options

- 做了什麼：
  - 使用 `data-interpretation-reviewer` 檢查資料入口後，發現 Dataset sidebar 雖然以
    `Interpret Data Source` 為主，但實際 UI 仍只開 EEG file picker，folder / BIDS root /
    saved recipe 入口不可見。
  - 先新增 focused UI tests，紅燈為 `DatasetSidebar` 缺少 `import_folder_btn` /
    `reload_recipe_btn`，`DatasetActionHandler` 缺少 `import_folder_source()` /
    `reload_interpretation_recipe()`。
  - 新增 `Interpret Folder / BIDS` 和 `Reload Import Recipe` sidebar buttons。
  - `import_folder_source()` 走 `ScanSourceCommand` -> preview -> validate -> apply；
    `reload_interpretation_recipe()` 走 `ReloadInterpretationRecipeCommand` -> preview dialog ->
    optional re-preview / validate -> apply。folder/BIDS 和 recipe 入口沒有 legacy controller
    fallback。
  - 產生 automated sidebar evidence：`artifacts/ui/data-source-entry-options/`。
  - 更新 current / roadmap / now / UI architecture / validation / implementation log。
- 結果：
  - 使用者第一層 UI 可見 EEG file(s)、folder / BIDS root 和 saved recipe 三種 source entry。
  - 這補 source type visibility，不是 mature import wizard editor completion。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py::test_init_ui tests/unit/ui/dataset/test_dataset_sidebar.py::test_button_connections -q`
    -> 初始紅燈 `AttributeError: import_folder_btn`，實作後 `2 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_folder_source_uses_folder_or_bids_root tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_reviews_then_applies -q`
    -> 初始紅燈 missing methods，實作後 `2 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/dataset/test_panel.py -q`
    -> `63 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/actions.py XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_ui_misc.py tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/dataset/test_panel.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_ui_misc.py tests/unit/ui/dataset/test_dataset_sidebar.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - Artifact：`artifacts/ui/data-source-entry-options/data-source-entry-options.png` /
    `.json` / `.md`；visible buttons include `Interpret Data Source`,
    `Interpret Folder / BIDS`, `Reload Import Recipe`，screenshot nonblank。
  - `timeout 120s git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `99 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - Human desktop acceptance 仍未完成，不能把 automated sidebar replay 當 Windows click-through。
  - 下一步仍應聚焦 mature embedded label/anchor editor、recipe reload diff 和 human desktop
    acceptance；這個 slice 不標 product complete。

### 14:25 Data Interpretation session-state boundary cleanup

- 做了什麼：
  - 使用 `refactor-slicer` / `clean-code-reviewer` 檢查後，選 Data Interpretation 的
    session state / resolver / snapshot / label-import recipe recording 作為下一個 backend cleanup
    slice。
  - 先新增 focused tests，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_state`。
  - 新增 `DataInterpretationSessionState`，承接 scan/candidate/preview/validation/applied/recipe
    lifecycle stores、latest-id resolver、snapshot assembly、clear 和 post-load label import recipe
    state update。
  - `DataInterpretationCommandService` 改成委派 state/resolver/snapshot，只保留 scan /
    preview / validate / apply / save recipe / reload recipe command orchestration。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `DataInterpretationCommandService` 從約 `514` 行降到 `297` 行。
  - 新增 `data_interpretation_state.py` 為 `385` 行，邊界是 lifecycle state truth，不是新的
    command dispatcher。
  - UI / agent / MCP command name、payload 和 `CommandResult` contract 未變。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_state.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_state.py tests/unit/backend/application/test_data_interpretation_service.py -q`
    -> `4 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation_state.py XBrainLab/backend/application/data_interpretation_service.py tests/unit/backend/application/test_data_interpretation_state.py tests/unit/backend/application/test_data_interpretation_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation_state.py XBrainLab/backend/application/data_interpretation_service.py tests/unit/backend/application/test_data_interpretation_state.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `99 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 120s git diff --check`
    -> pass。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - 這支撐 Data Interpretation internal boundary cleanup，不是 mature import wizard completion。
  - 下一步可繼續檢查 UI / agent / MCP 是否還有 controller-private fallback 或 legacy
    data-entry 心智模型殘留；這個 slice 不標 product complete。

### 13:10 State / query service boundary cleanup

- 做了什麼：
  - 延續 backend cleanup，選 state snapshot assembly 和 read-only `query_state` diagnostics 作為
    focused slice。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.state_service`。
  - 新增 `StateSnapshotService`，承接 raw / preprocess / epoch / dataset / training /
    evaluation / visualization / interpretation snapshot assembly 和 safe helper functions。
  - 新增 `QueryStateCommandService`，承接 `query_state` 的 state / data_lists / data_summary /
    preprocess_diagnostics / smart_filter_suggestions diagnostics。
  - `ApplicationService.get_state()` 只委派 snapshot builder；handler map 改成委派
    `QueryStateCommandService`。
  - 修正拆分中發現的命名風險：避免 instance attribute `query_state` 遮蔽 public
    `ApplicationService.query_state()` wrapper。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `945` 行降到 `458` 行。
  - `StateSnapshotService` / `QueryStateCommandService` 同檔為 `575` 行；這檔仍偏大，但邊界已
    從 command dispatch 分離，後續若需要可再拆 snapshot builder helpers。
  - `ApplicationService` 主要保留 command dispatch、capability / confirmation gate、result
    envelope 和 public compatibility wrappers。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/state_service.py tests/unit/backend/application/test_state_service.py tests/unit/backend/application/test_application_service.py`
    -> 初次發現 test import / mutable fixture class attributes，修正後 pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/state_service.py tests/unit/backend/application/test_state_service.py`
    -> 初次發現 test fixture snapshot 欄位和 payload narrowing 問題，修正後為
    `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `46 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `78 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - 這支撐 state/query handler isolation，不是 product completion。
  - 下一步應檢查 UI / agent / MCP 是否還有產品主路徑旁路，或轉回 Data Interpretation wizard /
    human desktop acceptance / long-running local assistant blockers。

### 12:35 Preprocess command service boundary cleanup

- 做了什麼：
  - 延續 backend cleanup，選 preprocessing operations / standard preprocess / `create_epoch`
    作為 focused slice，不碰 `query_state` / state snapshot。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.preprocess_service`。
  - 新增 `PreprocessCommandService`，承接 bandpass / notch / resample / normalize /
    rereference / channel selection / standard preprocess / create epoch。
  - 保留 `set_montage` preprocess operation 的 UI confirmation boundary；真正 confirmed montage
    apply 仍在 `AnalysisCommandService` 的 `apply_montage` command。
  - `ApplicationService` 的 handler map 改成窄委派到 preprocess service；對外 command name、
    capability policy 和 `CommandResult` contract 不變。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `1021` 行降到 `945` 行。
  - `PreprocessCommandService` 為 `107` 行。
  - preprocess / epoch handler 不再直接堆在 `ApplicationService`；`query_state` 和 state
    snapshot helpers 仍留在 `ApplicationService`。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_preprocess_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/preprocess_service.py tests/unit/backend/application/test_preprocess_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/preprocess_service.py tests/unit/backend/application/test_preprocess_service.py`
    -> 初次發現 test fixture `rate` 應為 `int | None`，修正後為 `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_preprocess_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `48 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `76 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
- 接續 / 本輪剩餘：
  - 這支撐 preprocess / epoch handler isolation，不是 product completion。
  - 下一個 backend cleanup slice 應評估 query/state snapshot boundary，或暫停 backend cleanup
    轉回 UI / import wizard / human verification blocker。

### 12:05 Data table command service boundary cleanup

- 做了什麼：
  - 延續 backend cleanup，選 `update_metadata` / `apply_smart_parse` / `remove_files` 作為
    focused slice。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.data_table_service`。
  - 新增 `DataTableCommandService`，承接 loaded-data table metadata mutation、smart parse
    normalization 和 remove-files count delta diagnostics。
  - `ApplicationService` 的 handler map 改成窄委派到 data-table service；對外 command name、
    capability policy 和 `CommandResult` contract 不變。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `1107` 行降到 `1021` 行。
  - `DataTableCommandService` 為 `114` 行。
  - loaded-data table mutation 不再直接堆在 `ApplicationService`；`query_state`、preprocess /
    epoch handlers 和 state snapshot helpers 仍留在 `ApplicationService`。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_table_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/data_table_service.py tests/unit/backend/application/test_data_table_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/data_table_service.py tests/unit/backend/application/test_data_table_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_table_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `48 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `72 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這支撐 loaded-data table handler isolation，不是 product completion。
  - 下一個 backend cleanup slice 應評估 preprocess / epoch service 或 query/state snapshot
    service；不要再把新 workflow 塞回 `ApplicationService`。

### 11:45 Data compatibility command service boundary cleanup

- 做了什麼：
  - 延續 backend cleanup，選舊 `load_data` / `attach_labels` / `import_labels` compatibility
    path 作為 focused slice。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.data_compatibility_service`。
  - 新增 `DataCompatibilityCommandService`，承接 legacy load failure mapping、post-load attach
    labels、label import plan、default event-name mapping 和 Data Interpretation recipe trace update。
  - `ApplicationService` 的 handler map 改成窄委派到 compatibility service；Data Interpretation
    主線仍在 `DataInterpretationCommandService`。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `1296` 行降到 `1107` 行。
  - `DataCompatibilityCommandService` 為 `241` 行。
  - 舊 command names 仍可用，但已被明確隔離為 compatibility boundary。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_compatibility_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/data_compatibility_service.py tests/unit/backend/application/test_data_compatibility_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/data_compatibility_service.py tests/unit/backend/application/test_data_compatibility_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_compatibility_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `47 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `68 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這支撐 legacy data / label compatibility handler isolation，不是 product completion。
  - `query_state`、metadata / smart parse / remove file 和 preprocess / epoch handlers 仍在
    `ApplicationService`；是否繼續拆分要看下一輪 cleanup risk。

### 11:05 Lifecycle command service boundary cleanup

- 做了什麼：
  - 延續 backend cleanup，選 `reset_preprocess` / `reset_session` / `new_session` 作為 focused
    slice，不碰 legacy data / label compatibility。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.lifecycle_service`。
  - 新增 `LifecycleCommandService`，承接 reset preprocess、reset session、new session、
    downstream rollback、reset-time training config clear 和 interpretation state clear。
  - `ApplicationService` 的 handler map 改成窄委派到 lifecycle service；reset preprocess 的
    dataset generator / trainer rollback 仍委派給 `DatasetGenerationCommandService`，避免重建
    第二套 rollback truth。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `1352` 行降到 `1296` 行。
  - `LifecycleCommandService` 為 `109` 行。
  - 對外 command names、confirmation policy、rollback diagnostics 和 `CommandResult` contract
    沒變。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_lifecycle_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/lifecycle_service.py tests/unit/backend/application/test_lifecycle_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/lifecycle_service.py tests/unit/backend/application/test_lifecycle_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_lifecycle_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `47 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `65 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這支撐 lifecycle reset handler boundary，不是 product completion。
  - 下一輪 backend cleanup 仍應處理 legacy data / label compatibility handlers；`query_state`
    也仍在 `ApplicationService`，但目前屬 cross-cutting query。

### 10:25 Dataset generation command service boundary cleanup

- 做了什麼：
  - 延續 backend cleanup，選 `generate_dataset` / `clear_datasets` 作為下一個 focused slice，
    不碰 reset lifecycle 或 legacy data / label compatibility。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.dataset_generation_service`。
  - 新增 `DatasetGenerationCommandService`，承接 split config、dataset generation、split audit、
    audit failure rollback、dataset cleanup 和 dataset split summary。
  - `ApplicationService` 的 handler map 改成窄委派到 dataset generation service；reset preprocess
    rollback 也只呼叫該 service 的 state restore helper，不再直接操作 dataset generator /
    trainer rollback 細節。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `1552` 行降到 `1352` 行。
  - `DatasetGenerationCommandService` 為 `233` 行。
  - 對外 command names、capability policy、split audit diagnostics 和 `CommandResult` contract
    沒變。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_dataset_generation_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/dataset_generation_service.py tests/unit/backend/application/test_dataset_generation_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/dataset_generation_service.py tests/unit/backend/application/test_dataset_generation_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_dataset_generation_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `47 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `62 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這支撐 dataset generation handler boundary，不是 product completion。
  - 下一輪 backend cleanup 仍應處理 reset lifecycle / legacy compatibility handlers。

### 09:45 Training command service boundary cleanup

- 做了什麼：
  - 依 refactor gate 延續 backend cleanup，選 training lifecycle / configuration 作為下一個
    focused slice，不碰 dataset generation、reset rollback 或 UI。
  - 先新增 focused test，紅燈為
    `ModuleNotFoundError: XBrainLab.backend.application.training_service`。
  - 新增 `TrainingCommandService`，承接 `configure_training`、`train`、`stop_training`、
    `clear_training_history` 和 reset-time training config clear。
  - `ApplicationService` 的 handler map 改成窄委派到 training service；public convenience methods
    仍保留，但只建立 typed command 再進 `execute()`。
  - 移出 model class resolve、optimizer / device / evaluation-option resolve、training option
    snapshot 和 model-name snapshot。
  - 更新 current / roadmap / now / backend architecture / validation / implementation log。
- 結果：
  - `ApplicationService` 從 `1719` 行降到 `1552` 行。
  - `TrainingCommandService` 為 `217` 行。
  - 對外 command names、capability policy 和 `CommandResult` contract 沒變。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/training_service.py tests/unit/backend/application/test_training_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/training_service.py tests/unit/backend/application/test_training_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `47 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `59 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這支撐 training command handler boundary，不是 product completion。
  - 下一輪 backend cleanup 仍應處理 dataset generation / reset lifecycle / legacy compatibility
    handlers。

### 09:20 Analysis command service boundary cleanup

- 做了什麼：
  - 依 refactor gate 選低風險 analysis / visualization slice，不同時碰 UI、agent runtime 或
    training lifecycle。
  - 先新增 focused test，紅燈為 `ModuleNotFoundError: XBrainLab.backend.application.analysis_service`。
  - 新增 `AnalysisCommandService`，承接 `evaluate`、`visualize`、`saliency` 和 confirmed
    `apply_montage` handler。
  - `ApplicationService` 的 handler map 改成窄委派到 analysis service；`query_state` 仍留在
    `ApplicationService`，避免 cross-cutting state/capability query 形成第二套 truth。
  - 移出 saliency parameter normalization 和 analysis JSON-safe metric conversion。
  - 更新 current / roadmap / now / architecture / implementation log。
- 結果：
  - `ApplicationService` 從 `1912` 行降到 `1719` 行。
  - `AnalysisCommandService` 為 `268` 行。
  - 對外 command names、capability policy 和 `CommandResult` contract 沒變。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py -q`
    -> 初始紅燈 `ModuleNotFoundError`，符合 test-first 預期。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py -q`
    -> `46 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `56 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這支撐 analysis / visualization handler boundary，不是 product completion。
  - 下一輪 backend cleanup 仍應處理 training / dataset generation / reset lifecycle / legacy
    compatibility handlers。

## 2026-05-04

### 21:12 Backend ApplicationService boundary cleanup

- 做了什麼：
  - 依 backend architecture steering 和 clean-code review，停止把 Data Interpretation 邏輯繼續堆進
    `ApplicationService`。
  - 新增 `DataInterpretationCommandService`，承接 scan / preview / validate / apply / save recipe /
    reload recipe lifecycle state、snapshot、clear 和 recipe label-import state 更新。
  - 新增 `DataInterpretationApplyService`，承接 reviewed metadata apply 和 reviewed label carrier
    apply side effects。
  - `ApplicationService` 的 Data Interpretation commands 改成窄委派；它仍負責 command dispatch、
    capability / confirmation gate、state/result envelope 和 error mapping。
  - 補 focused unit tests，直接驗證 Data Interpretation service 的 scan / preview / validate /
    clear，以及 apply 後 reviewed metadata、notification、label-import recipe state 同步。
  - 更新 `current.md`、`architecture/backend.md`、`architecture/agent.md`、`planning/now.md`、
    `planning/roadmap.md`、`validation/README.md` 和 `implementation_log.md`。
- 結果：
  - `ApplicationService` 從約 `2799` 行降到 `1912` 行。
  - `DataInterpretationCommandService` 第二刀後為 `514` 行。
  - `DataInterpretationApplyService` 為 `446` 行。
  - UI / agent / headless / MCP 對外仍走同一套 `ApplicationService.execute()` command spine。
- 證據：
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/backend/application/data_interpretation_apply.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/backend/application/data_interpretation_apply.py tests/unit/backend/application/test_data_interpretation_service.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `54 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 接續 / 本輪剩餘：
  - 這是 backend architecture cleanup slice，不是 product complete。
  - `ApplicationService` 仍有 training / visualization / analysis / lifecycle / legacy compatibility
    handlers；下一輪應繼續 handler/service 化。
  - Data Interpretation wizard 仍需要 mature embedded label / anchor editor，不能用 post-load
    compatibility label import 包裝成新資料入口完成。

### 20:43 MCP Inspector GUI click-through baseline

- 做了什麼：
  - 新增 `scripts/dev/capture_mcp_inspector_gui_walkthrough.py`。
  - 腳本啟動 Windows official MCP Inspector、用 Windows Chrome headless + CDP 點擊
    `Connect` 和 `List Tools`，再保存 JSON / Markdown / screenshot artifact。
  - 補 `tests/unit/scripts/test_capture_mcp_inspector_gui_walkthrough.py`，驗證 token redaction、
    WSL -> Windows path 轉換、connected checks、可見工具 checks 和 Markdown claim boundary。
  - 修正 runtime 驗證：Inspector GUI 會顯示 human labels，例如 `Scan Source`，不是
    snake_case `scan_source`；script 現在把可見 label 對回 canonical tool name。
- 結果：
  - `artifacts/mcp/inspector-gui-walkthrough.json` status `passed`。
  - 可見狀態包含 `Connected`、`Disconnect`、`xbrainlab`、`wsl.exe`、prepared runtime wrapper
    args、Tools / List Tools。
  - 可見 Data Interpretation tools：
    - `scan_source` / `Scan Source`
    - `preview_interpretation` / `Preview Interpretation`
    - `validate_interpretation` / `Validate Interpretation`
    - `apply_interpretation` / `Apply Interpretation`
  - post-run 檢查沒有殘留 Windows Inspector `node.exe` 或 XBrainLab MCP Chrome process。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_mcp_inspector_gui_walkthrough.py -q`
    -> `5 passed`。
  - targeted `ruff check` / `ruff format --check` -> pass。
  - `poetry run basedpyright scripts/dev/capture_mcp_inspector_gui_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 210s poetry run python scripts/dev/capture_mcp_inspector_gui_walkthrough.py --output-dir artifacts/mcp --timeout-seconds 150`
    -> exit `0`。
  - `artifacts/mcp/inspector-gui-connected.png`
  - `artifacts/mcp/inspector-gui-walkthrough.json`
  - `artifacts/mcp/inspector-gui-walkthrough.md`
- 接續 / 本輪剩餘：
  - 這是 automated Inspector GUI click-through baseline，不是 human GUI session、HTTP transport、
    long-running training through MCP、full MCP client certification、Windows Desktop 真人啟動或
    product completion。

### 20:31 Records scope cleanup

- 做了什麼：
  - 依使用者回饋，重新切分 `implementation_log.md` 和 `worklog.md` 的職責。
  - `implementation_log.md` 改為高層產品狀態快照：track 狀態、claim boundary、evidence 入口、
    下一手重點。
  - `worklog.md` 保留細節流水帳：TDD 紅燈、驗證命令、artifact 細節、失敗嘗試。
  - `roadmap.md` 同步更新已完成 baseline 與仍未完成的 product tracks。
- 結果：
  - 不再把 implementation log 寫成第二份 worklog。
  - roadmap 現在可直接掃描 completed baseline / active blockers，不會停留在過期的
    「Data Interpretation 尚未開始」狀態。
- 證據：
  - `rg -n "尚未開始|正式 local LLM eval runner 和足量 cases 尚未完成|實作紀錄與流水帳|BIDS-ish" docs/planning/roadmap.md docs/records docs/index.md`
    -> roadmap / index 無過期命中；只剩本 worklog 的歷史描述。
  - `git diff --check -- docs/records/implementation_log.md docs/records/worklog.md docs/planning/roadmap.md docs/index.md`
    -> pass。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - MCP Inspector GUI script / test 目前仍是未提交施工中變更，不納入這個 docs scope claim。

### 18:42 Post-load label import target context

- 做了什麼：
  - 補 TDD 紅燈：`ImportLabelDialog(target_files=[...])` 應顯示 labels 會套到哪些 loaded EEG
    files，`DatasetActionHandler.import_label()` 應把 selected target files 傳進 dialog。
  - `ImportLabelDialog` title 改為 `Add Labels to Loaded Data`。
  - dialog 上方新增 target summary，列出最多前三個 target EEG file，並顯示 target count。
  - dialog 新增 recipe impact note：若目前有 active data interpretation，成功 import 會更新
    import recipe trace。
- 結果：
  - 初跑 focused tests 先因 `target_files` 參數不存在、action 未傳 target context 而失敗。
  - compatibility label flow 現在不再讓使用者只看到 label file picker；使用者能看到 labels
    會套到哪些 loaded EEG files。
- 證據：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py::test_import_label_dialog_shows_target_context tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_passes_target_context_to_dialog -q`
    -> first run failed as expected, then `2 passed`。
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_ui_misc.py::TestImportLabelDialog -q`
    -> `83 passed`。
  - targeted `ruff` -> pass。
  - targeted `ruff format --check` -> pass。
  - production touched-file `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 這是 post-load compatibility label flow target visibility，不是完整 embedded label wizard。
  - 仍不能宣稱 raw-event-anchor-specific GDF/MAT alignment、真人 Windows click-through、
    interactive desktop 3D、MCP Inspector / release config 或 thesis-ready local LLM evidence。

### 18:35 Data Interpretation label carrier matched-EEG UI

- 做了什麼：
  - 補 UI regression：label carrier review row 應顯示 matched EEG file。
  - `DataInterpretationPreviewDialog` label carrier table 新增 `Matched EEG` 欄。
  - 單檔 direct match 或多檔唯一 normalized stem match 顯示目標 EEG 檔名；無法唯一對應時顯示
    `Needs review`。
  - 更新 dialog choice extraction column index，避免新增欄位後把 label field / anchor 寫到錯欄。
  - 更新 `capture_data_interpretation_replay.py`，讓 replay screenshot 前填入正確欄位。
- 結果：
  - 初跑 UI test 先因第 2 欄仍是 `MAT` 而失敗，實作後通過。
  - Replay JSON 現在顯示 `product_replay_events.tsv` 對到 `product_replay_raw.fif`，且
    reviewed label choices / `label_apply.status=applied` 仍正確。
- 證據：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_label_carrier_review -q`
    -> first run failed as expected, then `1 passed`。
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `6 passed`。
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `52 passed`。
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`。
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - targeted `ruff` -> pass。
  - targeted `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 仍不能宣稱 full embedded post-load label import wizard、raw-event-anchor-specific GDF/MAT
    alignment、真人 Windows click-through、interactive desktop 3D、MCP Inspector / release config
    或 thesis-ready local LLM evidence。

### 18:32 Data Interpretation multi-file sequence label mapping

- 做了什麼：
  - 補 TDD 紅燈：兩個 loaded raw files 各自有 reviewed MAT `classlabel` carrier 時，
    `apply_interpretation` 應以 file stem 建立 mapping，並逐檔呼叫既有
    `apply_labels_legacy`。
  - `_apply_interpretation_label_carriers()` 的多檔 mapping 現在同時支援 timestamp mode 和
    sequence mode。
  - sequence mode 多檔時不串接 labels；每個 target 只套用自己 matched carrier 的 labels。
  - 補 negative regression：兩個 raw files 只有 generic `labels.mat` 時必須 skipped，且不可呼叫
    `apply_labels_legacy`。
- 結果：
  - 初跑 positive test 先看到 `label_apply.status=skipped`，實作後 `applied`。
  - reviewed MAT / TXT trial-order labels 已有安全多檔 backend path。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem -q`
    -> first run failed as expected, then passed。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
    -> `2 passed`。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
    -> `65 passed`。
  - targeted `ruff` -> pass。
  - targeted `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 仍不能宣稱 raw-event-anchor-specific GDF/MAT alignment、generic folder-level label
    disambiguation、embedded label wizard UI、真人 Windows click-through、interactive desktop 3D、
    MCP Inspector / release config 或 thesis-ready local LLM evidence。

### 18:25 Data Interpretation multi-file timestamp label mapping

- 做了什麼：
  - 補 TDD 紅燈：兩個 loaded raw files 各自有 reviewed `_events.tsv` carrier 時，
    `apply_interpretation` 應該用 file stem 建立 mapping 並一次 `apply_labels_batch`，
    不能再因多 carrier / 多 loaded files 直接 skipped。
  - `_apply_interpretation_label_carriers()` 保留既有單檔 direct mapping；多檔 timestamp mode
    只在每個 loaded EEG file 都能唯一對應 reviewed carrier 時才自動套用。
  - 新增 normalized stem matching，會移除 `_events`、`_raw`、`_labels` 等 suffix。
  - 補 negative regression：兩個 raw files 只有 generic `events.tsv` 時必須 skipped，且不可呼叫
    `apply_labels_batch`。
- 結果：
  - 初跑 positive test 先看到 `label_apply.status=skipped`，實作後 `applied`。
  - BIDS-style per-run timestamp labels 現在可支撐安全多檔 mapping。
  - ambiguous folder-level events 仍不猜測。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem -q`
    -> first run failed as expected, then `1 passed`。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier -q`
    -> `4 passed`。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
    -> `63 passed`。
  - targeted `ruff` -> pass。
  - targeted `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 仍不能宣稱 generic folder-level events disambiguation、多檔 MAT / TXT sequence mapping、
    raw-event-anchor-specific GDF/MAT alignment、embedded label wizard UI、真人 Windows
    click-through、interactive desktop 3D、MCP Inspector / release config 或 thesis-ready local LLM
    evidence。

### 18:15 Data Interpretation shared state snapshot propagation

- 做了什麼：
  - 補 TDD 紅燈：reviewed MAT label carrier / class map apply 後，
    `ApplicationStateSnapshot.interpretation` 和 `query_state` 應暴露 reviewed
    `label_carrier_plan`、`format_capabilities`、`event_roles` 和 `class_map`。
  - `InterpretationStateSnapshot` 新增上述欄位。
  - `_interpretation_snapshot()` 以 applied interpretation 為優先，其次 candidate / preview /
    scan，建立同一份 import truth。
  - 補 automation / MCP envelope regression：`execute_automation_payload()` serialized state 要
    包含 label carrier plan / format capabilities。
  - 補 agent surface regression：ApplicationService-backed `query_state` tool 要傳出同一份
    interpretation review truth。
- 結果：
  - 初跑 focused test 先因 `InterpretationStateSnapshot` 沒有 `label_carrier_plan` attribute
    失敗，實作後通過。
  - UI / recipe、agent、headless / MCP-shaped envelope 不再因 state snapshot 少欄位而看不同
    Data Interpretation truth。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth -q`
    -> first run failed as expected, then `1 passed`。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth tests/unit/backend/application/test_automation.py::test_execute_automation_payload_state_contains_interpretation_review_truth tests/unit/llm/tools/test_application_surface.py::test_query_state_tool_surfaces_interpretation_review_truth -q`
    -> `3 passed`。
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
    -> `61 passed`。
  - targeted `ruff` -> pass。
  - targeted `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 仍不能宣稱 mature embedded label import wizard、多檔 label mapping、raw-event-anchor-specific
    MAT/GDF alignment、真人 Windows launcher click-through、interactive desktop 3D、MCP Inspector /
    release config 或 thesis-ready local LLM evidence。

### 18:06 Usage-refresh handoff after import label apply

- 做了什麼：
  - 依使用者要求刷新 usage refresh 交接：
    - `artifacts/goal/handoff-2026-05-04-usage-refresh.md`
    - `artifacts/goal/continuation-2026-05-04-product-completion.md`
  - 交接更新到最新 local product commit：
    - `0da24db backend: apply reviewed sequence labels during import`
    - `626b606 backend: apply reviewed timestamp labels during import`
    - `15c242d backend: surface import format boundaries`
    - `f49af63 ui: add label carrier review to import wizard`
- 結果：
  - 交接明確保存 protected dirty files 只應是 `.vscode/settings.json` 和 root `settings.json`。
  - 交接明確保存不要重做已完成的 ChatPanel training completion、VisualizationPanel Matplotlib
    render、headless 3D blocked UX、label carrier review、format boundaries 和 reviewed label apply。
  - 下一手優先處理 Data Interpretation import truth 是否進入 shared
    `ApplicationStateSnapshot.interpretation`，讓 agent / headless / MCP / `query_state` 看見
    `label_carrier_plan` 和 `format_capabilities`。
- 證據：
  - `git status --short` 當下只顯示 protected workspace settings 兩檔在既有 dirty 狀態。
  - `git diff --check` -> pass。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
- 接續 / 本輪剩餘：
  - Goal 仍不可標 complete。
  - 不能宣稱 mature embedded label import wizard、多檔 label mapping、raw-event-anchor-specific
    MAT/GDF alignment、真人 Windows launcher click-through、interactive desktop 3D、MCP Inspector /
    release config 或 thesis-ready local LLM evidence。

### 11:44 ChatPanel multi-turn compact tool history

- 做了什麼：
  - 新增 `scripts/dev/capture_chatpanel_local_workflow_walkthrough.py`，用真 MainWindow /
    ChatPanel / local model 連送兩個 prompts。
  - 首次 run 暴露 blocker：turn 1 `query_state` 成功後，完整 state JSON 放進 conversation
    history，turn 2 prompt 約 `10.7k` input tokens，Phi-4 mini generation timeout。
  - 修改 `LLMController._format_tool_output()`，ToolCommandResult 給下一輪 LLM 的內容改成 compact
    payload：message、capability、`state_summary`、small diagnostics；不再放 full state /
    raw_result。
  - 新增 controller regression，確保 tool history 不含 raw state / raw_result。
- 結果：
  - 重新跑 multi-turn walkthrough passed。
  - turn 1 executed tool：`query_state` `ok`。
  - turn 2 在同一 conversation 中正常回答 preprocessing follow-up，run log input tokens 約 `2.46k`，
    duration 約 `945ms`。
  - visible transcript 無 raw `Tool Output`、schema、traceback，UI 回到 idle。
- 證據：
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-ready.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-turn-1.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-turn-2.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.json`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.md`
  - `timeout 520s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_workflow_walkthrough.py --output-dir artifacts/ui/chatpanel-local-workflow --timeout-seconds 480`
    -> exit `0`
  - targeted controller tests -> `2 passed`
  - workflow script renderer test -> `1 passed`
- 接續 / 本輪剩餘：
  - 這是 basic two-turn continuity，不是長時間 autonomous tool-command chain。
  - 真資料 import -> preprocess -> epoch -> train 的 ChatPanel 操作鏈仍未完成。

### 11:26 Windows launcher automated command walkthrough

- 做了什麼：
  - `xbrainlab_wsl_launcher.ps1` 新增 `XBRAINLAB_LAUNCHER_SMOKE=startup` mode，透過 launcher
    path 進 WSL，bounded 執行 `run.py --model local` startup smoke。
  - 新增 `scripts/dev/capture_windows_launcher_walkthrough.py`，依序跑 Desktop `.cmd` smoke、
    PowerShell WSL stdout/stderr smoke、PowerShell startup smoke，並保存 JSON / Markdown artifact。
  - 新增 helper unit tests，保護 launcher log path parse 和 Markdown claim boundary。
- 結果：
  - artifact status `passed`。
  - Desktop command 指向 active repo `/mnt/d/workspace_v2/projects/lab/XBrainLab`。
  - PowerShell launcher 可透過 `wsl.exe` 進 WSL，stdout / stderr 都會 mirror。
  - startup smoke 經 launcher path 看到 `MainWindow initialized`，並由 timeout 收束。
  - 最新 artifact 已補 startup geometry diagnostics checks：screen count、screen detail、
    splash geometry、main-window geometry 都為 `True`。
- 證據：
  - `artifacts/launcher/windows-launcher-walkthrough.json`
  - `artifacts/launcher/windows-launcher-walkthrough.md`
  - launcher log：`/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/launcher-20260504-193942.log`
  - `timeout 180s poetry run python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher --startup-timeout 150`
    -> exit `0`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_windows_launcher_walkthrough.py -q`
    -> `3 passed`
  - targeted `ruff check` / `ruff format --check` clean。
  - `poetry run basedpyright scripts/dev/capture_windows_launcher_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant。
  - `git diff --check` -> pass。
- 接續 / 本輪剩餘：
  - 這是 automated command walkthrough，不是真人 Desktop click-through 或 packaged release approval。
  - 真雙螢幕/WSLg 桌面點擊、MCP Inspector GUI、完整 release packaging 仍未完成。

### 17:37 Data Interpretation label carrier review slice

- 做了什麼：
  - 先補 TDD 紅燈：
    - backend preview / apply / recipe 應保存 MAT `classlabel`、`cue_onset`、time model 和
      granularity 選擇。
    - wizard 應顯示可編輯 label carrier review rows，並回傳 `label_carrier_choices`。
  - `InterpretationCandidate` / `InterpretationPreview` 新增 `label_carrier_plan` /
    `label_carrier_preview`。
  - backend 會為 MAT、CSV / TSV、BIDS `events.tsv`、TXT carrier 建立 label field / MAT
    variable、anchor、time model、granularity 候選與 selected values。
  - `PreviewInterpretationCommand(choices=...)` 可接 `label_carrier_choices`；apply / save recipe
    會保存 reviewed `label_carrier_plan`，recipe trace 會寫 `choices:label_carriers`。
  - `DataInterpretationPreviewDialog` 新增 label carrier review table，顯示 carrier、format、
    label field、anchor、time、granularity；Dataset action 既有 re-preview / re-validate path
    會套用這些 choices。
  - UI replay 改成 folder source + `product_replay_events.tsv`，artifact 會記錄可見
    `label_carrier_rows` 與 reviewed choices。
- 結果：
  - TDD 紅燈確認過：
    - backend test 先因缺 `label_carrier_preview` 失敗。
    - dialog test 先因缺 `label_carrier_tree` 失敗。
  - UI replay JSON 顯示 `trial_type` / `onset` / `seconds` / `trial` label carrier review row，
    applied interpretation 保存同一份 plan。
  - backend unit test 覆蓋 MAT `classlabel` / `cue_onset` 寫入 `ImportRecipe.label_carrier_plan`
    和 `choices:label_carriers` trace。
- 證據：
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `33 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `50 passed`
  - targeted `ruff` -> `PASS`
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 這是 first-pass format-specific label carrier review，不是完整 post-load label import
    內嵌 wizard。
  - 仍缺 all-format manual compatibility matrix、真人 Windows launcher click-through、MCP
    Inspector GUI / release config。

### 17:46 Data Interpretation format capability boundaries

- 做了什麼：
  - 先補 TDD 紅燈：
    - backend scan / preview 應輸出 GDF、EDF、EEGLAB、BrainVision、MAT labels、BIDS events、
      XDF / LSL 等 format capability rows。
    - dialog review notes 應顯示 format capabilities，且可見文字不能直接露出 raw
      `needs_review`。
  - `ScanResult` / `InterpretationCandidate` / `InterpretationPreview` /
    `AppliedInterpretation` / `ImportRecipe` 新增 `format_capabilities`。
  - scan 會對 GDF、EDF / BDF、EEGLAB `.set`、BrainVision `.vhdr` / `.vmrk`、MNE FIF、MAT
    labels、CSV / TSV labels、BIDS `events.tsv`、TXT labels 和 XDF / LSL 建立 supported /
    needs-review / blocked boundary。
  - XDF / LSL 目前明確標成 blocked，訊息會要求使用者先轉成 supported EEG format 或提供
    prepared recipe；若同一 folder 還有 supported EEG，workflow 不會整個 blocked，但會 warning。
  - `DataInterpretationPreviewDialog` review notes 新增 `Format capabilities` section，並把
    backend status 轉成人能讀的 `needs review`。
  - replay JSON 新增 `review_notes`，保存可見 format boundary text。
- 結果：
  - TDD 紅燈確認過：
    - backend test 先因缺 `format_capabilities` 失敗。
    - dialog test 先因 review notes 沒有 `Format capabilities` 失敗。
  - UI replay JSON 顯示 BIDS events `needs review`、MNE FIF `supported`，且保留 label
    carrier rows。
- 證據：
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `34 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `51 passed`
  - targeted `ruff` -> `PASS`
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 這是 capability boundary display，不是 XDF stream parser 或 full all-format import matrix。
  - 仍缺完整 post-load label import 內嵌 wizard、真人 Windows launcher click-through、MCP
    Inspector GUI / release config。

### 17:56 Data Interpretation reviewed timestamp label apply

- 做了什麼：
  - 先補 TDD 紅燈：
    - `load_label_file()` 應接受 reviewed MAT variable、TSV label column 和 anchor column。
    - `apply_interpretation` 在已確認 reviewed timestamp label carrier 時應自動套用 labels，
      並更新 applied interpretation 的 `label_imports` / recipe trace。
  - `load_label_file(filepath, label_field=..., anchor=...)` 支援：
    - MAT selected variable。
    - CSV / TSV / BIDS events selected label / anchor columns，輸出 timestamp-style label dicts。
  - `ApplicationService._handle_apply_interpretation()` 現在會在 narrow safe path 自動套用
    labels：
    - 單一 loaded EEG file。
    - 單一 reviewed timestamp CSV / TSV / BIDS events carrier。
    - interpretation 已確認。
    - time model 是 `seconds` 或 `relative_time`。
  - 成功後會呼叫既有 `dataset.apply_labels_batch()`，再走
    `_record_label_import_for_recipe()` 更新 `label_imports` 和 `label_import:timestamp:<n>` trace。
  - UI replay artifact 已刷新並顯示 `label_apply.status=applied`。
- 結果：
  - TDD 紅燈確認過：
    - loader tests 先因 `label_field` 參數不存在失敗。
    - application test 先因缺 `label_apply` diagnostics 失敗。
  - replay JSON 顯示 timestamp label carrier 成功套用到 synthetic FIF source。
- 證據：
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `60 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `51 passed`
  - targeted `ruff` -> `PASS`
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 這不是 MAT sequence auto-apply，也不是多檔 label mapping。
  - 仍缺完整 post-load label import 內嵌 wizard、全格式人工 compatibility matrix、真人
    Windows launcher click-through、MCP Inspector GUI / release config。

### 18:02 Data Interpretation reviewed MAT/TXT sequence label apply

- 做了什麼：
  - 補 TDD 紅燈：reviewed MAT `classlabel` + trial-order + class map 的 interpretation apply 應該
    套用 external labels，而不是只保存 recipe plan。
  - `_apply_interpretation_label_carriers()` 新增 sequence path：
    - 單一 loaded EEG file。
    - 單一 reviewed MAT / TXT carrier。
    - time model 是 `trial_order`。
    - granularity 是 `trial`。
    - class map 已確認。
  - 成功後呼叫既有 `dataset.apply_labels_legacy()`，並透過 `_record_label_import_for_recipe()`
    寫入 `label_import:legacy:<n>`。
- 結果：
  - MAT sequence test 先看到 `label_apply.status=skipped`，實作後改為 `applied / legacy`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier -q`
    -> `2 passed`
- 接續 / 本輪剩餘：
  - 仍不支撐 raw-event-anchor-specific GDF/MAT alignment 或多檔 label mapping。
  - 仍缺完整 post-load label import 內嵌 wizard、全格式人工 compatibility matrix、真人
    Windows launcher click-through、MCP Inspector GUI / release config。

### 11:17 Data Interpretation metadata / class-map editor slice

- 做了什麼：
  - backend `PreviewInterpretationCommand(choices=...)` 接 `metadata_overrides`、`class_map` 和
    `event_roles`。
  - metadata override 會標成 `user_override` / `safe`，並寫入 `metadata_override:<field>` trace。
  - `AppliedInterpretation` / `ImportRecipe` 會保存 event roles 和 class map。
  - `DataInterpretationPreviewDialog` metadata review cells 可編輯 subject / session / task / run；
    class-map rows 可編輯 meaning。
  - Dataset action 會在 apply 前用 dialog choices re-preview / re-validate，然後 apply 新 candidate。
  - replay helper 會在 screenshot 前填入 `S01`、`session-01`、`motor-imagery`，並保存
    `review_choices`。
- 結果：
  - UI replay JSON 顯示 `metadata_overrides`，reviewed preview / apply path 保留
    `metadata_override` recipe trace。
  - recipe 現在可保存 metadata override 與 class map，不再只是 baseline preview。
- 證據：
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `49 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q` -> `37 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `1 passed`
- 接續 / 本輪剩餘：
  - 仍不是 format-specific label column / MAT variable / anchor editor。
  - label import 仍未內嵌進 wizard；Windows launcher、MCP Inspector、真人 click-through 仍未完成。

### 11:03 ChatPanel local tool-command walkthrough

- 做了什麼：
  - 修正 `AgentManager` 對 `Tool` sender 的處理：raw/internal tool output 仍隱藏到低噪音 notice，
    但已整理成使用者語言的 tool summary 會進入 visible transcript。
  - `capture_chatpanel_local_walkthrough.py` 補寫 `executed_tools`，讓 walkthrough artifact 不只靠
    stdout log 證明 tool call。
  - 用真 local model 從 ChatPanel UI composer 送出 readiness prompt，要求使用 state query tool。
- 結果：
  - local model 實際執行 `query_state`，metrics 顯示 `tools=1/1`。
  - artifact status `passed`，executed tool `query_state` `ok`。
  - visible assistant transcript 是 `Application state snapshot ready.`；未出現 raw `Tool Output`、
    schema 或 traceback。
  - UI 回到 idle：send button `Send` / enabled，input enabled，chat / controller processing false。
- 證據：
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-ready.png`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-response.png`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.json`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.md`
  - `scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q` -> `3 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
    -> `3 passed`
  - targeted `ruff` / `basedpyright` clean。
- 接續 / 本輪剩餘：
  - 這解除「真 ChatPanel tool-command 單步 evidence」缺口。
  - 仍不是 multi-turn workflow、長時間 assistant 操作、Windows Desktop launcher click-through、
    或完整 import wizard label/metadata editor 驗收。

### 10:49 Data Interpretation wizard review hardening

- 做了什麼：
  - `DataInterpretationPreviewDialog` 從 baseline preview modal 硬化成第一版 import wizard review
    surface。
  - 新增可見流程 `Scan -> Preview -> Validate -> Confirm -> Apply -> Save recipe`。
  - 新增 source/readiness、BIDS status、metadata preview、label/event/recipe trace、review notes、
    confirmation 和 reusable recipe save state。
  - blocked decision 現在明確 disabled apply / save recipe；needs-confirmation action button 顯示
    `Confirm and Apply`。
  - replay helper 補 `WindowNoState` deterministic resize，並用 offscreen mode 刷新 artifact。
- 結果：
  - `artifacts/ui/data-interpretation-preview.png` 顯示新的 wizard review surface。
  - replay JSON dialog title 是 `Interpret Data Source`，decision `needs_confirmation`，apply
    button enabled，save recipe checked。
- 證據：
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q` -> `47 passed`
  - targeted `ruff` / `basedpyright` clean。
- 接續 / 本輪剩餘：
  - 這仍不是完整 metadata override editor 或 label-class map editor。
  - file picker / real user click-through、format matrix 和 label import 內嵌 wizard flow 仍未完成。

### 10:36 ChatPanel true local-model one-turn walkthrough

- 做了什麼：
  - 新增 `scripts/dev/capture_chatpanel_local_walkthrough.py`。
  - 腳本在 `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 下打開真 MainWindow / ChatPanel，
    從 UI composer 送出 prompt，走 AgentManager -> LLMController -> AgentWorker ->
    LLMEngine local backend。
  - 新增 `tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`，覆蓋 transcript markdown
    render 和 raw tool/debug syntax detection。
- 結果：
  - walkthrough `passed`。
  - primary `microsoft/Phi-4-mini-instruct` runtime classification：`gpu-ready`。
  - cache usage：`15.34 GB`，no download，HF / Transformers offline。
  - visible transcript：
    - user：`In one short user-facing sentence, explain what EEG preprocessing does. Do not use tools.`
    - assistant：`EEG preprocessing involves cleaning and organizing the raw EEG data to prepare it for further analysis.`
  - UI 回到 idle：send button `Send` / enabled，input enabled，chat / controller processing false。
- 證據：
  - `artifacts/ui/chatpanel-local-ready.png`
  - `artifacts/ui/chatpanel-local-response.png`
  - `artifacts/ui/chatpanel-local-walkthrough.json`
  - `artifacts/ui/chatpanel-local-walkthrough.md`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown` ->
    `classification: gpu-ready`
  - `timeout 420s xvfb-run -a poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui --timeout-seconds 360` -> wrote artifacts
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q` -> `2 passed`
  - targeted `ruff` / `basedpyright` clean。
- 接續 / 本輪剩餘：
  - 這解除「沒有真 local model ChatPanel 可見回覆 artifact」的缺口。
  - 仍不是 multi-turn tool-command ChatPanel workflow、Windows Desktop launcher click-through、
    長時間 assistant 操作或完整 import wizard UI 驗收。

### 10:25 MCP stdio external-client walkthrough

- 做了什麼：
  - 新增 `scripts/dev/capture_mcp_stdio_walkthrough.py`，用只依賴 Python standard library 的
    client process 啟動 prepared XBrainLab MCP stdio server。
  - client 透過 JSON-RPC 跑 `initialize`、`tools/list`、`scan_source`、
    `preview_interpretation`、`validate_interpretation`。
  - 新增 `tests/integration/mcp/test_stdio_walkthrough_artifact.py`，確認 artifact 可重生且 summary
    保留 external-client dependency boundary、tool listing 和 Data Interpretation taxonomy。
- 結果：
  - `artifacts/mcp/stdio-walkthrough.json` / `.md` 已保存 client-observable transcript summary。
  - tool count `28`；`scan_source` taxonomy 是 `data_interpretation`。
  - `scan_source` / `preview_interpretation` / `validate_interpretation` 都回 `ok`；validation visible
    text 是 `Interpretation validation: needs_confirmation.`。
- 證據：
  - `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp` -> wrote
    artifacts。
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q` -> `7 passed`
  - `poetry run ruff check scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py` -> pass
  - `poetry run basedpyright scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py` -> `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 這解除「沒有外部 stdio client artifact」的缺口。
  - 仍不能宣稱 MCP product complete：Inspector GUI click-through、Windows release config、
    HTTP transport、long-running training through MCP 和 external agent recovery UX 未完成。
  - true ChatPanel local-model walkthrough、Windows launcher click-through、成熟 import wizard UI
    驗收仍是 product blockers。

### 10:10 local tool-call thesis-candidate 100-case rerun

- 做了什麼：
  - deterministic / local eval cases 從 `54` 擴到 `100`，納入 Data Interpretation file /
    folder / BIDS / recipe、metadata choices、relative / missing path、confirmation、blocked /
    recovery、多輪 workflow、bandpass-only vs standard preprocess、dataset split、visualization /
    saliency readiness 和 query-state cases。
  - 補 parser / normalizer / verifier / controller guardrails：partial tool-name JSON、
    command-only JSON with confirmation metadata、blank / relative source path rejection、
    metadata choice cleanup、bandpass-only demotion、dataset split vs training mode、epoch default
    window、visualization / saliency substitute rejection。
- 結果：
  - deterministic baseline：`100 / 100` pass。
  - primary `microsoft/Phi-4-mini-instruct` full local eval：`100 / 100` pass (`100.00%`)。
  - fallback `microsoft/Phi-3.5-mini-instruct` full local eval：`100 / 100` pass (`100.00%`)。
  - 兩者都是 `gpu-ready`，cache `15.34 GB`，no download。
- 證據：
  - `artifacts/agent_evals/deterministic/latest.md`
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_intent.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_controller.py -q` -> `166 passed`
  - targeted `poetry run ruff check ...` -> pass
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q` -> `487 passed`
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
- 接續 / 本輪剩餘：
  - 這解除 local tool-call eval case 數不足和 33% / 37% / 54-case failure blocker。
  - 仍不能宣稱 product complete：true ChatPanel local-model walkthrough、Windows launcher
    click-through、MCP Inspector / release config 和成熟 import wizard UI 驗收仍未完成。

### 07:40 local assistant full eval normalization rerun

- 做了什麼：
  - `CommandParser` 支援 command-only JSON 和 bare tool name。
  - 新增 tool-call normalizer，將常見 local model variants 對齊 registered tools /
    ApplicationService command：`create_epoch`、`train`、`get_dataset_info`、latest-turn
    scan / preview / validate / apply substitute、BIDS hint、subject override、dataset defaults、
    recipe save default。
  - 新增 typed `query_state` agent tool，走 `ApplicationService` `QueryStateCommand`。
  - placeholder validator 擋 prose path / `path/to/your/...`。
  - local eval scoring 納入 backend result interpretation。
- 結果：
  - primary full local eval：`53 / 54` pass (`98.15%`)。
  - fallback full local eval：`53 / 54` pass (`98.15%`)。
  - 兩者都是 `gpu-ready`，cache `15.34 GB`，no download。
- 證據：
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_intent.py -q` -> `156 passed`
  - targeted `poetry run ruff check ...` -> pass
  - targeted `poetry run basedpyright ...` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q` -> `464 passed`
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass
- 接續 / 本輪剩餘：
  - 仍不是 thesis-ready：只有 `54` cases，不是要求的 `100` thesis candidate cases。
  - 剩餘 failing case：bandpass-vs-standard preprocess 語意。
  - true ChatPanel local-model walkthrough、Windows launcher click-through、完整 UI product
    validation 仍未完成。

### 06:21 local assistant tool-call guardrail smoke

- 做了什麼：
  - `CommandParser` 支援 top-level tool-call array 和 OpenAI-style function tool call。
  - 新增 `PlaceholderArgumentValidator`，拒絕 local model 自造的 placeholder source / file /
    recipe path。
  - 新增 user intent helper，`LLMController` 會在 tool execution 前檢查最新使用者要求的
    workflow command；若該 command 被 `ApplicationService` capability policy 擋下，就拒絕
    模型改叫其他 tool 的 substitute call。
  - `LLMController` 會把 inferred latest intent 加進 prompt context，讓 local model 在多輪
    workflow 中知道最新要求的 direct command。
  - 產品 prompt / local eval prompt / tool schema 補 standard preprocess、dataset split 和
    state-authoritative latest-turn 規則。
  - local eval artifact 的 successful tool-call visible response 不再保存 raw JSON tool syntax。
- 結果：
  - 既有 raw outputs 用新 guardrail/scorer 投影：primary 可從 `18 / 54` 到 `30 / 54`，
    fallback 可到 `34 / 54`；這只是重算舊 raw output，不是新 full eval。
  - 真模型探索性 smoke：
    - primary `microsoft/Phi-4-mini-instruct`：`6 / 6` pass。
    - fallback `microsoft/Phi-3.5-mini-instruct`：`6 / 6` pass。
  - preflight 顯示兩個模型都是 `gpu-ready`、cache `15.34 GB`、沒有下載。
- 證據：
  - `artifacts/agent_evals/local_primary_guardrail_smoke/local_microsoft_phi_4_mini_instruct.md`
  - `artifacts/agent_evals/local_fallback_guardrail_smoke/local_microsoft_phi_3.5_mini_instruct.md`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_controller.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_assembler_stage.py -q` -> `125 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_assembler_stage.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_definitions.py -q` -> `150 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py -q` -> `426 passed`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir /tmp/xbrainlab_eval_guardrails` -> wrote temp deterministic report。
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
  - `git diff --check` -> pass
- 接續 / 本輪剩餘：
  - 此段為 guardrail smoke 當時風險；正式 full rerun 已由 07:40 normalization slice 更新，
    但仍不能宣稱 thesis-ready。
  - smoke subset 已清掉多輪 scanned -> preview 重複 scan；後續 full rerun 剩餘
    bandpass-vs-standard preprocess 語意 failure。
  - true ChatPanel local-model walkthrough 仍未驗證。

### 05:52 label import recipe trace integration

- 做了什麼：
  - `AppliedInterpretation` / `ImportRecipe` 新增 `label_imports`。
  - `ImportLabelsCommand` 成功後會把 label carriers、target files、file mapping、selected event
    names、class map 和 success count 寫入 applied interpretation / recipe trace。
  - `ApplicationStateSnapshot.interpretation` 新增 label carrier / label import summary。
  - Dataset panel 的 `Add Labels to Loaded Data` 若收到 `recipe_updated` diagnostics，會提示使用者
    可保存更新後 recipe。
- 結果：
  - label import 不再只是已載入 raw data 的 side mutation；它會進入 Data Interpretation recipe
    trace，之後保存 recipe 會包含外部 label 匯入資訊。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_import_labels_updates_applied_interpretation_recipe_trace tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe -q` -> `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q` -> `74 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q` -> `36 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` -> `3 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q` -> `66 passed`
  - targeted `ruff` / `basedpyright` clean。
- 接續 / 本輪剩餘：
  - 這仍不是成熟 import wizard label editor，也沒有新的 UI screenshot replay。
  - true local LLM ChatPanel walkthrough、Windows launcher click-through、MCP external-client
    walkthrough 和 local LLM tool-call accuracy 改善仍是 product blockers。

### 05:43 stdio MCP server baseline

- 做了什麼：
  - 新增 `XBrainLab.mcp.server`，支援 MCP `initialize`、`tools/list`、`tools/call`。
  - 新增 `scripts/dev/run_mcp_server.py` 作為 stdio entrypoint。
  - `mcp_tool_specs()` 補 `title` 和 `outputSchema`，讓 MCP tools 有同一份 command input /
    execution output schema。
  - MCP `tools/call` 只轉成 `execute_automation_payload()`，並在同一個 `ApplicationService`
    session 中執行，不直接碰 controller。
- 結果：
  - 現在不只是 MCP-shaped schema；已有可用的 stdio MCP server baseline。
  - schema / business failure 會以 MCP tool result `isError: true` 和 user-readable text 回傳，
    structured diagnostics 保留在 `structuredContent`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q` -> `6 passed`
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp tests/unit/backend/application/test_automation.py -q` -> `13 passed`
  - targeted `ruff` / `basedpyright` clean。
- 接續 / 本輪剩餘：
  - 尚未跑外部 MCP client / Inspector walkthrough，也未補 Windows release config。
  - true local LLM ChatPanel walkthrough、Windows launcher click-through 和 local LLM tool-call
    accuracy 改善仍是 product blockers。

### 03:50 Local LLM tool-call runner and schema verifier

- 做了什麼：
  - 新增 `scripts/agent/evals/run_local_tool_call_eval.py`，用同一份 `54` cases / scorer 接真
    local model raw output，並保存 parsed tool calls、schema verification、score breakdown 和
    failure taxonomy。
  - `CommandParser` 補 `arguments`、top-level `name` 和 `tool_calls` list 解析。
  - `VerificationLayer` 補 registered tool schema / required / type / enum 檢查，並讓
    `LLMController` 用 real `ToolRegistry` schema 初始化 verifier。
  - verifier rejection 改成 user-facing repair prompt + structured history，不再讓使用者看到
    schema/debug wording 或空白回覆。
  - 跑 primary / fallback full local eval，各 `54` cases x `3` repeats。
- 結果：
  - primary `microsoft/Phi-4-mini-instruct`：`18 / 54` pass，schema-invalid outputs `9`。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`20 / 54` pass，schema-invalid outputs `6`。
  - local LLM tool-call runner / evidence 已建立；目前 pass rate 明確不能宣稱 thesis-ready。
- 證據：
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py -q` -> `44 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_controller_integration.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q` -> `98 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py -q` -> `383 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q` -> `35 passed`
  - `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q` -> `34 passed, 8 warnings`
  - pipeline smoke -> `2 passed`
  - `poetry run python scripts/dev/update_quality_dashboard.py` -> overall `PASS`
  - targeted `ruff` / `basedpyright` clean。
  - final `ruff` / `basedpyright` / `mkdocs build --strict` / `architecture_compliance` / `git diff --check`
    clean。
- 接續 / 本輪剩餘：
  - 真 ChatPanel 長時間 workflow、完整 MCP server、label import recipe integration 尚未完成。
  - local LLM accuracy 需要 prompt / tool taxonomy / verifier feedback 後續改善，不能把這輪 report
    當 thesis-grade result。

### 03:22 Label import compatibility wording

- 做了什麼：
  - Dataset sidebar 的舊 `Import Label` 按鈕改成 `Add Labels to Loaded Data`。
  - 保留既有 `ImportLabelsCommand(LabelImportPlan)` service-backed path；legacy controller 仍只作
    fallback。
  - 重跑 Dataset sidebar / DatasetActionHandler regression，並刷新 Data Interpretation UI replay
    artifact。
- 結果：
  - 主資料入口語言保持 Data Interpretation；外部 label 匯入被定位為對已載入資料的 compatibility
    action，不再與 `Interpret Data Source` 並列成新的主要心智模型。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q` -> `48 passed`
  - targeted `ruff` / `basedpyright` clean。
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`
- 接續 / 本輪剩餘：
  - label import 尚未整合進 Data Interpretation recipe；完整 MCP server 和 local LLM 真實 eval
    仍未完成。

### 03:18 Data Interpretation recipe save UI

- 做了什麼：
  - `DataInterpretationPreviewDialog` 新增 `Save recipe after applying` checkbox。
  - Dataset panel apply 成功後，若使用者勾選，會走 `SaveInterpretationRecipeCommand`。
  - 若使用者選擇 JSON path，recipe 寫入檔案；若取消 save dialog，recipe 仍保留在 backend
    session。
  - 補 unit / walkthrough regression，並重跑 UI replay artifact。
- 結果：
  - 主 import flow 現在有 scan -> preview -> validate -> confirm/apply -> recipe path。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q` -> `46 passed`
  - targeted `ruff` clean。
  - targeted source/dialog `basedpyright` clean。
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`
- 接續 / 本輪剩餘：
  - label import 仍是 compatibility path，尚未整合進 Data Interpretation recipe；完整 MCP server
    和 local LLM 真實 tool-call eval 尚未完成。

### 03:10 Data Interpretation UI replay artifact

- 做了什麼：
  - 新增 `scripts/dev/capture_data_interpretation_replay.py`。
  - 腳本在固定 temp path 產生 synthetic `.fif`，啟動 real `MainWindow` / Dataset panel，使用真
    `ApplicationService` 跑 scan / preview / validate / apply。
  - 保存 Data Interpretation preview dialog screenshot、applied Dataset panel screenshot 和
    replay JSON。
- 結果：
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON 顯示 dialog decision `needs_confirmation`、未確認 apply 是
    `failed / confirmation_required`、確認 apply 是 `ok`、dataset table rows 是 `1`。
- 證據：
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`
- 接續 / 本輪剩餘：
  - 這是 Data Interpretation dialog / Dataset panel 的 UI-observable replay，不是完整真人
    click-through，也還未覆蓋 ChatPanel agent transcript。

### 03:04 Data Interpretation non-mocked workflow

- 做了什麼：
  - 新增 backend integration test，使用 real synthetic MNE `.fif` file 走 Data Interpretation
    source -> preview -> validation -> confirmation -> apply -> recipe -> reload review ->
    preprocess -> epoch -> dataset。
  - 驗證未確認 apply 會被 `confirmation_required` 擋下，confirmed apply 才會載入 raw data。
  - 驗證 recipe reload 在新的 `ApplicationService` session 只重建 scan / preview / validation，
    不直接套用資料。
  - 驗證 dataset split audit 和 train / val / test counts。
- 結果：
  - Goal 1 的 backend non-mocked source -> recipe -> preprocess -> epoch -> dataset evidence
    已有一條可重跑 test。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q` -> `1 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py -q` -> `38 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` -> `3 passed`
  - targeted `ruff` / `basedpyright` clean。
- 接續 / 本輪剩餘：
  - 這仍不是 UI-observable replay；後續要用 screenshot / visible state / transcript artifact
    驗證人看得到的 import flow。

### 02:53 Goal 1 automation adapter / eval baseline

- 做了什麼：
  - 新增 `XBrainLab.backend.application.automation`，從 typed command dataclass 產生
    command schema、workflow taxonomy、live capability / autonomy policy 和 MCP-shaped tool
    specs。
  - 新增 `scripts/dev/run_application_command.py`，可 headless 列 schema、列 MCP tool specs，
    或在同一個 `ApplicationService` session 中執行 JSON command payload。
  - deterministic tool-call eval 從 `21` cases 擴成 `54` cases，納入 Data Interpretation
    scan / preview / validate / apply / recipe、metadata choice、confirmation boundary、blocked、
    missing-input、recovery 和 `15` 個 multi-turn cases。
  - 刷新 `artifacts/agent_evals/latest.json`、`artifacts/agent_evals/latest.md`。
- 結果：
  - headless / MCP-ready path 不再需要第三套 workflow truth；JSON payload 會轉回
    `ApplicationService.execute()`。
  - deterministic engineering baseline 達到 Goal 1 的最低 `50` cases 與 multi-turn / negative
    比例要求。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py -q` -> `7 passed`
  - `poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py -q` -> `1 passed`
  - targeted `ruff check` -> `PASS`
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
- 接續 / 本輪剩餘：
  - 還不能宣稱 MCP server、local LLM 真實 tool-call accuracy 或 UI-observable replay 完成。
  - 下一步要補 source -> recipe -> preprocess -> epoch -> dataset 的 non-mocked walkthrough /
    replay evidence，並視範圍處理 recipe save UI / label import migration。

### 01:32 Goal 1 runbook 準備

- 做了什麼：
  - 補齊 target docs 中 UI / agent / headless / MCP external agent 的共同入口說法。
  - 檢查 repo-local skills frontmatter，確認 9 個 `.agents/skills/*/SKILL.md` 都有合法
    `name` / `description` frontmatter。
  - 新增 `artifacts/goal/goal-1-product-autopilot.md`，作為 Codex Goal / 長時間 runner
    可直接使用的工程級 prompt。
  - 新增 `artifacts/goal/README.md`，記錄 WSL 開 Goal 的實際 CLI 用法與常見問題。
  - 補強 Goal 1 對資料入口 UI 的授權：新的 Data Interpretation / load data 機制可也應該
    修改 UI，不能只做 backend 或把新流程塞回舊 import 外殼。
  - 更新 `docs/planning/now.md`，把 Goal 1 runbook 標成已建立，下一步改為 docs checkpoint
    與啟動 Codex goal。
- 結果：
  - 下一個 runner 不應再只做 UI 小修或 prompt 小修，而要以 Backend Command Spine、
    Data Interpretation、資料入口 UI redesign、Agent Tool Surface、UI-observable replay
    和 MCP-ready surface 為同一個產品 goal。
- 證據：
  - repo-local skill frontmatter quick check。
  - `codex-cli 0.128.0`；`codex features list` 顯示 `goals under development true`。
- 接續 / 本輪剩餘：
  - 跑文件 / diff 驗證，建立本地 docs checkpoint commit。

### 01:14 MCP 與 UI-observable replay

- 做了什麼：
  - 在 roadmap 新增 Automation Adapters / MCP track。
  - 在 target architecture 補 MCP server 作為 external agent adapter，MCP client 不需安裝
    XBrainLab 的完整 EEG / PyQt / PyTorch stack，但 MCP server 必須跑在 prepared runtime 並
    走 ApplicationService。
  - 在 thesis protocol 將 scripted replay 分成 backend replay 與 UI-observable replay；
    UI replay 必須保存 transcript、screenshots / UI artifact、visible status、button enablement
    或 wizard step。
  - 在 now 補 Goal 1 的 MCP-ready automation surface 與 UI-observable replay 驗收要求。
- 結果：
  - headless 不再被當作產品主介面，而是 CI / eval / batch adapter。
  - MCP 被正式定位成外部 agent adapter，但不能變成第三套 workflow truth。
  - scripted replay 不能只靠文字報告宣稱 UI 正確。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 驗證文件站點，下一步仍是 docs checkpoint 與 Goal 1 runbook。

### 01:02 Now 對齊 Goal 1

- 做了什麼：
  - 重寫 `docs/planning/now.md`，移除舊 product-delivery 長 checklist。
  - 將目前短期焦點改成 Goal 1 啟動前的施工入口。
  - 定義 Goal 1 範圍：Backend Command Spine + Data Interpretation System +
    Agent Tool Surface Migration。
  - 補 Goal 1 Scope、Done Definition、Goal 前必做、Validation Gates、不能宣稱與下一步。
- 結果：
  - `now.md` 現在可直接支撐下一步寫 goal runbook。
  - goal runner 不應再從舊 checklist 恢復，而應以 Data Interpretation / autonomy policy /
    tool taxonomy 作為第一個大 goal 的核心。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 驗證文件站點後，建立 docs checkpoint，接著寫 Goal 1 runbook。

### 00:54 Agent autonomy / decision boundary

- 做了什麼：
  - 在 `docs/target/agent.md` 補 Autonomy Policy / Decision Boundary，明確寫 agent 可規劃完整
    workflow，但必須一個 command 一個 command 地 verify / execute / refresh state。
  - 補 command-specific autonomy 欄位和 turn-level guard，並說明停止條件是 decision boundary，
    不是任何 state transition。
  - 重寫目標 tool taxonomy，從舊 dataset / preprocess / training 粗分類改成 Discovery /
    Data Interpretation / Metadata Resolution / Data Transform / Experiment Setup / Execution /
    Lifecycle / UI Routing。
  - 在 Data Interpretation target 補 subject / session / task / run metadata preview、
    confirmation 和 recipe 保存要求。
  - 在 architecture / thesis protocol 補 autonomy decision、decision boundary 和 scorer cases。
- 結果：
  - 文件不再把「agent 聰明停下來」當假設，而是要求 backend / Verification Layer 用 policy 強制。
  - goal runner 之後應實作 autonomy policy，而不是只調 prompt。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 驗證文件站點，接著更新 `now.md` 或 goal runbook 時，要把 autonomy policy 當成必做範圍。

### 00:33 Roadmap 定義成產品主線

- 做了什麼：
  - 重寫 `docs/planning/roadmap.md`，移除舊的歷史階段 / 短期 TODO 混合寫法。
  - 定義 Product North Star、路線原則、Product Completion Tracks、Roadmap Order、
    Non-goals 和成品判定。
  - 把 Backend Command Spine、Data Interpretation System、UI Product Experience、
    Agent Runtime / Tool Surface、Validation / Thesis Evidence、Packaging / Release
    分成可驗收主線。
- 結果：
  - roadmap 現在描述工程級成品路線，不再取代 `now.md`。
  - 後續 autopilot 應以這份 roadmap 判斷是否完成產品，而不是只看單一 milestone。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 驗證文件站點，然後視需要更新 `now.md` 成下一個短期施工焦點。

## 2026-05-03

### 22:26 驗證模型分層

- 做了什麼：
  - 在 Data Interpretation target 補三層驗證模型：資料解讀、workflow state、agent tool-call。
  - 將 target agent 的資料入口 tool surface 改成 scan / preview / validate / apply / recipe，
    不再以舊 load data / attach labels 為目標心智模型。
  - 在 thesis protocol 補 Data Interpretation cases 與 Verification Layer guard 要求。
- 結果：
  - confidence gate 的定位更清楚：它只管 LLM tool-call retry / self-correction，不代表資料正確。
  - recipe reload、BIDS validation、blocked / confirmation / safe 都能進入 agent benchmark。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 盤點目前實際 agent code 狀態，對照 target 說明差距。

### 20:45 Data Interpretation 設計對齊

- 做了什麼：
  - 全盤 review target design 後，修正 `target/architecture.md` 的舊 data entry 心智模型。
  - 保留 agent confidence gate，但寫清楚它只管 tool-call retry / self-correction，不管資料解讀正確性。
  - 補 Data Interpretation lifecycle 和 BIDS `warning` / `limited` / `blocked` 分層。
- 結果：
  - Target architecture、agent target 和 Data Interpretation target 不再互相打架。
  - DataInterpretation 不再同時代表候選與已套用 truth。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 之後才能把這套 target design 轉成 goal prompt 或 implementation plan。

### 20:29 Data Interpretation target design

- 做了什麼：
  - 新增 `docs/target/data_interpretation_system.md`，把資料匯入 / label-event 解讀 /
    BIDS / recipe / UI-agent 行為整理成 target truth。
  - 明確定義使用者輸入是 `source_path`，輸出是可預覽、可驗證、可重跑的
    `DataInterpretation` / recipe。
  - 更新 Target README、mkdocs Target nav 和 decisions。
- 結果：
  - 設計結論從 research 文件抽出，正式放進 `docs/target/`。
  - 不再把舊 `load_data` / `attach_labels` 心智模型當成終局設計原則。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 之後才能基於 target design 寫 goal prompt 或 implementation plan。

### 18:11 BCI/EEG import label 設計資料來源

- 做了什麼：
  - 新增 `docs/research/bci_eeg_import_label_design_source.md`，定位為後續 import /
    label / BIDS / fallback 設計的資料來源，不是 deficiency report 或 roadmap。
  - 補使用者族群、label carrier、coverage classes、BIDS 獨立章節、統一分析維度與後續
    import wizard / label preview / recipe / agent eval 應回答的問題。
  - `mkdocs.yml` 加上 Research 導航。
- 結果：
  - 後續討論 label / event 制度時有一份整理過的現實案例基礎，可避免只從單一 GDF
    或單一 `.mat` label 情境設計。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 基於這份資料來源，另行設計 import / label / BIDS / fallback 的 target solution。

### 17:20 Tool-call eval gate 補強

- 做了什麼：
  - 把 tool 重構、Verification Layer contract、足量 cases 和資料級支撐寫進 canonical docs。
- 結果：
  - 不再只寫「建立 scoring system」；現在明確要求 engineering baseline `50` cases、
    thesis candidate `100` cases、negative / blocked / recovery `30%`、multi-turn `15` cases、
    local LLM primary / fallback 至少重跑 `3` 次。
  - tool surface 必須重構成 service-backed command；mutating agent tools 不可直接包 controller。
  - 資料級支撐要覆蓋 checked-in fixtures 和 event-rich public fixture slice。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 實作 scorer / runner、case schema、case set 和 artifact report。

### 17:10 Thesis evidence 主線校正

- 做了什麼：
  - 使用者指出論文要仔細驗證的是 tool-call 準確率，不是訓練準確率。
  - 更新 thesis protocol、validation README、validation architecture、current docs、
    `.agents/context/thesis.md` 和 backend goal runbook。
- 結果：
  - current truth 改成：agent tool-call accuracy 是 thesis 主線；EEG split / training /
    evaluation metrics 是 product pipeline support，不可取代 tool-call scoring。
  - 後續 goal runner 不應把 external EEG dataset experiment / training accuracy 當成主要
    thesis milestone。
- 證據：
  - `git diff --check`
  - `poetry run mkdocs build --strict`
- 接續 / 本輪剩餘：
  - 產品主線穩定後，才建立 local LLM primary / fallback tool-call accuracy run、score report
    和 failure taxonomy。

### 00:40 Supervisor rule / window fallback / backend hardening review

- 做了什麼：
  - 將 repo agent 入口補上 supervisor model：worker 回報完成不算完成，主 agent 必須自己讀 diff、
    看 artifact、跑 tests、比對 current docs，仍有 blocker 就打回。
  - 發包 UI/window worker 修正 Windows/WSLg offset dual-monitor 開窗回歸；first launch、
    壞 saved geometry、post-show recovery 改成 maximized fallback，不使用 fullscreen。
  - 發包 backend worker 補 dataset generation apply/audit rollback boundary，並把
    `evaluate` / `clear_training_history` capability 改成看 actual training plan history。
  - 發包 QA explorer 只讀審核 tests 是否真的支撐 product delivery。
- 結果：
  - UI/window slice 的 regression tests 覆蓋使用者回報 geometry：
    `screen[0] x=0 y=362`、`screen[1] x=1920 y=0`、cursor `(0,0)` 在 virtual gap。
  - Backend slice 避免 split apply 例外或 split audit blocker 留下半成功 datasets /
    generator / trainer。
  - QA 審核確認仍不能宣稱完整產品完成：真 Windows launcher click-through、true local model
    UI walkthrough、real UI button-click 到 training/eval/viz completion 仍未完成。
  - 我自己的驗證中曾把 Markdown 檔誤丟給 `ruff`，該失敗是驗證命令錯誤，不是程式碼失敗；
    已改用只含 Python 檔的 ruff gate。
- 證據：
  - `git diff --check` PASS
  - `poetry run ruff check XBrainLab/ui/main_window.py XBrainLab/backend/application/capabilities.py XBrainLab/backend/application/service.py XBrainLab/backend/facade.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/backend/application/test_application_service.py tests/unit/backend/test_facade_headless.py`
    - `All checks passed!`
  - `poetry run pytest --capture=sys tests/unit/ui/test_window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/test_run_splash_geometry.py -q`
    - `22 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_headless.py tests/unit/backend/test_facade_coverage.py tests/unit/llm/tools/test_application_surface.py -q`
    - `80 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q`
    - `48 passed`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict`
    - PASS
- 接續 / 本輪剩餘：
  - 使用者仍需在真 Windows/WSLg 雙螢幕上 click-through 確認 launcher / splash / main window。
  - 要補真 UI E2E：button click 到 real training completion、evaluation record、visualization/saliency。
  - 不可把 synthetic product walkthrough 或 deterministic eval 當完整 release evidence。

## 2026-05-02

### 22:44 Launcher visible logs / geometry diagnostics

- 做了什麼：
  - 重新讀取 repo launcher、PowerShell launcher、Desktop `XBrainLab.cmd`、`run.py`、
    `MainWindow` placement path 和既有 geometry tests。
  - 確認 Desktop `XBrainLab.cmd` 指向 `/mnt/d/workspace_v2/projects/lab/XBrainLab`，
    Desktop 上也沒有其他 XBrainLab shortcut / generated app；目前不像是跑舊 repo。
  - `.cmd` 改為 bootstrap active repo 的 PowerShell launcher，避免 Desktop command 變成
    stale generated app；terminal 會先顯示 active WSL repo、Windows repo、PowerShell launcher path。
  - `.ps1` launcher 改成 visible preamble + live tee：log path、開 log / tail log 指令、
    WSL / Python stdout/stderr 都同時出現在 terminal 和
    `%LOCALAPPDATA%\XBrainLab\logs\launcher-*.log`。
  - 新增 `XBRAINLAB_STARTUP_DIAGNOSTICS=1` safe diagnostic mode，只有開 env var 才 log
    screens、cursor、splash geometry、MainWindow restore/default placement、show event、
    post-show 0ms / 250ms geometry。
  - `showEvent()` 的 post-show recovery 從單次 `0ms` 補成 `0ms + 250ms`，覆蓋 Windows / WSLg
    show 後才 finalise native frame 或二次移動 window 的 timing。
  - 新增 `XBRAINLAB_LAUNCHER_SMOKE=1` smoke mode，用來驗證 launcher preamble / active repo
    delegation / log 寫入而不真的啟動 GUI。
- 結果：
  - Windows terminal 不應再是一片黑；一開始就會看到 repo、log path、正在啟動、如何看 log。
  - Desktop launcher 目前判斷不是 stale app；它會委派到 active repo 內的 PowerShell launcher。
  - 如果使用者再遇到「正上方」，可用 `XBRAINLAB_STARTUP_DIAGNOSTICS=1` 收到 screens /
    splash / MainWindow after-show / post-show geometry，比只猜 margin 更可定位。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
    - `19 passed`
  - `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
    - `All checks passed!`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - Launcher syntax / smoke：
    - PowerShell parser：`PowerShell syntax OK`
    - repo `.cmd` smoke：active repo bootstrap passed
    - Desktop `.cmd` smoke：active repo bootstrap passed
    - repo `.ps1` smoke：WSL stdout / stderr were mirrored to terminal and launcher log
- 接續 / 本輪剩餘：
  - 仍需要真人雙螢幕 Windows click-through 驗收；這輪補的是 visible diagnostics 和 timing
    recovery，不能完全替代真 window manager 行為。

### 22:14 Dual-monitor startup geometry follow-up

- 做了什麼：
  - 使用者回報第一版 geometry recovery 後仍會貼到最上方，且 loading splash 不在螢幕中央；
    判斷上一版只處理 top-left / offscreen，沒有完整處理 top-edge、native frame、
    dual-monitor startup screen。
  - 新增 `XBrainLab/ui/window_placement.py`，把 startup screen selection、saved geometry
    screen ranking、splash centering、frame-aware geometry health check 抽成可測 helper。
  - `run.py` 的 loading splash 會在 `show()` 前根據 saved geometry / cursor / primary
    選定 startup screen 並置中，並把同一個 screen hint 傳給 MainWindow。
  - MainWindow 對 restored / persisted geometry 改成 frame-aware 判斷：top-edge、
    native frame titlebar 不可達、跨螢幕 frame、尺寸不合理都會 reset / recenter。
  - 預設 window size 改為保留足夠上下視覺空間，避免小螢幕上看起來貼在最上方。
- 結果：
  - 第一版「只處理左上角」的缺口已補；loading splash 和 main window 不再各自選螢幕。
  - 正常 saved geometry 仍會保留；貼上緣 / top-center / top-right 都會視為不健康。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
    - `15 passed`
  - `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
    - `All checks passed!`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 仍需要使用者在真雙螢幕 Windows launcher 上人工確認；這是 WSLg / Windows window
    manager 行為，不能只靠 xvfb 宣稱完全通過。

### 21:08 MainWindow saved geometry recovery

- 做了什麼：
  - 針對 Windows launcher 打開後主視窗卡在左上角且不可拖的退件，重看
    `MainWindow._restore_or_place_window()`、post-show clamp、`closeEvent()` geometry
    persistence，以及 Assistant dock custom titlebar。
  - 將 restore 成功和 geometry 可用拆開判斷；貼左上、offscreen、尺寸不合理、
    titlebar 不可達的 saved `main_window/geometry` 會移除並用安全預設位置重置。
  - `closeEvent()` 不再保存明顯不可用的 geometry，避免壞 QSettings 反覆自我保存。
  - 補 Assistant dock titlebar regression，確認空白 titlebar mouse events 會交回
    `QDockWidget` 原生拖曳處理，double-click 仍可 float / dock。
- 結果：
  - 既有壞 `QSettings("XBrainLab", "XBrainLab")["main_window/geometry"]` 不需要使用者手動清除；
    啟動時會 migration reset 到可見、可拖曳 titlebar 的安全位置。
  - 正常 user-resized geometry 仍會保留。
- 證據：
  - `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py -q`
    - `6 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
    - `32 passed`
  - `poetry run ruff check XBrainLab/ui/main_window.py XBrainLab/ui/components/agent_manager.py tests/integration/ui/test_window_geometry.py`
    - `All checks passed!`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
- 接續 / 本輪剩餘：
  - 真 Windows Desktop launcher click-through 仍需人工驗收，但 blocker 的 persisted bad
    geometry path 已有 regression protection。

### 20:35 Final validation closure

- 做了什麼：
  - 收斂最後一輪退件：local-disabled assistant startup 改成 visible reason，
    confirmation transcript 不再暴露 raw tool names，montage apply 改走 command surface，
    `run.py` startup path 維持 local-only，UI baseline geometry 穩定，UI unit legacy runtime
    expectations 改成 remote switch fail-closed / active local deletion block。
  - 刷新 deterministic tool-call eval artifact，tracked `artifacts/agent_evals/latest.json`。
  - 同步 canonical docs，避免 current truth 停在舊 dashboard 或舊 API/Gemini removal wording。
- 結果：
  - latest fast dashboard 從先前 FAIL 修到 clean `PASS`。
  - `artifacts/quality/latest.md` generated at `2026-05-02 20:35:07 UTC+08:00`，
    overall `PASS`。
  - dashboard summary：Ruff PASS，Basedpyright PASS `0 errors, 0 warnings, 0 notes`，
    Architecture PASS，Startup Smoke PASS，UI Baseline PASS，UI Dialog PASS，
    UI Unit Suite `814 passed`，Real-Data IO Integration `31 passed, 8 warnings`。
- 證據：
  - `git diff --check` PASS
  - `poetry run ruff check .` PASS
  - `poetry run basedpyright` PASS
  - `poetry run mkdocs build --strict` PASS
  - `poetry run python tests/architecture_compliance.py` PASS
  - UI product / geometry gate：`121 passed`
  - agent / backend command gate：`225 passed`
  - backend + IO integration：`33 passed, 8 warnings`
  - full pipeline integration：`70 passed, 4 warnings`
  - LLM / local settings / script unit gate：`674 passed`
  - deterministic tool-call eval artifact refresh：commit
    `e5454c7 test: refresh agent eval artifact`
  - local model preflight：primary `microsoft/Phi-4-mini-instruct` already cached，
    current / projected cache `15.34 GB`，available disk `158.54 GB`，
    estimated download `0.00 GB`，VRAM estimate `9.0 GB`，license MIT。
  - relevant commits：
    `8b04380`、`1883d4b`、`8a6099a`、`41ec91c`、`3edee21`、`5ed1c87`、
    `4cd4d4c`、`406719c`、`e5454c7`。
- 接續 / 本輪剩餘：
  - Windows Desktop launcher click-through 尚未人工驗收。
  - true local LLM ChatPanel long walkthrough 尚未跑。
  - external thesis dataset experiment / statistical reporting 尚未完成。

### 19:28 Backend command surface migration closure

- 做了什麼：
  - 擴充 `ApplicationService` command contract：`update_metadata`、`apply_smart_parse`、
    `remove_files`、`import_labels` / `LabelImportPlan`、`apply_montage`、`query_state`。
  - 將 dataset metadata edit / smart parse / remove / label import、InfoPanel read query、
    agent montage confirmation、agent `load_data` command surface 接到 `ApplicationService.execute()`。
  - 補 capability policy：train 在 load 前明確 blocked；epoch / dataset 後 raw edit、
    label / metadata / remove / preprocess / recreate epoch / regenerate dataset 會要求 reset /
    new session。
  - 保留 mock/unit-test fallback；real `Study` path 回 `CommandResult`。
- 結果：
  - 先前列出的 label import、smart parse、remove files、metadata update、montage confirmation
    legacy mutating paths 已收斂到 service command。
  - `BackendFacade` 保留 compatibility wrapper，data summary / preprocess diagnostics 改用
    `QueryStateCommand`。
- 證據：
  - `git diff --check`
  - `poetry run ruff check XBrainLab/backend XBrainLab/llm/tools XBrainLab/ui/panels/dataset XBrainLab/ui/components/info_panel_service.py XBrainLab/ui/components/agent_manager.py tests/unit/backend tests/integration/backend tests/unit/llm/tools`
    - `All checks passed!`
  - `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/unit/llm/tools tests/integration/io/test_io_integration.py -q`
    - `249 passed, 8 warnings`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/components/test_info_panel_service.py -q`
    - `133 passed`
- 接續 / 本輪剩餘：
  - `set_montage` / `switch_panel` 仍是 UI request path；montage apply 本身已 service-backed。
  - 真 Windows launcher click-through / 真 local model 長時間 walkthrough 仍需人工驗收。

### 19:20 Local-only assistant runtime enforcement

- 做了什麼：
  - 將 `LLMConfig`、`LLMEngine`、`AgentWorker` product path 改成 local-only。
  - 刪除 product package 中的 remote backend modules，model settings 移除 remote key / remote model UI。
  - `pyproject.toml` default deps 移除 remote SDK，保留 optional legacy dependency group。
  - 刪除 Gemini verify/list scripts，legacy benchmark scripts 移除 Gemini model option。
  - 加 architecture compliance guard，掃 product path 禁止 remote backend class / remote key env path。
- 結果：
  - `INFERENCE_MODE=api`、舊 settings 裡的 Gemini mode、`reinitialize_agent("Gemini")`
    都不會 instantiate remote backend。
  - worker/model switching 只接受 local catalog 裡的 Phi primary / fallback 或 generic `Local`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/core/test_engine.py tests/unit/llm/agent/test_worker.py tests/unit/ui/dialogs/test_model_settings.py -q`
    - `73 passed`
  - `poetry run pytest --capture=sys tests/unit/llm -q`
    - `644 passed`
- 接續 / 本輪剩餘：
  - 跑使用者指定的完整 ruff / pytest / architecture gates。

### 19:12 Assistant product shell / window geometry rebuild

- 做了什麼：
  - 依退件回饋重做 Assistant 第一層：header 保留 `XBrainLab Assistant` 和低干擾 `...`
    menu；Retry / Clear 收進 menu / compatibility controls，不再佔第一層。
  - empty state 改成 EEG 使用者語言：`Load EEG data to begin`、`Ask what is ready`、
    `Explain why training is blocked`。
  - composer footer 改成只顯示 workflow hint，例如
    `No data loaded · Import EEG files to begin`；runtime / backend detail 只留在 tooltip /
    settings / logs，不進第一層。
  - 修 Assistant dock custom titlebar：空白 titlebar mouse events 交回 `QDockWidget`，保留
    dock drag；浮動 dock 會放在主視窗附近並 clamp 到可用螢幕。
  - 修 MainWindow geometry：首次啟動依可用螢幕置中；restore geometry 後 clamp；保留 resize /
    maximize / restore。
  - 補 `tests/integration/ui/test_window_geometry.py`，並更新 chat / walkthrough /
    AgentManager regression tests。
  - 重新 capture UI screenshots，更新 `artifacts/ui/ai-assistant-open.png` 與
    `tests/baselines/ui/ai-assistant-open.png`。
- 結果：
  - 第一層不再顯示 `General Assistant`、`Single step`、`Local model ready`、`Backend:`、
    `pipeline_stage`，visible transcript 也不曝露 raw tool/debug payload。
  - 320 / 380 / 460px dock 下 `hello` 保持可讀，composer input / Send button 不重疊。
  - status bar / footer 只保留 workflow next action，不顯示 local runtime ready。
- 證據：
  - `git diff --check`
  - `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py XBrainLab/ui/main_window.py tests/unit/ui/chat tests/integration/ui`
    - `All checks passed!`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py -q`
    - `42 passed in 9.22s`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py tests/integration/ui/test_window_geometry.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
    - `92 passed in 10.86s`
  - `xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
    - saved `artifacts/ui/ai-assistant-open.png`
- 接續 / 本輪剩餘：
  - 真 Windows launcher click-through / 真 local model 長時間 walkthrough 仍需人工驗收。

### 18:27 Assistant footer status removal follow-up

- 做了什麼：
  - 依最新人工不滿意回饋重看 `ChatPanel`、chat UI tests 和
    `artifacts/ui/ai-assistant-open.png`。
  - 確認舊 artifact 仍顯示 footer 狀態列文字，例如 workflow / local runtime summary。
  - 將常駐 workflow guidance band 改成隱藏相容欄位；workflow / model detail 改放
    header / Options tooltip 和 empty state。
  - 補 UI tests 鎖住 footer：composer footer 不得再出現 visible status label。
- 結果：
  - Assistant footer 只服務輸入、Retry、Clear，不再當 workflow/runtime status dashboard。
  - empty state 仍保留目前 workflow 和下一步；進入對話後不會持續把狀態文字壓在 footer。
- 證據：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py -q`
    - `38 passed in 11.15s`
  - `timeout 240s scripts/dev/run_ui_pytest.sh --capture=no tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q`
    - `1 passed in 6.62s`
  - `timeout 240s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_baseline.py`
    - updated `artifacts/ui/ai-assistant-open.png`
  - synced `tests/baselines/ui/ai-assistant-open.png` to the accepted assistant artifact
  - `git diff --check`
- 接續 / 本輪剩餘：
  - 仍需人工看圖確認 empty state 的 workflow 文案是否也要再降噪。

### 18:15 Assistant product status polish

- 做了什麼：
  - 人工審核 Goal session 產物後，確認 raw tool output 不再直接進入 visible transcript。
  - 發現 footer / runtime status 仍有 debug 感，補修 `ChatPanel`：隱藏 legacy
    `runtime_status_label`，改由 tooltip 保留完整資訊；subtitle 縮短；footer 狀態降噪；控制列高度
    由 70px 調成 64px。
  - 重新 capture `artifacts/ui/ai-assistant-open.png`，同步更新
    `tests/baselines/ui/ai-assistant-open.png`。
  - 修正 controller coverage 測試，避免 `hi` 被 greeting shortcut 接走而測不到 exception path。
- 結果：
  - Assistant dock 目前第一層資訊更接近使用者產品介面：header、guidance、empty state、
    composer footer 各自分工，不再把 workflow / runtime diagnostics 擠成一條醜的狀態列。
  - local ready / retry / clear 仍保留，但降到低干擾 footer，不把 raw backend command 或 tool
    schema 直接丟給使用者。
- 證據：
  - `git diff --check`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller_cov.py tests/unit/ui/chat/test_chat_panel.py -q`
    - `67 passed`
  - `poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/dev/update_quality_dashboard.py`
    - overall `PASS` at `2026-05-02 18:11:29 UTC+08:00`
  - commit：`bb2c6f1 ui: polish assistant product status`
- 接續 / 本輪剩餘：
  - 真 Windows launcher click-through。
  - 真 local model 長時間 ChatPanel walkthrough。
  - API / Gemini code path 從 source code 刪除。

### 17:20 Assistant product audit follow-up

- 做了什麼：
  - 依人工驗收失敗證據重新審視 `ChatPanel`、`AgentManager`、`LLMController`、
    `application_surface.py` 和 local runtime settings。
  - 移除 assistant dock 頂部 chip dump；header 只保留 `XBrainLab Assistant`、subtitle、
    `Options`，workflow state / next step 改成單句 guidance。
  - 將 `Retry` / `Clear` 降到底部 composer footer；`Retry` 沒有上一則 request 時 disabled，
    direct call 只顯示 footer/status notice，不進 transcript。
  - 修正 message bubble minimum width，避免 380px dock 下 `hello` 被切成 `hell/o`。
  - `LLMController` 新增 greeting shortcut，`hello` 不再先亂 call tool。
  - `ToolCommandResult` 增加 product-level error bucket；read-only `list_files` 也走 typed
    normalization。
  - visible transcript 改成產品語言：missing directory 追問 folder/path，empty list 顯示空狀態，
    backend precondition 顯示 blocked reason，不再顯示 `Tool <name> completed (...)`、
    `Error: directory is required`、`[]` 或 snake_case command。
  - Gemini / remote runtime 一般產品 UI 和 startup 改由 `XBRAINLAB_SHOW_LEGACY_REMOTE_LLM=1`
    隔離，未設定時不顯示或啟動 legacy remote runtime。
  - 重跑 UI capture，更新 `artifacts/ui/ai-assistant-open.png` 和
    `tests/baselines/ui/ai-assistant-open.png`。
- 結果：
  - Assistant dock 目前像使用者產品面板，而不是 tool/debug status panel。
  - raw tool payload 仍保留在 controller history / diagnostics / logs，可供測試與 debug；
    第一層 chat transcript 不再外洩開發者語法。
- 證據：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
    - `131 passed`
  - `timeout 240s poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/core/test_config.py -q`
    - `110 passed`
  - `timeout 240s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `57 passed`
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
    - `2 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py tests/integration/agent/test_product_flow.py -q`
    - `7 passed`
  - `timeout 240s xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
    - saved `artifacts/ui/ai-assistant-open.png`
  - `timeout 420s poetry run python scripts/dev/update_quality_dashboard.py`
    - final rerun overall `PASS` at `2026-05-02 17:44:37 UTC+08:00`
- 接續 / 本輪剩餘：
  - final lint / format / mkdocs / dashboard gate。
  - local commits；不 push。
  - 真 Windows launcher click-through 和真 local model 長時間 UI walkthrough 仍未做。

### 12:02 Chat product blocker correction

- 做了什麼：
  - 接受人工驗收回報：AI Assistant UI 仍像 debug dock，且使用者輸入 `hello` 後沒有
    assistant 回覆。
  - 將 product gate 狀態從「接近完成」修正為被 chat response reliability / chat UX 擋住。
  - 追蹤 chat 路徑：`ChatPanel._on_send -> AgentManager.handle_user_input ->
    ChatController.add_user_message -> LLMController.handle_user_input -> AgentWorker ->
    LLMEngine -> chunk / finished / error -> ChatPanel bubble`。
  - 找出 automated gate 漏掉的風險：empty response 可 silent finalize；tool-only successful
    response 可被隱藏 JSON 後直接 finalize；normal `hello` product flow 沒有測 user-visible
    assistant bubble。
  - 重設計 ChatPanel 結構：header、status chips、empty state、composer、professional bubbles。
  - 補 product-flow tests：normal response、empty response fallback、worker error visible、
    local unavailable visible、UI structure。
- 結果：
  - 一般輸入 path 現在必須產生 visible assistant response 或 visible error。
  - empty response 會顯示可理解 fallback error；tool-only success 會顯示短 tool summary。
  - 文件已開始校正 automated smoke / deterministic eval / true product flow 的邊界。
- 證據：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
    - `55 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py -q`
    - `75 passed`
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `817 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
    - `652 passed`
  - `timeout 180s poetry run basedpyright`
    - `0 errors, 0 warnings, 0 notes`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py -q`
    - `102 passed`
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過
  - `timeout 60s git diff --check`
    - 通過
  - `timeout 360s poetry run python scripts/dev/update_quality_dashboard.py`
    - overall `PASS`
- 接續 / 本輪剩餘：
  - 做 checkpoint commit。
  - 真 Windows Desktop shortcut click-through 仍需人工或可控 UI smoke。

### 07:05 Deterministic tool-call eval baseline

- 做了什麼：
  - 參考 BFCL、LangSmith trajectory evaluation、OpenAI structured-output / function-calling
    思路，落成 XBrainLab deterministic baseline，而不是先跑不穩的 local LLM eval。
  - 新增 `scripts/agent/evals/run_tool_call_eval.py`，定義 21 個 XBrainLab 專用 cases。
  - cases 覆蓋 empty state train refusal、load、preprocess、epoch、dataset、train readiness、
    reset confirmation、visualization/saliency block、invalid parameter、多輪補參數、tool result interpretation。
  - 產出 `artifacts/agent_evals/latest.json` 和 `artifacts/agent_evals/latest.md`。
- 結果：
  - deterministic baseline `21 / 21` passed。
  - 這是 eval framework / scripted baseline，不是 local LLM primary / fallback 真實成功率。
- 證據：
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent -q`
    - `1 passed`
  - `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
    - wrote latest JSON / Markdown；failed cases `0`
- 本輪剩餘：
  - 若要宣稱 local LLM tool-call ability，需在下一輪用同一 case schema 接 primary / fallback runner。

### 06:46 Resource-safe final gate plan

- 做了什麼：
  - 準備進入本輪 final validation / documentation closure。
  - 依 resource-safe execution 規則，每次只跑一個重型任務，所有 pytest / UI / LLM /
    launcher / docs build 都加 `timeout`。
- 將跑哪些：
  - backend unit：`timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
  - backend + IO integration：`timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - pipeline integration：`timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
  - UI unit：`timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - LLM unit：`timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - local runtime health/prompt/structured smoke：單獨執行，不與測試並行。
  - launcher startup smoke：`timeout 45s xvfb-run -a poetry run python run.py --model local`
  - docs / whitespace：`timeout 120s poetry run mkdocs build --strict`、`timeout 60s git diff --check`
- 為什麼：
  - 目前 backend、UI、agent、local runtime、launcher 都已有分段 evidence；final gate 要確認
    commit checkpoint 後仍能一起過。
- 預估風險：
  - pipeline integration 和 local model smoke 可能最耗時 / 最吃資源；若超時，會記錄超時點並改跑代表性抽樣。
- 結果：
  - backend unit、backend/IO integration、pipeline integration、UI unit、LLM unit、local runtime
    health/prompt/structured smoke、launcher startup smoke 皆完成。
  - local model preflight 首次發現 product bug：primary 已在 cache 中時仍被當成新增下載，
    造成 projected cache 誤判超過 20GB。已修成 already-cached model 不增加 projected cache。
  - launcher smoke 在 `MainWindow initialized` 後以 timeout 結束，屬 GUI smoke 預期結果。
- 證據：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
    - `2661 passed, 1 skipped, 1 xfailed, 3 warnings`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
    - `33 passed, 8 warnings`
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
    - `70 passed, 4 warnings`
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `811 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
    - first run found stale coverage tests expecting string-only tool results; after test/product fix:
      `649 passed`
  - `timeout 120s poetry run python scripts/dev/plan_local_model_download.py --format markdown`
    - after fix: `ok=True`, estimated download `0.00 GB`, projected cache `15.34 GB`
  - `timeout 300s poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
    - classification `gpu-ready`; prompt smoke `passed`; structured-output smoke `passed`
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
    - `MainWindow initialized` before expected timeout `124`
  - `timeout 60s git diff --check`
    - 通過
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過
- worktree：
  - final docs closure 前仍有 local preflight fix、typed result compatibility test、validation docs 更新待 commit。

### 06:39 UI -> agent -> backend blocked-command flow test

- 做了什麼：
  - 新增 `tests/unit/ui/components/test_agent_manager.py` deterministic product-flow test。
  - 測試在不載入本地模型的情況下啟動 `AgentManager` / real `LLMController` / real `Study`，
    透過 debug tool 執行 `start_training`。
  - empty state 下 `ApplicationService` policy 擋下 train，UI chat 收到 structured
    `Tool Output`，內含 `ok=false`、`command_name=train` 和 shared blocked reason。
- 結果：
  - Milestone D/H 的「至少一條 UI -> agent -> backend blocked command flow 可測」已有 low-risk
    deterministic coverage。
  - 這不是取代真 launcher click-through；真桌面啟動後開 chat panel 的 product smoke 仍要跑。
- 證據：
  - `timeout 180s scripts/dev/run_ui_pytest.sh tests/unit/ui/components/test_agent_manager.py tests/unit/ui/chat/test_chat_panel.py -q`
    - `49 passed`
- 本輪剩餘：
  - launcher startup / chat-panel smoke。
  - final gate 前依 resource-safe 規則逐步跑 backend、UI、LLM、integration、MkDocs。

### 06:25 Agent typed result adapter

- 做了什麼：
  - 在 `XBrainLab/llm/tools/application_surface.py` 新增 `ToolCommandResult`，把 agent tool
    blocked / failed / successful result 轉成 typed payload。
  - `LLMController._execute_tool_no_loop()` 對 ApplicationService-backed tools 回傳 structured
    result，並把 legacy `"Error: ..."` / `"Failed ..."` 字串判定成 failed result。
  - 補 `test_application_surface.py` 和 `test_controller.py`，確認 blocked preprocess / blocked
    train / legacy string failure 都不再被當成成功。
  - 修正 `tests/unit/llm/agent/test_worker.py`，避免測試將 repo `settings.json` 寫回
    Gemini / API mode。
- 結果：
  - Agent tool system alignment 的 typed result adapter 缺口已收斂。
  - ApplicationService-backed tool output 會保留 `command_name`、`error_type`、`blocked_reason`、
    `state`、`capability`、`raw_result`。
- 證據：
  - `timeout 120s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
    - `55 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    - `321 passed`
  - `timeout 60s git diff --check`
    - 通過
- 本輪剩餘：
  - 驗收 launcher -> MainWindow -> chat panel -> blocked-command product flow。
  - 逐步把 real tool execution 由 legacy facade string surface 推進到直接回傳 backend `CommandResult`。

### 04:46 Resource-safe autopilot 恢復與 worktree checkpoint 規劃

- 做了什麼：
  - 依使用者指示切到 resource-safe execution：重型任務一次只跑一個、所有可能卡住的測試 / UI / LLM / docs build 都要加 `timeout`。
  - 確認沒有殘留的 `pytest`、`python run.py`、local model health check、download 或 GUI 常駐 process。
  - 重新讀取 `git status --short`、`git diff --stat`、`AGENTS.md`、planning / roadmap / architecture / validation / worklog / implementation log 的恢復點。
  - 將 current-facing 文件中把本輪交付缺口寫成「後續」的語意改成「本輪剩餘 / 目前執行中」，避免下一個 agent 誤判成可延後事項。
- 結果：
  - 目前判斷不是重做 Milestone 1，而是從已完成的 backend baseline、UI/agent readiness、local LLM smoke、launcher baseline 繼續收斂。
  - `tests/unit/llm` 重新跑通；中途發現 coverage-booster tests 還停在舊 downloader / controller / worker / engine contract，已修成目前 contract 並移除無限 queue mock。
  - 接下來先跑 docs / diff 靜態驗證，再做 coherent checkpoint commit，不把整個 dirty worktree 一次吞掉。
- 證據：
  - `timeout 30s ps -ef | rg 'poetry|pytest|python run.py|inspect_local_assistant_runtime|plan_local_model_download|mkdocs|xvfb|huggingface|transformers|pip|uvicorn|jupyter'`
    - 無殘留 heavy process。
  - `timeout 60s git status --short`
    - worktree 仍有 docs cleanup、backend application service、UI / agent command surface、local LLM / launcher、validation / public fixture 等多類變更，需分批 commit。
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/core/test_model_catalog.py tests/unit/scripts/test_plan_local_model_download.py tests/unit/scripts/test_inspect_local_assistant_runtime.py tests/unit/llm/core/test_config.py tests/unit/llm/core/test_downloader.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py tests/unit/llm/agent/test_worker.py tests/unit/llm/test_controller_coverage.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_local_bootstrap_validation.py -q`
    - `183 passed`
  - `timeout 240s poetry run pytest --capture=sys tests/unit/llm -q -x`
    - `647 passed`
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過
  - `timeout 60s git diff --check`
    - 通過
  - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `55 passed`
  - `timeout 120s git commit -m "backend: add application service command core"`
    - `a6f0175`
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_local_bootstrap_validation.py tests/unit/ui/test_workflow.py -q`
    - `115 passed`
  - pre-commit 首次檢查擋下 local runtime / launcher checkpoint：修正 ruff 長行、測試假 key allowlist、launcher path false positive、以及舊 coverage tests。
  - 重新跑：
    - `timeout 240s poetry run pytest --capture=sys tests/unit/llm -q -x`
      - `647 passed`
    - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_local_bootstrap_validation.py tests/unit/ui/test_workflow.py -q`
      - `115 passed`
  - `timeout 180s git commit -m "assistant: unify command surface and local runtime"`
    - `38d3f00`
  - `timeout 120s poetry run mkdocs build --strict`
    - 通過；用於驗收 docs cleanup / current-facing docs patch。
  - data / validation chunk：
    - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/load_data/test_raw_data_loader.py tests/unit/scripts/test_report_dataset_validation_matrix.py tests/unit/scripts/test_run_public_cross_source_training_smoke.py -q`
      - `10 passed`
    - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
      - `31 passed, 8 warnings`
    - `timeout 300s poetry run pytest --capture=sys tests/integration/pipeline/test_checked_in_real_dataset_validation.py -q`
      - `6 passed`
    - `timeout 300s poetry run pytest --capture=sys tests/integration/pipeline/test_public_cross_source_training_smoke.py -q`
      - `4 passed, 3 warnings`
  - UI/type/artifact chunk：
    - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
      - `810 passed`
- 本輪剩餘：
  - 先提交 local LLM runtime + launcher + docs correction checkpoint。
  - 再盤點並提交 backend / UI-agent / docs cleanup / validation chunks。

### 02:08 Local LLM runtime / launcher product baseline

- 做了什麼：
  - 依使用者限制移除舊 Qwen cache，並把 benchmark script 裡可執行的 Qwen local model
    entry 改成 product catalog 內的 Phi model。
  - 新增/收斂 local model catalog、下載 preflight、runtime inspection、primary/fallback
    health check。
  - 下載 primary `microsoft/Phi-4-mini-instruct` 和 fallback
    `microsoft/Phi-3.5-mini-instruct`，總 cache 約 `15.34GB`。
  - 修正 local backend 對 Phi remote code / Transformers cache API 的 compatibility，
    並讓 generation thread exception 能回傳錯誤，不再讓 smoke 卡住。
  - AgentManager 第一次開 chat panel 不再強迫 settings modal；runtime 不可用時面板仍可開，
    並顯示明確原因。
  - 建立 Windows launcher `.cmd` / `.ps1`，並複製 `.cmd` 到 Desktop。
- 結果：
  - 中國公司或中國來源模型不再是 product local runtime 候選；Qwen cache 已刪。
  - primary / fallback local model 都可在 CUDA 上完成 prompt smoke 和 structured-output smoke。
  - startup smoke 顯示 `MainWindow initialized`，GUI timeout 結束屬預期。
- 證據：
  - `poetry run python scripts/dev/plan_local_model_download.py --model microsoft/Phi-3.5-mini-instruct --format markdown`
    - `ok: True`，projected cache `15.33 GB`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
    - primary prompt smoke `passed`
    - primary structured-output smoke `passed`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
    - fallback prompt smoke `passed`
    - fallback structured-output smoke `passed`
  - `timeout 35s xvfb-run -a poetry run python run.py --model local`
    - `MainWindow initialized` 後 timeout
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py tests/unit/ui/components/test_agent_manager.py -q`
    - `66 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py -q`
    - `18 passed`
- 本輪剩餘：
  - 需要完成 launcher -> chat panel -> agent blocked-command 的互動式 walkthrough。
  - API / Gemini code path 仍是待移除殘留，不是產品目標。

### 01:38 Product delivery 文件指令校準

- 做了什麼：
  - 全面掃描 `docs/`、`.agents/`、`AGENTS.md`、`README.md` 的 current-facing 文件。
  - 找到 `docs/planning/now.md`、`docs/index.md`、`docs/planning/roadmap.md`、
    `docs/validation/README.md`、`.agents/runbooks/*` 等仍殘留文件整理期 /
    全盤架構複盤期的保守指令。
  - 將這些入口統一改成 product-delivery engineering：backend、UI、agent、
    local LLM、desktop launcher、product stabilization，且 tool-call eval 等產品主線穩定後再做。
- 結果：
  - 下一個 agent 不應再被「不開工 / 先全盤複盤 / 只做後端 baseline」的舊文字拉回保守模式。
  - milestone 被明確定位為最低交付門檻，不是工作上限。
- 證據：
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check -- docs .agents AGENTS.md README.md mkdocs.yml`
    - 通過
  - stale instruction scan：
    - current-facing 文件已沒有過期停止條件；records 內歷史語句保留為歷史紀錄。
- 本輪剩餘：
  - 下一個工程 agent 可直接按 `AGENTS.md` 和 `docs/planning/now.md` 推進 product delivery。

### 01:04 UI / Agent command surface unification

- 做了什麼：
  - 依成熟工程驗收標準回頭檢查 Milestone 1，發現 `preprocess` capability 原本用
    `has_preprocessed_data` 當前置條件，會讓 raw-only state 的 readiness 判斷失真。
  - 修正 capability policy：preprocess 現在要求 raw data，而 create epoch 才要求
    preprocessed data。
  - 新增 `XBrainLab/llm/tools/application_surface.py`，把 agent tools 對映到
    ApplicationService commands，讓 prompt tool list 與 execution guard 都讀同一套
    backend capability policy。
  - Chat panel 補 retry / clear controls、compact backend/model status；AgentManager
    補 retry、debug tool 接線和 backend diagnostics refresh。
  - UI readiness 第一批接到 ApplicationService policy：dataset import、preprocess、
    epoching、start training。
  - Agent tool output 寫回 structured JSON payload，保留 `ok`、`tool_name`、
    `message`、`raw_result`。
  - 補 UI / agent command surface tests。
- 結果：
  - load / preprocess / epoch / dataset / train / reset 主 workflow 的 availability 判斷
    已由 ApplicationService capability policy 產生。
  - UI 和 Agent 對同一 blocked command 會看到同一套 backend reason。
  - UI action execution 仍有 legacy controller path，但 UI-facing decision 已開始共用
    service policy。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
    - `9 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `44 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    - `318 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
    - `807 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
    - `2 passed`
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check`
    - 通過
- 本輪剩餘：
  - 下一步要把更多 UI action execution 改成 command adapter，而不是只讀 policy。
  - Agent real tools 仍需要更完整地直接消費 `CommandResult`，目前 history 已保留
    structured tool output，但 UI side effects 還是 `Request:` 字串協定。

### 00:23 Backend Application Service contract 驗收收斂

- 做了什麼：
  - 跑第二輪基準驗收：targeted backend/facade tests、MkDocs strict、diff whitespace 都先通過。
  - 開四個 auditor 檢查 command contract、facade parity、workflow test depth、dirty worktree scope。
  - 補齊 `evaluate` / `visualize` / `saliency` / `new_session` 的 future command objects，並在 policy 中標成 unavailable。
  - 將 service 內 `set_montage` 從假成功改成 confirmation-required failure，保留 `BackendFacade.set_montage()` legacy path。
  - 補強 `reset_session`，讓它清掉 active session 的 raw / preprocess / epoch / dataset / trainer / model option / saliency config。
  - 修正 `BackendFacade.load_data()` total failure 的舊 `(count, errors)` shape，並讓 inactive `stop_training()` 不再靠錯誤訊息字串判斷。
  - 補 application unit tests、low-mock integration workflow tests、facade parity tests。
- 結果：
  - CommandName、command dataclass、CapabilityPolicy、execute router 已對齊。
  - 未實作 command 不再被 policy 宣稱可用，也不會掉進 router `KeyError`。
  - workflow test 已覆蓋 load -> epoch -> dataset -> training readiness -> reset invalidation，以及 failed command last_error lifecycle。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `54 passed`
  - `poetry run pytest --capture=sys tests/unit/backend -q`
    - `2660 passed, 1 skipped, 1 xfailed`
  - `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
    - `33 passed`
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
    - `70 passed`
  - `poetry run ruff check XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py`
    - 通過
  - `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py`
    - `0 errors`
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check`
    - 通過
  - `poetry run python scripts/dev/update_quality_dashboard.py`
    - `Overall status: PASS`
- 後續：
  - 下一輪補 facade/controller parity real workflow，並設計 evaluation / visualization / saliency query command contract。

## 2026-05-01

### 23:49 Backend refactor validation 收尾

- 做了什麼：
  - 跑完 backend unit、backend+IO integration、full pipeline、MkDocs strict、diff whitespace 和 quality dashboard。
  - 修正 `RealListFilesTool` 在 WSL/Linux 下把不存在的 Windows fallback path resolve 成 repo root，導致 `tests/data` 被誤判為敏感目錄的問題。
- 結果：
  - 後端 Application Service slice 與既有 IO / pipeline smoke 都通過。
  - `artifacts/quality/latest.md` 已更新為 `PASS`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend -q`
    - `2651 passed, 1 skipped, 1 xfailed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/integration/io/test_io_integration.py -q`
    - `32 passed`
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
    - `70 passed`
  - `poetry run mkdocs build --strict`
    - 通過
  - `git diff --check`
    - 通過
  - `poetry run python scripts/dev/update_quality_dashboard.py`
    - `Overall status: PASS`
- 後續：
  - UI service-first migration、`set_montage()` command 化、agent tools 直接消費 `CommandResult`。

### 23:41 Backend Application Service 第一版

- 做了什麼：
  - 先盤點 dirty worktree：文件整理 / validation / backend / UI+LLM 變更混在一起，保留既有合理成果，不清空 worktree。
  - 開 subagents 盤點 backend 架構、test quality、Application Service 設計與 implementation readiness。
  - 新增 `XBrainLab/backend/application/`，包含 commands、state snapshot、capability policy、command result、error boundary 和 `ApplicationService`。
  - 將 `BackendFacade` 核心 workflow 改成透過 `ApplicationService` 執行，保留舊 API 形狀給 assistant tools / scripts。
  - 新增 service contract unit tests 和 synthetic real backend workflow integration test。
- 結果：
  - `BackendFacade` 不再是核心 workflow 邏輯聚集點；它現在是 command API wrapper。
  - backend 可由 state snapshot 判斷 raw / preprocess / epoch / dataset / training / evaluation / visualization 狀態。
  - capability policy 可由 backend state 阻擋缺前置條件 command。
- 證據：
  - `XBrainLab/backend/application/`
  - `tests/unit/backend/application/test_application_service.py`
  - `tests/integration/backend/test_application_service_workflow.py`
  - `poetry run pytest --capture=sys tests/unit/backend -q`
    - `2651 passed, 1 skipped, 1 xfailed`
  - `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py`
    - `0 errors`
- 後續：
  - 跑 pipeline / IO / docs validation。
  - 補更多 state invalidation、training readiness、facade/controller parity tests。

### 23:04 .agents 工程 workflow skill pack 校準

- 做了什麼：
  - 新增 TDD、測試品質、code review、software design review skills。
  - 新增 `tdd-change` 和 `test-audit` workflows。
  - 將 context 文件降級成 source-of-truth 導讀，不重寫架構。
- 結果：
  - `.agents` 從專案文件操作層，補上更通用的軟體工程 workflow。
  - skills 設計方向改成參考成熟 AI coding / TDD / review workflow，再套到 XBrainLab。
- 證據：
  - `.agents/skills/`
  - `.agents/workflows/`
  - `.agents/context/`
- 後續：
  - MkDocs strict、diff whitespace、agent skill/workflow scan 已通過。

### 22:55 .agents skills / workflows 第一版

- 做了什麼：
  - 新增 `.agents/skills/` 與 `.agents/workflows/`。
  - 建立 docs-curator、architecture-reviewer、validation-runner、refactor-slicer、agent-toolcall-designer 五個 skill。
  - 建立 documentation-review、architecture-review、refactor-slice、agent-toolcall-scoring 四個 workflow。
  - 更新 `.agents/README.md`、`.agents/stack.md`、setup、autopilot、active queue。
- 結果：
  - `.agents` 不再只有 runbook / context，而有可重用能力與多步驟流程。
  - 舊 `xbrainlab-*` skills 仍不恢復；新 skills 對齊目前 canonical docs。
- 證據：
  - `.agents/skills/`
  - `.agents/workflows/`
- 後續：
  - 跑 MkDocs strict、diff whitespace、agent file scan。

### 22:52 blocked commands 定位

- 做了什麼：
  - 補充 `blocked_commands` 的用途與暴露邊界。
  - 明確寫出完整 blocked list 不應直接塞給 LLM。
- 結果：
  - `blocked_commands` 保留給 verifier、scorer、debug、UI diagnostics。
  - Context Assembler 只在和使用者當前意圖相關時摘要 blocked reason。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 blocked command wording scan 已通過。

### 22:48 Active dataset pipeline 邊界校準

- 做了什麼：
  - 將多 dataset 的說法收斂成一個 active dataset pipeline。
  - 明確寫出 epoch / dataset 形成後，不應讓 agent 一般性地 load new data / 開新 dataset。
  - 將載入新資料改成 reset / new session / fork 類高風險 command，需要確認。
- 結果：
  - 目標狀態支援同一 dataset 上多個 run / result，但不支援同時任意開多個 active dataset。
  - capability policy 需在 epoch / dataset 後阻擋一般 load new data。
- 證據：
  - `docs/target/agent.md`
  - `docs/target/architecture.md`
  - `docs/architecture/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 active dataset wording scan 已通過。

### 22:47 多資源不等於任意並行

- 做了什麼：
  - 修正 target agent / architecture 對多資源 workflow 的描述。
  - 補明確 dependency gate：沒 data 不能 preprocess、沒 dataset 不能 training、沒 trained result 不能 saliency。
- 結果：
  - 多資源 / 多 job 表示狀態可以共存，不代表所有 command 都能同時或任意執行。
  - capability policy 需要針對每個 target resource 判斷可執行性。
- 證據：
  - `docs/target/agent.md`
  - `docs/target/architecture.md`
  - `docs/architecture/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 dependency wording scan 已通過。

### 22:45 Command gate 與多資源 workflow 校準

- 做了什麼：
  - 將 `available_commands` 改成 backend / Application Service capability policy 的輸出。
  - 在 State Snapshot 補 `capability_policy`、`active_jobs`、`completed_runs`。
  - 補上 workflow state 不應是單一路徑，而應支援多資料、多 training run、visualization / saliency 和下一筆 training 並行。
  - 同步 `target/architecture.md` 和 `architecture/agent.md`。
- 結果：
  - agent 不再被設計成拿全部 tool 自己猜；backend 應控制可用 capability。
  - target state model 開始支援 resources / jobs / results，而不是只靠 `workflow_stage`。
- 證據：
  - `docs/target/agent.md`
  - `docs/target/architecture.md`
  - `docs/architecture/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 capability wording scan 已通過。

### 22:42 Target agent 補四個 contract 外框

- 做了什麼：
  - 將 State Snapshot、Tool Call、Verification Result、Scoring 四個 contract 寫進 `docs/target/agent.md`。
  - 保持在外框規格，不展開每個具體 tool schema。
- 結果：
  - target agent 從流程概念變成可開工前討論的 contract 草案。
  - 後續可以在 backend command surface 定下來後補實際 schema。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 contract wording scan 已通過。

### 22:40 Target agent Mermaid 圖修正

- 做了什麼：
  - 將 `docs/target/agent.md` 的 Mermaid 從 subgraph-heavy layout 改成 left-to-right 單線流程。
  - 移除造成圖面拉歪的 Prompt subgraph 與交叉回饋線。
- 結果：
  - 圖面更接近：prompt inputs -> Context Assembler -> LLM -> Verification -> Backend / Self-correction -> State feedback。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - 跑 MkDocs strict 和 diff whitespace 檢查。

### 22:37 Thesis evidence 改成 tool-call scoring system

- 做了什麼：
  - 將 thesis evidence 從泛稱 evidence 改成要建立 agent tool-call scoring system。
  - 在 `target/agent.md` 補分項準確率、benchmark case 類型與失敗 taxonomy。
  - 在 `validation/README.md` 補 Agent Tool-Call Scoring 區塊。
- 結果：
  - thesis evidence 的目標更具體：要有可重跑 benchmark、scorer、report / artifact。
  - 舊 Gemini/API benchmark 被標成歷史參考，新的 scorer 要對齊 local-only runtime 和新 command surface。
- 證據：
  - `docs/target/requirements.md`
  - `docs/target/agent.md`
  - `docs/validation/README.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 scoring wording scan 已通過。

### 22:35 Target agent 補 State Manager / Verification Layer

- 做了什麼：
  - 在 `docs/target/agent.md` 加入 target control loop Mermaid 圖。
  - 補 Context Assembler、State Manager、Verification Layer、Self-Correction 的目標責任。
  - 補 tool schema 應標示的 contract 欄位。
- 結果：
  - agent 目標文件不再只描述 tool-call，而是記錄完整狀態管理與驗證閉環。
  - 使用者提供的設計被納入 target 文件，後續可作為 agent redesign 的基準。
- 證據：
  - `docs/target/agent.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 target agent wording scan 已通過。

### 22:32 Target requirements 補 XBrainLab 本體

- 做了什麼：
  - 補強 `docs/target/requirements.md` 對 XBrainLab 本體的描述。
  - 將需求從 assistant / command API 前移到 EEG desktop workflow 本身。
  - 修正 `docs/target/README.md` 仍殘留的 API / Gemini 待簡化說法。
- 結果：
  - requirements 現在先說清楚資料匯入、label/event、preprocess、dataset、training、evaluation、visualization 這些本體需求。
  - assistant 被定位成同一套 workflow 的操作層，不再壓過 XBrainLab 本體。
- 證據：
  - `docs/target/requirements.md`
  - `docs/target/README.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 target wording scan 已通過。

### 22:30 API / Gemini 移除決策校準

- 做了什麼：
  - 將 API / Gemini code path 從「待簡化 / compatibility」改成「後續要移除」。
  - 同步 current、architecture、validation、planning、decisions 和 `.agents` 文件。
- 結果：
  - local-only 不再只是抽象方向，而是排除 API / Gemini 產品路線的明確決策。
  - 實作上仍不在本輪文件整理直接拔除，避免在架構複盤前擴大改動。
- 證據：
  - `docs/decisions/README.md`
  - `docs/architecture/agent.md`
  - `docs/planning/roadmap.md`
  - `.agents/runbooks/active-queue.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 active wording scan 已通過。

### 22:26 Documentation audit 收束

- 做了什麼：
  - 刪除 `docs/records/documentation_audit.md`。
  - 移除 README、MkDocs nav、`docs/current.md`、`.agents/runbooks/*` 對它的 active 引用。
- 結果：
  - `records/` 回到只承載 implementation log 和 worklog。
  - 文件可信度不再獨立成一張表，而是回到 current、architecture、validation、decisions 各自維護。
- 證據：
  - `README.md`
  - `docs/current.md`
  - `mkdocs.yml`
  - `.agents/runbooks/setup.md`
  - `.agents/runbooks/autopilot.md`
- 後續：
  - MkDocs strict、diff whitespace 檢查與 active stale reference scan 已通過。

### Workspace 搬遷確認

- 做了什麼：
  - 將 active repo 建立在 `/mnt/d/workspace_v2/projects/lab/XBrainLab`。
  - 舊 `/mnt/d/repos/XBrainLab` 保留為備援 / 參考副本。
- 結果：
  - active repo path 已確認。
  - branch 和 remote 保留。
- 證據：
  - branch: `codex/stabilization-autopilot`
  - remote: `https://github.com/hxin-an/XBrainLab.git`
- 後續：
  - active 文件中避免再把舊路徑當成 current truth。

### 文件結構重整

- 做了什麼：
  - 將文件切成 `docs/`、`docs/architecture/`、`docs/legacy/`。
  - 舊 agent 文件、舊 current、舊 ADR、history、archive 移到 `legacy/`。
- 結果：
  - current truth 和 historical reference 已分離。
- 證據：
  - `docs/index.md`
  - `docs/README.md`
  - `docs/legacy/README.md`
- 後續：
  - 從 legacy 抽可信內容時，先對 source code / runtime evidence。

### 新 Poetry 環境建立

- 做了什麼：
  - 在新 workspace 執行 `poetry install --with dev,test,docs`。
- 結果：
  - 標準開發、測試、文件工具鏈可用。
- 證據：
  - Poetry env: `/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12`
  - import probe 通過：`PIL`、`mne`、`PyQt6`、`torch`、`pytest`、`XBrainLab`
- 後續：
  - optional `llm` group 尚未安裝，local LLM / `torchinfo` 不能算已驗證。

### Dashboard 第一次刷新

- 做了什麼：
  - 執行 `scripts/dev/update_quality_dashboard.py`。
- 結果：
  - dashboard 可在新 workspace 產生。
  - 第一次結果有兩個 UI unit failure 和一個 UI baseline failure。
- 證據：
  - `test_on_plan_select_success` 因缺 `torchinfo` 失敗。
  - `test_set_model` 期待 `Gemini`，但實際 runtime key 是 `gemini`。
  - `ai-assistant-open.png` live artifact 尺寸和 current worktree reference 不同。
- 後續：
  - 判斷 UI unit failure 是測試邊界問題，不是 app 行為壞掉。

### UI unit test 修正

- 做了什麼：
  - `tests/unit/ui/test_model_summary.py` 改用 fake `torchinfo` module。
  - `tests/unit/ui/test_ui_misc.py` 對齊 `LLMConfig.normalize_backend_mode()`，期待 `gemini`。
- 結果：
  - targeted UI tests 通過。
- 證據：
  - `2 passed`
- 後續：
  - `torchinfo` 保持 optional `llm` dependency，不要求標準 `dev,test` env 安裝。

### Dashboard 第二次刷新

- 做了什麼：
  - 重新執行 fast quality dashboard。
- 結果：
  - dashboard overall 仍是 `FAIL`。
  - 失敗只剩 `UI Baseline Capture`。
- 證據：
  - generated at: `2026-05-01 19:16:09 UTC+08:00`
  - workspace: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - Ruff Lint: `PASS`
  - Basedpyright: `PASS`
  - Architecture Compliance: `PASS`
  - Startup Smoke: `PASS`
  - UI Dialog Acceptance: `PASS`
  - UI Unit Suite: `PASS` (`799 passed`)
  - Real-Data IO Integration: `PASS` (`31 passed`)
- 後續：
  - 決定 `tests/baselines/ui/ai-assistant-open.png` 要採用哪個 approved reference。

### UI baseline 待決策

- 做了什麼：
  - 比對 `ai-assistant-open.png` 尺寸來源。
- 結果：
  - live artifact 是 `(1428, 800)`。
  - repo HEAD reference 是 `(1428, 800)`。
  - current dirty worktree reference 是 `(1523, 800)`。
- 證據：
  - `artifacts/ui/ai-assistant-open.png`
  - `tests/baselines/ui/ai-assistant-open.png`
- 後續：
  - 建議接受 `(1428, 800)` 作為 approved baseline，再重跑 dashboard 取得 clean `PASS`。

### 文件站點驗證

- 做了什麼：
  - 修正 legacy current README 的 active 文件連結。
  - 讓 MkDocs 排除 legacy API stub。
  - 執行 `poetry run mkdocs build --strict`。
- 結果：
  - MkDocs strict build 通過。
- 證據：
  - active / architecture 連結檢查：`MISSING=0`
  - `mkdocs build --strict` exit 0
- 後續：
  - legacy 裡沒有進 nav 的頁面保留為 reference，不當成 active 文件站點核心內容。

### UI baseline 決策

- 做了什麼：
  - 接受 `artifacts/ui/ai-assistant-open.png` 作為 `tests/baselines/ui/ai-assistant-open.png` 的 approved baseline。
- 結果：
  - baseline reference 從 dirty worktree 的 `(1523, 800)` 對齊到 `(1428, 800)`。
  - 這個尺寸和 live artifact、repo HEAD reference 一致。
- 證據：
  - live artifact: `(1428, 800)`
  - repo HEAD reference: `(1428, 800)`
  - current reference: `(1428, 800)`
- 後續：
  - 重跑 fast quality dashboard。

### Dashboard clean PASS

- 做了什麼：
  - 執行 `/home/administrator/.local/bin/poetry run python scripts/dev/update_quality_dashboard.py`。
- 結果：
  - dashboard overall 從 `FAIL` 變成 `PASS`。
  - 所有 fast checks 都是 `pass`。
- 證據：
  - generated at: `2026-05-01 19:28:48 UTC+08:00`
  - workspace: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - Ruff Lint: `PASS`
  - Basedpyright: `PASS`
  - Architecture Compliance: `PASS`
  - Startup Smoke: `PASS`
  - UI Baseline Capture: `PASS`
  - UI Dialog Acceptance: `PASS`
  - UI Unit Suite: `PASS` (`799 passed`)
  - Real-Data IO Integration: `PASS` (`31 passed`)
- 後續：
  - 進入 legacy 文件抽樣驗證，不再卡在工程基準是否健康。

### Pipeline smoke 抽樣

- 做了什麼：
  - 檢查現有 `tests/integration/pipeline/`。
  - 跑兩個代表性的 tiny pipeline smoke。
- 結果：
  - 已有 synthetic train/evaluate 和 Study facade train cycle 測試。
  - targeted smoke 通過。
- 證據：
  - `tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics`
  - `tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet`
  - `2 passed in 7.54s`
- 後續：
  - 在 `validation/README.md` 定義 pipeline validation 分層。
  - 在 `planning/roadmap.md` 記錄是否要把 tiny pipeline smoke 加入 fast dashboard。

### Roadmap 對齊 repo legacy 進度報告

- 做了什麼：
  - 對照 `docs/legacy/current/STATUS_REPORT.md` 的 `Next Review Focus`。
  - 對照 `docs/legacy/current/PLAN.md` 的高層順序。
- 結果：
  - `planning/roadmap.md` 不再只用臨時整理路線，而是對齊舊進度報告的方向：
    - stabilization first
    - agent redesign second
    - validation throughout
  - 下一階段改成 dataset / pipeline reproducibility baseline、supported desktop/runtime matrix，然後才進 phase-5 tool-call redesign。
- 證據：
  - `STATUS_REPORT.md` 指出 phase 5 尚未開始。
  - `STATUS_REPORT.md` 的候選下一步包含 local-only cross-source evidence、desktop/local runtime matrix、bounded phase-5 item。
- 後續：
  - 審 `BUG_TRIAGE.md` 和 `STATUS_REPORT.md` 時，優先確認這些方向還有哪些 claims 需要降級或補 evidence。

### 21:07 Agent 架構文件整理

- 做了什麼：
  - 對照 `ChatPanel`、`AgentManager`、`LLMController`、`AgentWorker`、`LLMConfig`、`pipeline_state`、tool registry 和 real tools。
  - 重寫 `docs/architecture/agent.md`。
- 結果：
  - agent 文件改成描述目前真實路徑：UI -> AgentManager -> LLMController -> worker / parser / verifier / tools -> BackendFacade -> Study。
  - 文件明確標出目前是可工作的中間狀態，未來目標是 UI / Agent / Script 共用 Application Service / Command API。
- 證據：
  - `docs/architecture/agent.md`
  - `docs/records/documentation_audit.md`
- 後續：
  - local LLM、RAG 品質、多步 tool-call workflow 仍要做 runtime 驗證；Gemini/API 之後不再作為產品驗證目標。

### 21:09 Assistant runtime 改為 local-only 目標

- 做了什麼：
  - 根據新的產品判斷，將未來 assistant runtime 方向改成 local-only。
  - 更新 `docs/architecture/agent.md`、`docs/decisions/README.md`、`docs/validation/README.md`。
- 結果：
  - Gemini/API 不再是未來產品驗證目標。
  - source code 目前仍保留 Gemini/API 分支，文件明確標為待簡化的 current code state。
- 證據：
  - `docs/architecture/agent.md`
  - `docs/decisions/README.md`
  - `docs/validation/README.md`
- 後續：
  - 等文件整理完成後，再把 agent runtime 簡化列入後端 / agent 重構範圍。

### 21:21 Active / architecture 文件校準

- 做了什麼：
  - 平行整理 `current.md`、`operations.md`、`ui.md`、`validation.md`。
  - 同步更新 `docs/index.md`、`docs/architecture/README.md`、`planning/roadmap.md`、`records/documentation_audit.md`。
- 結果：
  - active 入口現在清楚標示：先看 canonical 文件，使用者 review 後清 legacy，legacy 清完再審後端。
  - UI 架構文件已記錄 `MainWindow`、五個 panels、controller 取得方式、observer bridge、AgentManager、InfoPanelService。
  - validation architecture 已更新為 2026-05-01 dashboard 現況，不再停在 2026-04-19。
- 證據：
  - `docs/current.md`
  - `docs/operations.md`
  - `docs/architecture/ui.md`
  - `docs/architecture/validation.md`
  - `docs/records/documentation_audit.md`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check` exit 0。
- 後續：
  - 使用者 review 後開始清 legacy 文件。

### 21:27 Roadmap 加入全盤架構複盤 gate

- 做了什麼：
  - 根據使用者判斷，將清完 legacy 後的下一步改為全盤架構複盤。
  - 更新 `planning/roadmap.md`、`current.md`、`decisions/README.md`。
- 結果：
  - Roadmap 不再是 legacy 清完就直接進後端。
  - 新順序是：canonical 文件 review -> legacy 清理 -> 全盤架構複盤 -> 後端重構審視。
- 證據：
  - `docs/planning/roadmap.md`
  - `docs/current.md`
  - `docs/decisions/README.md`
- 後續：
  - 使用者 review 文件後，先清 legacy；清完再一起重新討論整體架構。

### 21:39 Docs legacy 整合後刪除

- 做了什麼：
  - 依使用者指示，改用「整合後刪除」策略，而不是保留短期 snapshot。
  - 刪除 `docs/legacy/current/`、`decisions/`、`workflows/`、`guides/`、`api/`、`thesis/`、`history/`。
  - 更新 `docs/legacy/README.md`、`mkdocs.yml`、`current.md`、`records/documentation_audit.md`、`planning/roadmap.md`。
  - 補充 test mock-heavy 判讀到 `validation/README.md` 和 `validation.md`。
- 結果：
  - `docs/legacy/` 現在只保留 `archive/` 與 legacy README。
  - test health 判讀明確區分 mock-heavy regression floor 與真正 non-mocked evidence。
- 證據：
  - `docs/legacy/README.md`
  - `docs/validation/README.md`
  - `docs/architecture/validation.md`
  - `poetry run mkdocs build --strict` exit 0。
- 後續：
  - 接著處理 `.agents/legacy/`；`docs/legacy/archive/` 先保留。

### 21:50 Agent legacy 整合後刪除

- 做了什麼：
  - 刪除 `.agents/legacy/`。
  - 更新 `AGENTS.md`、`.agents/stack.md`、`.agents/runbooks/active-queue.md`、`autopilot.md`、`setup.md`、`session-prompts.md`。
  - 同步 `current.md`、`planning/roadmap.md`、`records/documentation_audit.md`、`docs/index.md`、`architecture/README.md`。
- 結果：
  - active agent 操作層只剩少數入口：stack、runbooks、thesis context。
  - 舊 role、skill、AQ queue、workflow、multi-session prompt 不再留在 repo reading surface。
  - 下一步改成全盤架構複盤，不直接跳後端重構。
- 證據：
  - `test ! -e .agents/legacy` -> `.agents/legacy removed`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` exit 0。
- 後續：
  - 開始全盤架構複盤。

### 21:58 Docs legacy 完全收掉

- 做了什麼：
  - 刪除整個 `docs/legacy/`。
  - 從 `mkdocs.yml` 移除 Legacy nav。
  - 更新 `README.md`、`AGENTS.md`、`.agents/stack.md`、`current.md`、`planning/roadmap.md`、`records/documentation_audit.md`、`docs/index.md`、`architecture/README.md`。
- 結果：
  - repo 文件閱讀面只剩 `docs/` 與 `docs/architecture/`。
  - `docs/legacy/` 和 `.agents/legacy/` 都不再存在。
  - 下一步仍是全盤架構複盤。
- 證據：
  - `test ! -e docs/legacy` -> `docs/legacy removed`
  - `test ! -e .agents/legacy` -> `.agents/legacy removed`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` exit 0。
  - stale link scan 沒有 active nav / markdown link 指回 `docs/legacy/`。
- 後續：
  - 重新審視 canonical / architecture 文件是否還有重疊、膨脹或可信度不清的地方。

### 22:02 Active folder 收掉

- 做了什麼：
  - 將 `docs/active/*.md` 搬到 `docs/` 根層。
  - 刪除 `docs/active/README.md` 和空的 `docs/active/`。
  - 將 MkDocs nav 從 `Active` 改成 `Core`。
  - 更新 `README.md`、`AGENTS.md`、`.agents/*`、`docs/index.md`、architecture 文件與 thesis context link。
- 結果：
  - docs 只剩根層 canonical 文件與 `architecture/`。
  - 文件入口少一層，讀者不需要再理解 active / legacy 分區。
- 證據：
  - `test ! -e docs/active` -> `docs/active removed`
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` exit 0。
  - stale path scan 沒有 active markdown link 指向已刪除資料夾。
- 後續：
  - 重新審視 canonical / architecture 文件是否還有重疊、膨脹或可信度不清的地方。

### 22:05 Root homepage 文件收斂

- 做了什麼：
  - 刪除 root `ROADMAP.md`。
  - 更新 `README.md`，改指向 `docs/planning/roadmap.md`。
  - 更新 `CHANGELOG.md` 開頭，標成歷史版本紀錄，不再承載 current plan。
  - 更新 `current.md` 和 `records/documentation_audit.md`。
- 結果：
  - 現在只有一份 roadmap source-of-truth：`docs/planning/roadmap.md`。
  - root homepage 不再把舊 Track A/B roadmap 當重要文件。
- 證據：
  - `test ! -e ROADMAP.md` -> root `ROADMAP.md` removed。
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- README.md CHANGELOG.md planning/roadmap.md AGENTS.md .agents docs mkdocs.yml` exit 0。
- 後續：
  - 重新審視 README / docs index 是否還有多餘入口。

### 22:21 文件資訊架構第一版

- 做了什麼：
  - 將 docs 重排為 current / operations / target / architecture / planning / decisions / validation / records。
  - 寫第一版 `docs/target/`：requirements、target architecture、target agent。
  - 寫第一版 `.agents/README.md`、project context、architecture target context。
  - 寫第一版 `.agents/runbooks/architecture-review.md` 與 `refactor-gate.md`。
  - 更新 MkDocs nav、README、AGENTS、`.agents/stack.md` 和 cross-links。
- 結果：
  - 需求 / 理想架構、現況架構、短期 / 長期規劃、決策、驗證、紀錄已分開。
  - 下一步可以由使用者 review 文件架構，再進全盤架構複盤。
- 證據：
  - `poetry run mkdocs build --strict` exit 0。
  - `git diff --check -- README.md CHANGELOG.md AGENTS.md .agents docs mkdocs.yml` exit 0。
  - stale path scan 沒有 active markdown link 指向舊大寫 canonical 檔名、`docs/active/`、`docs/legacy/` 或 `validation_architecture.md`。
- 後續：
  - 使用者 review 第一版文件架構。

### 19:56 Agent 文件清理

- 做了什麼：
  - 掃描 `AGENTS.md` 和 `.agents/` 裡的舊引用。
  - 先將舊 `AQ-*` queue、role、skill、workflow、multi-session prompts 從 active agent 入口移除；當時暫存到 `.agents/legacy/`，21:50 已整合後刪除。
  - 重寫 `AGENTS.md`、`.agents/stack.md`、`.agents/runbooks/setup.md`、`.agents/runbooks/autopilot.md`、`.agents/runbooks/active-queue.md`。
- 結果：
  - active agent 入口不再指向 `docs/current/*`、`docs/history/*`、`docs/workflows/*`。
  - 舊 `Prep Gate` / `Repair Loop` / `AQ-*` 控制面不再是 current surface。
  - `.agents/context/thesis.md` 保留為 agent-facing thesis context。
- 證據：
  - `.agents/runbooks/active-queue.md`
  - `AGENTS.md`
  - active stale-reference scan 沒有發現舊路徑作為 current reading order；剩下的命中都是禁用 / 歷史說明。
  - `poetry run mkdocs build --strict` exit 0。
- 後續：
  - 後續已在 21:50 完成 `.agents/legacy/` 整合後刪除。

### Roadmap 對齊 2026-04-26 會議進度報告

- 做了什麼：
  - 讀取 `/mnt/d/workspace_v2/core/lab/meetings/progress/reports/2026-04-26.md`。
  - 以其中 `To Do List` 作為 active roadmap 的主要階段來源。
- 結果：
  - `planning/roadmap.md` 的階段路線改為：
    - GUI 重構
    - 建立新 Agent 架構
    - 後端重構
    - 穩定化
    - tool call 驗證
    - 優化迭代
  - 目前主線聚焦在後端重構與資料集測試，不提前跳到大規模 agent redesign。
- 證據：
  - 進度報告前次 TODO：繼續 XBrainLab 後端架構重構。
  - 本週延續方向：回到 XBrainLab 修後端、開始整理不同資料集。
- 後續：
  - 用 `BUG_TRIAGE.md` 驗證後端重構 claims。
  - 用 dataset matrix / pipeline smoke 整理不同資料集支援狀態。

### Roadmap 瘦身與順序修正

- 做了什麼：
  - 將 `planning/roadmap.md` 瘦身成短版。
  - 修正目前位置為 `文件整理與現況盤點`。
  - 將資料集測試併入穩定化階段，不再列成目前獨立主線。
- 結果：
  - 現在的順序是先整理文件、掌握目前狀態，再審視後端重構。
  - 資料集測試不提前拆出來，而是穩定化的一環。
- 證據：
  - `docs/planning/roadmap.md`
- 後續：
  - 下一步仍是文件整理與舊文件可信度判讀。

### Thesis context 移出 active

- 做了什麼：
  - 將 `docs/THESIS.md` 移到 `.agents/context/thesis.md`。
  - 從 active 文件清單和 MkDocs nav 移除 thesis 頁。
- 結果：
  - 人類 active 入口更乾淨，只保留目前狀態、路線、驗證、操作、決策和稽核。
  - 碩論背景改成 agent context，需要時再讀。
- 證據：
  - `.agents/context/thesis.md`
  - `docs/README.md`
  - `docs/index.md`
  - `mkdocs.yml`
- 後續：
  - thesis claim 仍要在 `validation/README.md` 裡保留邊界提醒，但不再作為 active 閱讀文件。

### 20:06 Backend 架構文件驗證

- 做了什麼：
  - 對照 `docs/architecture/backend.md` 與目前 source code。
  - 查 `facade.py`、`study.py`、`data_manager.py`、`training_manager.py`、controllers、`ui/main_window.py`、LLM real tools、pipeline state。
  - 重寫 backend 架構文件，區分 UI controller path 和 assistant/headless facade path。
- 結果：
  - 確認 `BackendFacade` 不是所有 UI workflow 的入口；UI panels 目前直接透過 `Study.get_controller(...)` 拿 controller。
  - 確認 `Study` 已拆出 `DataManager` / `TrainingManager`，但仍保留 backward-compatible delegation properties。
  - 確認 controllers 不是純薄轉接，仍含 import、preprocess copy/swap、training monitor 等 workflow logic。
- 證據：
  - `XBrainLab/ui/main_window.py`
  - `XBrainLab/backend/study.py`
  - `XBrainLab/backend/facade.py`
  - `XBrainLab/backend/controller/*.py`
  - `XBrainLab/llm/tools/real/*.py`
  - `poetry run pytest --capture=sys tests/unit/test_architecture.py -q` -> `3 passed`
  - `poetry run mkdocs build --strict` exit 0
- 後續：
  - 後端重構前，先盤點 controller 內哪些 logic 要保留在 controller，哪些應下沉到 manager / service。

### Backend 目標架構記錄

- 做了什麼：
  - 將 backend 理想方向寫入 `docs/architecture/backend.md`。
  - 使用者確認未來目標是重構成 UI / Agent / Script 共用 Application Service / Command API。
- 結果：
  - 目標方向明確化：UI、agent tools、scripts 應共用同一批 command，而不是各走一套流程。
  - `BackendFacade` 的目標角色被降成 assistant / script wrapper，而不是新的平行 backend。
- 證據：
  - `docs/architecture/backend.md`
  - `docs/decisions/README.md`
- 後續：
  - 後端重構前，先盤點 controller 裡的 workflow logic，再決定哪些抽成 service / command。

### 21:01 Data pipeline 架構文件驗證

- 做了什麼：
  - 對照 `docs/architecture/data_pipeline.md` 與目前 source code。
  - 查 `RawDataLoaderFactory`、raw loaders、`LabelImportService`、preprocessor、`Epochs`、`DatasetGenerator`、`Dataset`、`Trainer`。
  - 對照 real-data IO、checked-in GDF+MAT、public cross-source training smoke 測試。
- 結果：
  - 確認目前註冊 loader 格式是 `.set`、`.gdf`、`.fif`、`.fif.gz`、`.edf`、`.bdf`、`.cnt`、`.vhdr`。
  - 將 import、label/event、preprocess、epoch/dataset、training 分層寫清楚。
  - 明確區分 import evidence、dataset generation evidence、training smoke、thesis-grade reproducibility。
- 證據：
  - `XBrainLab/backend/load_data/raw_data_loader.py`
  - `XBrainLab/backend/services/label_import_service.py`
  - `XBrainLab/backend/dataset/epochs.py`
  - `XBrainLab/backend/dataset/dataset_generator.py`
  - `tests/integration/io/test_io_integration.py`
  - `tests/integration/pipeline/test_checked_in_real_dataset_validation.py`
  - `tests/integration/pipeline/test_public_cross_source_training_smoke.py`
  - `poetry run mkdocs build --strict` exit 0
  - `poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q` -> `31 passed, 8 warnings`
  - tiny pipeline smoke -> `2 passed in 5.89s`
- 後續：
  - 下一份 architecture 文件建議清 `agent.md`，因為它會影響未來 tool-call validation 與 Application Service 目標。

### 2026-05-02 Product delivery UI / agent / validation slice

- 做了什麼：
  - 將 AI Assistant header、status chips、available next steps、persona/runtime/mode labels、
    empty state、message bubbles 和 composer 改成使用者導向語言。
  - 第一層 UI 不再顯示 raw command names；advanced command diagnostics 留在 tooltip / details。
  - 修正 user bubble right margin / word wrap，避免最後一個字被截掉。
  - 新增 `XBrainLab/ui/product_language.py`，集中 stage / command / status 的產品文字。
  - 新增 UI command adapter，讓 dataset import、reset、preprocess、epoching、training
    start / stop 優先走 `ApplicationService.execute()`，mock / legacy path 保留 controller fallback。
  - agent mapped workflow tools 優先直接執行 ApplicationService command，回傳 structured
    `CommandResult` payload；`load_data` / `set_montage` / `switch_panel` 仍保留 legacy / UI request path。
  - 新增 product UI integration smoke，覆蓋 assistant click-through layout 和 synthetic EEG
    button-driven pipeline walkthrough。
  - 更新 current / planning / architecture / validation 文件，誠實標出剩餘 release risk。
- 證據：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q` -> `78 passed`
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_panel_normalize.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/test_sidebars_and_components.py -q` -> `74 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q` -> `11 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q` -> `60 passed`
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q` -> `2 passed`
  - combined UI product gate -> `62 passed`
  - combined agent / backend gate -> `95 passed`
  - IO integration -> `31 passed, 8 warnings`
  - selected pipeline smoke -> `2 passed`
  - launcher startup smoke printed `MainWindow initialized` before expected GUI timeout.
- commits:
  - `941efaf ui: polish assistant product language`
  - `e52687a backend: align ui command adapter slice`
  - `34816c7 agent: execute mapped tools via command results`
  - `5ede90e validation: add product walkthrough smoke`
- push status:
  - each `git push origin HEAD` failed because GitHub credentials were unavailable in this environment:
    `fatal: could not read Username for 'https://github.com': No such device or address`
- 後續：
  - 完成剩餘 service-first UI action migration：label import、smart parse、channel selection、
    split / model / training setting dialogs、evaluation / visualization query actions。
  - 做 Windows Desktop launcher 人工 click-through 與 true local model UI walkthrough。
  - 將 `evaluate` / `visualize` / `saliency` / `new_session` 從 future placeholder 推進成真 command。

### 2026-05-02 Assistant runtime consent / query commands / thesis protocol closure

- 做了什麼：
  - ChatPanel 主視覺改成使用者語言：自然語言 workflow state、next step、Options；persona、
    runtime、single/auto mode 不再佔主視覺。
  - 新增 local runtime first-run consent dialog，顯示 resource notice、estimated download、
    current/projected cache、provider/license/VRAM estimate，提供 Enable / Download /
    Use existing cache / Later / Disable。
  - `ApplicationService` 實作 `evaluate`、`visualize`、`saliency`、`new_session` typed result；
    `BackendFacade.get_latest_results()` 保留舊 caller shape。
  - UI channel selection、split/model/training dialog submit、evaluation/visualization query、
    saliency setup/query 走 service command adapter，mock / legacy path 保留 fallback。
  - 新增 split audit helper、split artifact schema、validator script 和 thesis protocol 文件。
  - deterministic tool-call eval 更新 query-command 語意並刷新 `artifacts/agent_evals/latest.json`。
- 證據：
  - `poetry run ruff check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
  - `poetry run ruff format --check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
  - `git diff --check` -> pass
  - `poetry run mkdocs build --strict` -> pass
  - UI product gate -> `62 passed`
  - backend / split audit / config gate -> `41 passed`
  - agent / facade / backend workflow gate -> `130 passed`
  - deterministic eval refresh -> `21 / 21` cases passed
  - full test gate -> `4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`
- 後續：
  - 真 Windows launcher click-through 和 true local model UI walkthrough 尚未跑。
  - label import、smart parse、montage confirmation 仍要做 typed/service 收斂。
  - thesis protocol 已建立；external dataset runner、repeat runs、baselines、statistics 尚未完成。

### 2026-05-03 Backend Workflow Contract v2 first slice

- 做了什麼：
  - 新增 `ClearDatasetsCommand`、`ClearTrainingHistoryCommand`、`ResetPreprocessCommand`，
    補齊 command export、service handlers、capability policy 和 `BackendFacade` compatibility wrappers。
  - `GenerateDatasetCommand` 接上 split audit；empty train/validation/test 或 leakage 會回
    structured `DATA_MISMATCH` failure，不再悄悄當成功。
  - split audit failure 會 rollback dataset / generator / trainer state，避免 failure 後仍可 train。
  - `evaluate`、`visualize`、`saliency` policy 不再在 empty state 無條件可用；blocked command
    仍透過 `CommandResult` envelope 回傳。
  - `saliency` diagnostics 分出 `action=configure/query`；configure 可先保存參數，
    saliency view/readiness 仍以 finished evaluation + configured params 為準。
- 證據：
  - `poetry run ruff check XBrainLab tests` -> pass
  - `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run pytest tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/integration/ui/test_product_walkthrough.py tests/integration/pipeline/test_public_cross_source_training_smoke.py` -> `32 passed, 3 warnings`
  - `poetry run pytest tests/unit/backend/application tests/integration/backend tests/integration/pipeline` -> `95 passed, 4 warnings`
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
- 後續：
  - 這只是 Backend Workflow Contract v2 + Evidence-Ready Pipeline 的第一個可交付切片，
    不是終局。
  - UI service-first migration 還有 remaining UI bypass，需要逐步接到 command layer。
  - thesis evidence 還需要 external dataset runner、repeat runs、baseline/statistics 和 artifact
    emission policy。

### 2026-05-03 Assistant UI single-toolbar correction

- 做了什麼：
  - 移除 chat panel 內可見 `Conversation` header、composer 底下狀態列、第二個 options menu
    和未完成的 Assistant mode / Step behavior controls。
  - dock title bar 成為唯一第一層功能列：`XBrainLab`、retry icon、new conversation、
    settings menu、float/dock；`Clear conversation` 收進 settings menu。
  - `AgentManager` 攔截 tool/debug sender 或 internal tool syntax，visible transcript 不再顯示
    `Tool list_files completed...`、schema error、`ApplicationService` / `BackendFacade`。
  - short bubble minimum width 降低，避免 `hello` 形成過大的框，同時保留窄 dock 可讀性。
- 證據：
  - `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py` -> pass
  - `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py -q` -> `50 passed`
  - combined assistant UI + backend workflow contract gate -> `80 passed, 3 warnings`
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`

### 2026-05-04 Goal 1 Data Interpretation backend command baseline

- 做了什麼：
  - 依 `artifacts/goal/goal-1-product-autopilot.md` 啟動 Goal 1 第一個可驗證 slice。
  - 先讀 `AGENTS.md`、`.agents/README.md`、autopilot / backend runbook、
    `docs/current.md`、`docs/planning/roadmap.md`、`docs/planning/now.md`、target /
    architecture / validation 文件，確認 Data Interpretation 仍是主要未實作缺口。
  - 新增 `XBrainLab/backend/application/data_interpretation.py`，定義 `ScanResult`、
    `InterpretationCandidate`、`InterpretationPreview`、`ValidationDecision`、
    `AppliedInterpretation`、`ImportRecipe`。
  - 新增 `scan_source`、`preview_interpretation`、`validate_interpretation`、
    `apply_interpretation`、`save_interpretation_recipe`、`reload_interpretation_recipe`
    command。
  - `ApplicationStateSnapshot` 新增 `interpretation` section，`CommandCapability` 新增
    `can_auto_execute`、`requires_confirmation`、`decision_boundary`、
    `continue_allowed_after_success`、`retry_limit`、`stop_after_success`、
    `blocks_downstream_until_confirmed`。
  - recipe reload 走重新 scan / preview / validate，不會自動 apply。
  - deterministic eval lightweight state builder 補 `InterpretationStateSnapshot`，避免 scorer
    使用舊 state contract。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
    -> `28 passed`
  - `poetry run ruff check XBrainLab/backend/application tests/unit/backend/application/test_application_service.py scripts/agent/evals/run_tool_call_eval.py`
    -> `PASS`
  - `poetry run basedpyright XBrainLab/backend/application scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_application_service.py`
    -> `0 errors, 0 warnings, 0 notes`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/integration/backend/test_application_service_workflow.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `92 passed`
  - `poetry run mkdocs build --strict` -> pass
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals_tmp_goal1`
    -> temporary artifact `21 / 21` after saliency query policy alignment；temporary directory removed。
  - `git diff --check` -> pass
- 後續：
  - UI import entry 尚未改成 scan -> preview -> validate -> confirm -> apply -> recipe。
  - agent tool taxonomy 尚未遷移到 Data Interpretation tools。
  - headless / MCP-ready adapters 尚未暴露新 command taxonomy。
  - non-mocked synthetic workflow 目前只到 backend command baseline，尚未走 preprocess -> epoch -> dataset。

### 2026-05-04 Goal 1 Data Interpretation agent tool surface

- 做了什麼：
  - 新增 Data Interpretation agent tool definitions、mock tools、real tools，並註冊到
    `get_all_tools(mode="mock" / "real")`。
  - `application_surface.py` 將 `scan_source`、`preview_interpretation`、
    `validate_interpretation`、`apply_interpretation`、`save_interpretation_recipe`、
    `reload_interpretation_recipe` 映射到 ApplicationService commands。
  - `ToolAvailability` payload 補齊 backend autonomy policy 欄位，讓 agent history /
    diagnostics 能看到 `can_auto_execute`、`requires_confirmation`、`decision_boundary`、
    retry / stop / downstream confirmation boundary。
  - `LLMController` 新增 dynamic confirmation boundary：backend policy 若要求 confirmation，
    即使 static tool 不標記 dangerous，也會暫停等 UI confirmation；確認後
    `apply_interpretation` 會帶 `confirmed=True`。
  - `BackendFacade(study)` 會重用同一個 `ApplicationService`，避免 Data Interpretation scan /
    candidate / validation state 在連續 agent tool calls 間遺失。
  - `PathExistsValidator` 補 `scan_source.source_path` 和
    `reload_interpretation_recipe.recipe_path`。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/agent/test_controller.py -q`
    -> `219 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/agent/test_verification_layer.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `286 passed`
  - `poetry run ruff check <slice files>` -> pass
  - `poetry run basedpyright <slice source files>` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals_tmp_goal1_agent_surface`
    -> pass；temporary artifact directory removed。
  - `git diff --check` -> pass
- 後續：
  - UI import entry 尚未重做。
  - headless / MCP adapter 尚未暴露新 command taxonomy。
  - deterministic / local LLM tool-call cases 尚未改以 Data Interpretation 作為主要資料入口。
  - 尚未有 source -> scan -> preview -> validate -> apply -> recipe -> preprocess -> epoch ->
    dataset 的 non-mocked synthetic workflow evidence。

### 2026-05-04 Goal 1 Dataset panel Data Interpretation entry

- 做了什麼：
  - Dataset sidebar 主按鈕從 `Import Data` 改為 `Interpret Data Source`。
  - `DatasetActionHandler.import_data()` 改走 `ScanSourceCommand` ->
    `PreviewInterpretationCommand` -> `ValidateInterpretationCommand` ->
    `ApplyInterpretationCommand`。
  - 新增 `DataInterpretationPreviewDialog`，顯示 source、validation decision、metadata preview、
    warnings、confirmation items 和 blocked reasons；`blocked` decision 不能按 apply。
  - `needs_confirmation` decision 只有在 preview dialog 接受後才對 apply command 帶
    `confirmed=True`。
  - 多檔跨不同資料夾選取時，不用 filesystem common root 做 scan，避免意外掃描過大的上層路徑。
  - product walkthrough 的 synthetic `.fif` import 已改成通過新 preview / apply path。
- 證據：
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q`
    -> `50 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/dataset tests/unit/ui/dialogs/dataset tests/unit/ui/test_ui_misc.py tests/unit/ui/test_application_capabilities.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `166 passed`
  - `poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
    -> `76 passed`
  - `poetry run ruff check <ui data interpretation slice files>` -> pass
  - `poetry run basedpyright <ui data interpretation source files>` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
  - `git diff --check` -> pass
- 後續：
  - recipe save UI 尚未接上。
  - label import 仍是舊入口，尚未納入 Data Interpretation preview / recipe。
  - headless / MCP adapter 尚未暴露新 command taxonomy。
  - 尚未有 source -> scan -> preview -> validate -> apply -> recipe -> preprocess -> epoch ->
    dataset 的 non-mocked synthetic workflow evidence。

### 2026-05-04 12:08 ChatPanel Data Interpretation tool-chain handoff

- 做了什麼：
  - 新增 `scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py`，用真 MainWindow /
    ChatPanel / AgentManager / LLMController / AgentWorker / LLMEngine local backend，在
    `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 下建立 synthetic FIF，經可見 composer
    要求 local model 依序執行 Data Interpretation `scan_source`、`preview_interpretation`、
    `validate_interpretation`。
  - 新增 `tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`。
  - 首次真跑揭露 blocker：`scan_source` 成功後，`preview_interpretation` 仍失敗為
    `Scan a data source before previewing interpretation.`；final state 顯示 scan state 存在，
    因此不是 `ApplicationService` lifecycle 遺失，而是 local model 帶了 generated
    placeholder id，覆蓋 backend latest-state fallback。
  - 修 `XBrainLab/llm/agent/tool_call_normalizer.py`：`preview_interpretation` 只保留
    `scan-<n>`，`validate_interpretation` / `apply_interpretation` 只保留 `candidate-<n>`；
    `latest_scan_id` / current-style placeholder 會被移除。
  - 更新 current / now / validation，並新增 continuation prompt：
    `artifacts/goal/continuation-2026-05-04-product-completion.md`。
- artifact：
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.md`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.json`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-ready.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-1.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-2.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-3.png`
- 驗證：
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py -q`
    -> `30 passed`
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
    -> pass
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`
  - `timeout 620s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool-chain --timeout-seconds 580`
    -> passed；primary `microsoft/Phi-4-mini-instruct`、`gpu-ready`、cache `15.34 GB`、三個
    expected tools 全部 `ok`。
- 不能宣稱：
  - 這只支撐短鏈 Data Interpretation tool-command workflow。
  - 還不能宣稱 confirm/apply、preprocess、epoch、dataset、training 長鏈 autonomous workflow。
  - 還不能宣稱 Windows Desktop launcher 真人 click-through、MCP Inspector GUI 或完整 import
    wizard / label editor 完成。

### 2026-05-04 12:20 ChatPanel import-to-dataset pipeline chain

- 做了什麼：
  - 新增 `scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py`，用真 MainWindow /
    ChatPanel / local model 走 `scan_source` -> `preview_interpretation` ->
    `validate_interpretation` -> `apply_interpretation` -> `apply_standard_preprocess` ->
    `epoch_data` -> `generate_dataset`。
  - script 會觀察 `Confirm Action` QMessageBox 並按 Yes，artifact 會記錄 confirmation dialog。
  - `apply_standard_preprocess` 現在由 `application_surface.py` 直接 route 到
    `PreprocessCommand(operation=STANDARD)`，避免 real-tool legacy string fallback。
  - 首次真跑在 `generate_dataset` 被 split audit 擋下，原因是 prompt 只形成 `left` 單一 event
    和 3 epochs；修正 `tool_call_normalizer`，讓 `events left and right` 可抽出多個 event ids。
  - 新增 `tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py`。
- artifact：
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.md`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.json`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-ready.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-1.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-2.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-3.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-4.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-5.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-6.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-7.png`
- 驗證：
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py::test_application_tool_command_routes_standard_preprocess tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py -q`
    -> `32 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `timeout 840s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-pipeline-chain --timeout-seconds 800`
    -> passed；七個 expected tools 全部 `ok`，confirmation dialogs observed `1`，epoch count `6`，
    dataset available `True`。
- 不能宣稱：
  - 這支撐 ChatPanel 到 dataset ready，不支撐 model / training settings / train / evaluation /
    saliency 長鏈。
  - 仍未完成人工 Windows Desktop launcher click-through、MCP Inspector GUI、完整 import wizard
    label/anchor editor。

### 2026-05-04 12:23 Usage-refresh handoff

- 因用量即將刷新，新增交接紀錄：
  - `artifacts/goal/handoff-2026-05-04-usage-refresh.md`
  - 並在 `artifacts/goal/continuation-2026-05-04-product-completion.md` 加上索引。
- 交接紀錄保存：
  - 最新 commit：`0cb480e assistant: capture import to dataset chain`。
  - expected dirty worktree：只應剩 `.vscode/settings.json` 和 root `settings.json`，兩者都不可碰。
  - 已驗證的真 local ChatPanel import-to-dataset artifact 與 validation command。
  - 下一輪最高優先級：補 evaluation / visualization / saliency 的 agent tool exposure，然後做
    dataset -> train/evaluate/saliency readiness 的 ChatPanel local-model walkthrough。
- Goal 仍不可標 complete。

### 2026-05-04 12:37 Agent analysis-tool exposure

- 做了什麼：
  - 新增 `evaluate` / `visualize` / `saliency` 的 definitions、mock tools、real tools。
  - `get_all_tools("mock")` / `get_all_tools("real")` 現在會註冊三個 analysis-readiness tools。
  - `application_surface.py` 直接將三個 tool route 到 `EvaluateCommand`、
    `VisualizeCommand`、`SaliencyCommand`，回 typed `ToolCommandResult`。
  - `CommandParser` 支援三個 bare tool names，`infer_user_intent()` 補上 evaluation intent。
  - `PipelineStage.TRAINED` prompt stage 現在明確列出 analysis tools。
- 驗證：
  - 先寫測試並確認 initial failure：缺 `analysis_def` / `analysis_mock`。
  - 目標測試：`293 passed`。
  - broader agent/tools regression：`516 passed`。
  - deterministic eval refresh：`artifacts/agent_evals/latest.json` / `.md`，`100 / 100` pass。
  - primary affected-case local smoke：`artifacts/agent_evals/local_primary_analysis_tools/`，
    `5 / 5` pass，`gpu-ready`，no download。
  - fallback affected-case local smoke：`artifacts/agent_evals/local_fallback_analysis_tools/`，
    `5 / 5` pass，`gpu-ready`，no download。
  - targeted `ruff` -> pass；`poetry run ruff check .` -> pass；
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`；
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`；
    `poetry run mkdocs build --strict` -> pass；`git diff --check` -> pass。
- 不能宣稱：
  - 這只解除 analysis command 的 agent exposure gap。
  - 還沒有真 ChatPanel dataset -> model / training settings -> train -> evaluation /
    visualization / saliency readiness 長鏈 walkthrough。

### 2026-05-04 12:51 ChatPanel training-readiness boundary

- 做了什麼：
  - 新增 `scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py`。
  - script 先用 ApplicationService 準備 synthetic dataset-ready state，避免重跑已驗證的
    import-to-dataset UI chain。
  - 真 MainWindow / ChatPanel / local model visible turns：
    `set_model` -> `configure_training` -> `start_training` confirmation observed/rejected ->
    `visualize` -> `saliency` -> `evaluate` blocked reason。
  - 新增 `tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py`。
- artifact：
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.md`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.json`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-ready.png`
  - turn screenshots 1-6。
- 驗證：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py -q`
    -> `4 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `timeout 900s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-readiness --timeout-seconds 840`
    -> passed；primary `microsoft/Phi-4-mini-instruct`、`gpu-ready`、cache `15.34 GB`、
    confirmation dialogs observed `1` 且 `approved=False`。
  - visible assistant text clean check -> pass。
- 不能宣稱：
  - 這支撐 training confirmation boundary 和 analysis-readiness tool path。
  - 還不支撐 actual training completion、evaluation metrics 或 saliency render。

### 2026-05-04 12:57 Usage-refresh handoff refresh

- 因使用量即將刷新，刷新交接紀錄：
  - `artifacts/goal/handoff-2026-05-04-usage-refresh.md`
- 交接已更新到最新 commit：
  - `a228a9d assistant: capture training readiness boundary`
  - `84d9c66 agent: expose analysis tools`
- 交接紀錄明確保存：
  - expected dirty worktree 只應剩 `.vscode/settings.json` 和 root `settings.json`，兩者不可碰。
  - 最新可驗證 evidence 是 true local ChatPanel training-readiness boundary，不是 actual training
    completion。
  - 下一手優先處理 `configure_training` tool schema / `output_dir` path，然後做 controlled tiny
    training completion -> evaluation / visualization / saliency evidence。
- Goal 仍不可標 complete。

### 2026-05-04 13:04 Configure-training output directory surface

- 做了什麼：
  - `BaseConfigureTrainingTool` schema 新增 optional `output_dir`，讓 ChatPanel / local model 可以
    指定 controlled tiny training artifact 的輸出位置。
  - `application_surface.py` 的 `configure_training` mapping 現在會把 `output_dir` 傳入
    `ConfigureTrainingCommand`，不再落回 `./output`。
  - legacy `RealConfigureTrainingTool` 也會把 `output_dir` 傳給 `BackendFacade.configure_training`。
  - `tests/unit/llm/tools/test_definitions.py` 補 helper，讓直接 targeted basedpyright 檢查時不再
    因 property getter optional-call 報錯。
- TDD failure：
  - schema 缺 `output_dir`。
  - ApplicationService-backed tool result 的 training option 仍是 `./output`。
  - real tool wrapper 沒傳 `output_dir`。
- 驗證：
  - initial focused tests -> `3 failed`，原因符合預期。
  - focused tests after fix -> `3 passed`。
  - related regression：
    `poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py tests/unit/llm/agent/test_verification_layer.py -q`
    -> `311 passed`。
  - targeted `ruff` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - deterministic tool-call eval refresh：
    `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
    -> `100 / 100` pass。
- 不能宣稱：
  - 這只解除 controlled training artifact 的 output path gap。
  - 還沒有 actual ChatPanel training completion、evaluation metrics、visualization render 或
    saliency render evidence。

### 2026-05-04 13:30 ChatPanel controlled tiny training completion

- 做了什麼：
  - 新增 `scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`。
  - 使用 training-safe synthetic FIF（14s raw、1.5s epochs）避免 EEGNet minimum epoch duration
    guardrail。
  - 真 MainWindow / ChatPanel / local primary model visible turns：
    `set_model` -> `configure_training` with temp `output_dir` -> observed/approved
    `start_training` confirmation -> wait for 1 epoch CPU training completion -> `evaluate` ->
    `saliency` configure -> `visualize` -> saliency readiness query。
  - 新增 `tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py`。
  - 修正產品缺口：
    - saliency command 將 flat `method` / `params` normalize 成 backend-required
      `SmoothGrad` / `SmoothGrad_Squared` / `VarGrad` params。
    - `infer_user_intent()` 認得 `visualization` / `visualisation`。
    - saliency readiness query 會清掉上一輪 stale saliency config params。
    - evaluation metrics bar chart `tight_layout` failure 降級為 warning。
    - missing `torchinfo` model summary 回可理解 unavailable message，不再打 traceback。
- artifact：
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.md`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.json`
  - ready / trained / turn 1-7 screenshots。
- 驗證：
  - true local ChatPanel run：
    `timeout 1200s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-completion --timeout-seconds 1080`
    -> passed；primary `microsoft/Phi-4-mini-instruct`、`gpu-ready`、cache `15.34 GB`、no download。
  - final state：finished runs `1`、evaluation metrics available `True`、saliency configured /
    available `True`、ChatPanel idle。
  - targeted regression：`48 passed`。
  - UI fallback tests：`3 passed`。
  - broader agent suite：`235 passed`。
  - targeted `ruff` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - deterministic tool-call eval -> `100 / 100` pass。
- 不能宣稱：
  - 這支撐 controlled tiny training completion 和 analysis readiness summary。
  - 還不是完整 saliency / visualization canvas render、真人 Windows launcher click-through、
    MCP Inspector GUI、mature import wizard label editor 或 external thesis experiment package。

### 2026-05-04 13:52 Usage-refresh handoff after training completion

- 因使用量即將刷新，刷新交接紀錄：
  - `artifacts/goal/handoff-2026-05-04-usage-refresh.md`
  - `artifacts/goal/continuation-2026-05-04-product-completion.md`
- 交接已更新到最新 product commit：
  - `f9f0956 assistant: capture training completion walkthrough`
  - `7936328 agent: preserve training output dir`
- 交接紀錄明確保存：
  - expected dirty worktree 只應剩 `.vscode/settings.json` 和 root `settings.json`，兩者不可碰。
  - controlled tiny ChatPanel training completion 已完成，不要下一輪重做。
  - 下一手優先處理 visualization / saliency canvas render UI evidence；不能把 readiness summary
    包裝成 render。
- Goal 仍不可標 complete。

### 2026-05-04 17:15 VisualizationPanel Matplotlib render evidence

- 做了什麼：
  - 新增 `scripts/dev/capture_visualization_render_walkthrough.py`。
  - script 使用 ApplicationService 準備 synthetic source -> Data Interpretation apply ->
    preprocess -> epoch -> dataset -> configure EEGNet -> configure saliency -> apply montage ->
    1 epoch CPU train。
  - 開啟真 MainWindow / VisualizationPanel，依序 render `Saliency Map`、`Spectrogram`、
    `Topographic Map` 三個 tab，並保存 screenshots / JSON / Markdown。
  - 新增 `tests/unit/scripts/test_capture_visualization_render_walkthrough.py`，要求三個 render tab
    都有 screenshot、visible canvas、axes 和 rendered image artist，避免只記錄 placeholder。
  - capture script 會 auto-dismiss offscreen training completion dialog，避免 modal 把 render
    capture 卡住。
- artifact：
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.md`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.json`
  - ready / saliency map / spectrogram / topographic map screenshots。
- 驗證：
  - initial TDD failure：script module 不存在，pytest collection failed。
  - script tests：`poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
    -> `6 passed`。
  - existing visualization UI tests：
    `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization.py -q`
    -> `20 passed`。
  - true UI render run：
    `timeout 600s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_visualization_render_walkthrough.py --output-dir artifacts/ui/visualization-render --timeout-seconds 540`
    -> passed。
  - final evidence：finished runs `1`、metrics available `True`、saliency available `True`、
    montage available `True`；三個 tab 無 error label 且有 rendered image artist。
  - targeted `ruff` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐 MainWindow VisualizationPanel post-training Matplotlib saliency render。
  - 還不是 3D / PyVista render、ChatPanel UI-routing render、真人 Windows launcher click-through、
    MCP Inspector GUI、mature import wizard label editor 或 external thesis experiment package。

### 2026-05-04 17:23 3D headless blocked UX guard

- 做了什麼：
  - 真 prototype 在 `QT_QPA_PLATFORM=offscreen` / `PYVISTA_OFF_SCREEN=true` 切到 `3D Plot` 時，
    PyVista / X11 直接 `BadWindow` crash。
  - `Saliency3DPlotWidget.update_plot()` 新增 interactive OpenGL runtime preflight；offscreen /
    minimal Qt platform、`PYVISTA_OFF_SCREEN=true` 或 Linux 無 `DISPLAY` 時，不建立
    `pyvistaqt.QtInteractor`，改在 3D tab 顯示人話 blocked reason。
  - `scripts/dev/capture_visualization_render_walkthrough.py` 現在也 capture `3D Plot` blocked
    screenshot 和 `plotter_created=False` evidence。
- artifact：
  - `artifacts/ui/visualization-render/visualization-render-3d-blocked.png`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.md`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.json`
- 驗證：
  - initial TDD failure：`test_update_plot_blocks_offscreen_before_qtinteractor` 顯示 current code
    仍呼叫 `QtInteractor`。
  - focused 3D guard：
    `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
    -> `1 passed`。
  - visualization artifact tests：
    `poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
    -> `8 passed`。
  - true UI render / blocked run：
    `timeout 600s env QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python scripts/dev/capture_visualization_render_walkthrough.py --output-dir artifacts/ui/visualization-render --timeout-seconds 540`
    -> passed；2D tabs render，3D blocked reason visible，`plotter_created=False`。
- 不能宣稱：
  - 這支撐 headless/offscreen 3D tab blocked UX，不是 interactive desktop 3D render。
  - Windows / WSLg interactive 3D click-through 仍未驗證。

### 2026-05-04 18:41 Usage refresh handoff refresh

- 因使用量即將刷新，交接紀錄已更新到最新本地 commit：
  - `15002a1 ui: show label import target context`
  - `7d0f92c ui: show matched eeg for label carriers`
  - `4c2ad99 backend: map reviewed sequence labels by file stem`
  - `c9c79e2 backend: map reviewed timestamp labels by file stem`
  - `a26942a backend: propagate import review state`
- 已刷新：
  - `artifacts/goal/handoff-2026-05-04-usage-refresh.md`
  - `artifacts/goal/continuation-2026-05-04-product-completion.md`
- 下一輪建議直接從 MCP Inspector / release config hardening 開始；不要重做已完成的 state snapshot
  propagation、多檔安全 label mapping、matched EEG UI 或 post-load label target context。
- 預期未提交的 dirty worktree 只應剩 `.vscode/settings.json` 和 root `settings.json`，兩者不可碰。
- Goal 仍不可標 complete。

### 2026-05-04 19:18 MCP Inspector-style release config baseline

- 做了什麼：
  - 新增 `scripts/dev/run_mcp_server_for_client.sh`，讓外部 MCP client / Inspector 啟動 prepared
    XBrainLab runtime wrapper，而不是在 client side 安裝 EEG / PyQt / PyTorch stack。
  - 新增 `scripts/dev/write_mcp_client_config.py`，可重生並驗證
    `artifacts/mcp/xbrainlab-mcp.json` / `.md`。
  - `xbrainlab-mcp.json` 使用 Inspector 支援的 `mcpServers` / `type: "stdio"` config：
    `default-server` 走 `bash <wrapper>`，`xbrainlab-windows-wsl` 走
    `wsl.exe bash <wrapper>`。
  - 新增 unit / integration tests；integration test 會讀 committed config，再用 config command
    啟動 prepared runtime wrapper 重跑 MCP stdio walkthrough。
- TDD：
  - 初跑 `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py -q`
    因 `scripts.dev.write_mcp_client_config` 不存在而 collection failed。
- 驗證：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py -q`
    -> `5 passed`。
  - `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir /tmp/xbrainlab-mcp-config-walkthrough --server-command bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
    -> wrote walkthrough artifact in `/tmp/xbrainlab-mcp-config-walkthrough`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py -q`
    -> `6 passed`。
  - `poetry run ruff check scripts/dev/write_mcp_client_config.py tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py`
    -> pass。
  - `poetry run ruff format --check scripts/dev/write_mcp_client_config.py tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py`
    -> pass after formatting `tests/unit/scripts/test_write_mcp_client_config.py`。
  - `poetry run basedpyright scripts/dev/write_mcp_client_config.py tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/unit/mcp tests/integration/mcp -q`
    -> `13 passed`。
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐 MCP Inspector-style `mcp.json` release config baseline 和 prepared-runtime launch path。
  - 還不是 Inspector GUI 人工 click-through、HTTP transport、Windows Desktop 真人啟動或
    long-running training through MCP。
  - Goal 仍不可標 complete。

### 2026-05-04 19:31 Data Interpretation manual generic label target mapping

- 做了什麼：
  - `label_carrier_choices` 新增 `target_file`，backend 會保存到
    `label_carrier_plan[*].selected_target_file`。
  - Data Interpretation wizard 的 editable `Matched EEG` 欄位現在會在使用者把 `Needs review`
    改成 EEG filename/path 時，把 target mapping 帶進 choices。
  - `apply_interpretation` 現在可將 generic `events.tsv` 或 `labels.mat` 只套用到使用者指定的
    loaded EEG file；未指定 target 時，原本 ambiguous skip behavior 保持不變。
  - UI replay 改成兩個 synthetic FIF + generic `events.tsv`，artifact 顯示
    `events.tsv -> sub-01_task-mi_run-2_raw.fif`，且 label_apply 只套用到第二個 EEG。
- TDD：
  - UI 初跑失敗：`label_carrier_choices` 沒有 `target_file`。
  - backend 初跑失敗：manual target 的 generic timestamp / sequence carriers 仍
    `label_apply.status=skipped`。
- artifact：
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
- 驗證：
  - focused UI manual target mapping -> pass after implementation。
  - focused backend manual timestamp / sequence mapping -> `2 passed`。
  - dialog suite：
    `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `7 passed`。
  - focused backend positive + negative：
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
    -> `4 passed`。
  - backend / automation / agent surface regression：
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
    -> `67 passed`。
  - dialog + DatasetActionHandler regression：
    `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `54 passed`。
  - true UI replay:
    `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`。
  - targeted `ruff`, `ruff format --check`, production `basedpyright` clean。
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐 generic label carrier manual target mapping 的第一個 embedded wizard path。
  - 還不是 raw-event-anchor-specific GDF/MAT alignment、all-format manual compatibility matrix、
    post-load label import full editor 或真人 click-through。
  - Goal 仍不可標 complete。

### 2026-05-04 19:39 Data Interpretation label target selector UX

- 做了什麼：
  - Ambiguous label carrier rows now render a `QComboBox` in the `Matched EEG` column.
  - Selector options are `Needs review` plus scanned EEG filenames.
  - `get_result()` reads the selector value and still returns `target_file` in
    `label_carrier_choices`.
  - replay `tree_rows()` now reads cell widgets, so UI artifact records the visible selected
    target rather than stale item text.
- TDD：
  - 初跑 focused UI test failed，因 `itemWidget(carrier_item, 1)` 是 `None`。
- 驗證：
  - focused selector test -> `1 passed`。
  - dialog suite -> `7 passed`。
  - true UI replay -> exit `0`。
  - dialog + DatasetActionHandler regression -> `54 passed`。
  - backend manual target mapping focused tests -> `2 passed`。
  - targeted `ruff` / `ruff format --check` / production `basedpyright` clean。
- 不能宣稱：
  - 這支撐 generic carrier target mapping 的使用者操作不再依賴手打 filename。
  - 還不是 post-load label import full editor、all-format manual compatibility matrix 或真人
    click-through。
  - Goal 仍不可標 complete。

### 2026-05-04 19:48 MCP Inspector CLI smoke and WSL poetry fallback

- 做了什麼：
  - 用官方 Inspector CLI 跑 committed `xbrainlab-windows-wsl` config 時，初次失敗：
    `Failed to connect to MCP server: MCP error -32000: Connection closed`。
  - direct WSL smoke 找到 root cause：Windows-side `wsl.exe` 啟動的是非 login shell，
    `poetry` 不在 PATH。
  - `scripts/dev/run_mcp_server_for_client.sh` 新增 `POETRY_BIN` / `command -v poetry` /
    `$HOME/.local/bin/poetry` fallback。
  - 保存 official Inspector CLI `tools/list` artifact：
    `artifacts/mcp/inspector-cli-tools-list.json` / `.md`。
- 驗證：
  - `/mnt/c/Windows/System32/wsl.exe bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
    + MCP initialize request -> valid initialize JSON。
  - `timeout 180s '/mnt/c/Program Files/nodejs/npx' -y @modelcontextprotocol/inspector --cli --config artifacts/mcp/xbrainlab-mcp.json --server xbrainlab-windows-wsl --method tools/list`
    -> exit `0`。
  - Inspector CLI artifact lists `28` tools and includes `scan_source` / `apply_interpretation`。
- 不能宣稱：
  - 這支撐 official Inspector CLI with Windows WSL config。
  - 仍不是 Inspector GUI 人工 click-through、HTTP transport、long-running MCP training 或完整
    product completion。

### 2026-05-04 Usage refresh handoff

- 做了什麼：
  - 刷新 `artifacts/goal/handoff-2026-05-04-usage-refresh.md`，以最新 commit
    `3ffa73d` 作為接續基準。
  - handoff 現在列出 MCP client config、generic label carrier manual mapping、label
    target selector UX、Inspector CLI smoke 的 commit、artifact、驗證和 claim boundary。
  - 下一步建議 slice 改為 Data Interpretation format capability matrix，避免下一個 runner
    重做已完成的 MCP CLI / label target work。
- 不能宣稱：
  - 這只是交接記錄，不是產品完成。
  - 仍不能宣稱 Inspector GUI、Windows launcher click-through、interactive desktop 3D、
    raw-event-anchor label alignment、external thesis experiment 或完整 product completion。

### 2026-05-04 Data Interpretation format capability matrix artifact

- 做了什麼：
  - 新增 `scripts/dev/report_data_interpretation_format_matrix.py`，用 live
    `ApplicationService` 的 `scan_source -> preview_interpretation -> validate_interpretation`
    command path 產生 format capability matrix。
  - 產出 `artifacts/data_interpretation/format-capability-matrix.json` / `.md`。
  - matrix 覆蓋 GDF、EDF、BDF、EEGLAB、BrainVision VHDR / VMRK、MNE FIF、MAT、CSV、TSV、
    BIDS events、TXT、XDF / LSL，並保留 supported / needs_review / context / blocked 與
    safe / needs_confirmation / blocked validation boundary。
- TDD：
  - 初跑 focused test failed，因 reporter module 尚不存在。
  - 後續 CLI JSON test failed，因 `Study initialized` log 污染 stdout；reporter 已把
    ApplicationService info logs 壓到 warning 以上。
- 驗證：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py -q`
    -> `3 passed`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
    -> `4 passed`。
  - targeted `ruff check` / `ruff format --check` -> pass。
  - `poetry run basedpyright scripts/dev/report_data_interpretation_format_matrix.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run python scripts/dev/report_data_interpretation_format_matrix.py --write-artifacts`
    -> wrote JSON / Markdown artifacts。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐 generated capability-boundary matrix。
  - 仍不是 XDF / LSL stream parser、raw-event-anchor-specific MAT/GDF alignment、real-data manual
    certification 或完整 product completion。

### 2026-05-04 Data Interpretation reviewed MAT sample-anchor apply

- 做了什麼：
  - `load_label_file()` 現在可用 reviewed MAT `label_field` + `anchor` 產生 MNE-style event
    array：`[sample_index, 0, class_label]`。
  - `apply_interpretation` 對 reviewed MAT plan 新增 `anchored` mode：需要 selected label、
    selected anchor、`time_model=sample_index`、`granularity=trial` 和 confirmed class map。
  - anchored mode 走 `apply_labels_batch`，並保存 `label_import:anchored:<n>` recipe trace。
- TDD：
  - focused label loader 初跑只回 plain labels，未回 event rows。
  - focused ApplicationService 初跑 `label_apply.status=skipped`。
- 驗證：
  - focused MAT anchor tests -> `2 passed`。
  - label loader + label apply regression subset -> `35 passed`。
  - full `tests/unit/backend/application/test_application_service.py` -> `43 passed`。
  - targeted `ruff check` / `ruff format --check` clean。
  - production `basedpyright` for touched backend files -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐 reviewed MAT sample-index anchor 的窄版 apply path。
  - 仍不是任意 raw trigger selection、non-sample timestamp conversion、complex MAT/GDF anchor
    reconciliation、XDF parser 或完整 product completion。

### 2026-05-04 PyVistaQt runtime probe

- 做了什麼：
  - 新增 `scripts/dev/probe_pyvistaqt_runtime.py`，用 child process 嘗試建立最小
    `pyvistaqt.QtInteractor` + sphere render。
  - 產出 `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.json` / `.md`。
- 結果：
  - 目前 runner session 有 `DISPLAY=:0` 和 `WAYLAND_DISPLAY=wayland-0`。
  - probe status 是 `blocked`。
  - stderr 是 X `BadWindow (invalid Window parameter)`；screenshot 未產生。
- 驗證：
  - 直接 exploratory probe 先以相同 X `BadWindow` 失敗。
  - `timeout 90s poetry run python scripts/dev/probe_pyvistaqt_runtime.py --output-dir artifacts/ui/visualization-render --timeout-seconds 60`
    -> wrote artifacts。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_probe_pyvistaqt_runtime.py -q`
    -> `2 passed`。
  - targeted `ruff check` / `ruff format --check` clean。
  - `poetry run basedpyright scripts/dev/probe_pyvistaqt_runtime.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐目前 session 的 interactive PyVistaQt runtime 被 blocked。
  - 仍不能宣稱 XBrainLab interactive 3D saliency render 或真人 OpenGL desktop walkthrough 完成。

### 2026-05-04 Usage refresh handoff

- 做了什麼：
  - 因使用量即將刷新，刷新 `artifacts/goal/handoff-2026-05-04-usage-refresh.md`。
  - 同步刷新 `artifacts/goal/continuation-2026-05-04-product-completion.md`。
  - 交接點明確標在 product commit `26bed60 validation: probe pyvistaqt runtime` 之後。
- 目前狀態：
  - 最新 verified slices 包含 format capability matrix、reviewed MAT sample-anchor apply、
    Windows launcher geometry capture、PyVistaQt runtime probe。
  - 預期剩餘 dirty files 只有 protected `.vscode/settings.json` 和 root `settings.json`。
- 不能宣稱：
  - Goal 仍不能完成；embedded Data Interpretation label editor、Inspector GUI、真人 Windows
    launcher click-through、interactive 3D、XDF / LSL、real-data certification、external thesis
    experiment runner 仍是 blockers。

### 2026-05-04 Data Interpretation role review UI

- 做了什麼：
  - `DataInterpretationPreviewDialog` 的 event role rows 現在可編輯，`get_result()` 會回傳
    `choices.event_roles`。
  - label carrier table 新增 `Role` 欄位，會把 carrier role 併入 `label_carrier_choices`。
  - `scripts/dev/capture_data_interpretation_replay.py` 會在 replay 中確認 `trial_type` 是
    `class cue`，並把 `events.tsv` role 設為 `class cue labels`。
- TDD：
  - focused UI test 初跑失敗，因 `event_roles` 沒有從 dialog choices 輸出。
  - focused UI test 初跑失敗，因 label carrier `role` 沒有輸出。
- 驗證：
  - focused UI tests -> `2 passed`。
  - full dialog suite -> `8 passed`。
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `47 passed`。
  - full ApplicationService unit suite -> `43 passed`。
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`。
  - replay JSON 顯示 `class cue labels` 和 `review_choices.event_roles.trial_type = class cue`。
  - targeted `ruff check` / `ruff format --check` clean。
  - targeted `basedpyright` clean。
- 不能宣稱：
  - 這支撐 role review 已進 Data Interpretation recipe UI。
  - 仍不是完整 embedded post-load label editor、raw trigger selector、全格式 real-data
    certification 或真人 click-through。

### 2026-05-04 Data Interpretation label carrier selectors

- 做了什麼：
  - label carrier review 的 label field、anchor、time model、granularity、role 欄位改用
    `QComboBox` selectors。
  - selector 顯示人話選項，例如 `Seconds`、`Trial`、`Class cue labels`。
  - `get_result()` 從 combo `itemData` 讀 recipe value，保存 `seconds`、`trial` 等 backend 值。
  - replay script 改用 selector 操作並刷新 screenshots / JSON。
- TDD：
  - selector-focused UI test 初跑失敗，因欄位沒有 combo widget。
- 驗證：
  - full dialog suite -> `9 passed`。
  - DatasetActionHandler suite -> `47 passed`。
  - focused ApplicationService recipe flow -> `1 passed`。
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`。
  - replay JSON 顯示 visible row 使用 `Seconds` / `Trial` / `Class cue labels`，choices 使用
    `seconds` / `trial` / `class cue labels`。
  - targeted `ruff check` / `ruff format --check` clean。
  - targeted `basedpyright` clean。
- 不能宣稱：
  - 這支撐 label carrier review selector UX。
  - 仍不是完整 embedded post-load label editor、raw trigger selector、全格式 real-data
    certification 或真人 click-through。

### 2026-05-04 Add Labels compatibility guard

- 做了什麼：
  - Dataset sidebar 在 empty state 會 disable `Add Labels to Loaded Data`，tooltip 指向先
    interpret data source。
  - locked state 也會 disable 該 compatibility action。
  - `DatasetActionHandler.import_label()` 會先讀 backend `ImportLabelsCommand` capability，
    blocked 時直接顯示人話 reason，不開 legacy dialog。
  - 沒有 table rows 時不再問 `Apply to ALL?`，改成 warning。
  - Data Interpretation replay JSON 新增 empty/applied sidebar button state。
- TDD：
  - focused sidebar tests 初跑失敗，因 button 沒有 disable。
  - focused action tests 初跑失敗，因 no-data / capability block guard 缺失。
- 驗證：
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_dataset_sidebar.py -q`
    -> `54 passed`。
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`。
  - replay JSON empty state：button enabled `False`，tooltip `Interpret a data source before adding labels.`。
  - replay JSON applied state：button enabled `True`，tooltip 提示 update current recipe trace。
  - targeted `ruff check` / `ruff format --check` clean。
  - targeted `basedpyright` clean。
- 不能宣稱：
  - 這支撐 compatibility label action 的 state guard。
  - 仍不是完整 Data Interpretation embedded label editor。

### 2026-05-04 Tool-call best-practices / 117-case dashboard

- 做了什麼：
  - 研究並落地 OpenAI Structured Outputs / function calling、Berkeley Function Calling
    Leaderboard、LangSmith trajectory evaluation 的可執行設計重點。
  - 新增 `XBrainLab/llm/tools/schema_contract.py`，用 prompt-facing taxonomy contract 統一
    tool schema 呈現，Data Interpretation 標為資料入口主線，`load_data / attach_labels` 標為
    legacy compatibility。
  - `preview_interpretation.choices` 改成 structured fields：selected EEG files、label carrier、
    event role、class map、anchor、subject / session / task / run。
  - Context Assembler / local eval prompt 強化 no-call、ask-clarification、legacy compatibility
    降權和 Data Interpretation primary path。
  - Controller 對 no-tool / ask-clarification intent 加入短路回覆，避免概念問題或缺輸入時
    執行 mutating tool。
  - Parser 支援 `tool` alias、OpenAI-style function payload、no_tool / ask_clarification output；
    normalizer 補 safe repair：drop optional null、preview fields 移進 `choices`、task/event role
    confusion、relative recipe path、explicit legacy load request。
  - Verifier 補 nested object required / type / enum / unknown-field checks。
  - deterministic / local eval cases 擴到 `117`，新增中文、中英混雜、ambiguous / missing input、
    no-call / should-not-call、wrong-tool temptation、blocked command、multi-intent、multi-turn
    recovery、Data Interpretation confirmation boundary、BIDS / label ambiguity / subject metadata、
    destructive / long-running confirmation 和 EEG/BCI domain phrasing。
  - scorer 新增 tool-or-no-tool decision、clarification behavior、confirmation boundary、visible
    response quality、family pass rate、failure taxonomy、worst cases 和 repeated-run stability。
  - 新增 `scripts/agent/evals/write_tool_call_eval_dashboard.py`，產生
    `artifacts/agent_evals/dashboard.md`。
- local model resource boundary：
  - primary / fallback 都已 cached，runtime classification `gpu-ready`。
  - cache usage `15.34 GB`，本輪沒有下載模型。
- evidence：
  - deterministic baseline：`117 / 117` pass。
  - primary `microsoft/Phi-4-mini-instruct`：`117 / 117` x `3` pass。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`117 / 117` x `3` pass。
  - dashboard：`artifacts/agent_evals/dashboard.md`，含 model comparison、metric pass rates、
    family pass rates、failure taxonomy、worst cases、source / artifact paths 和 thesis claim boundary。
- validation：
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_definitions.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/scripts/test_write_tool_call_eval_dashboard.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `343 passed`。
  - targeted `ruff check` -> pass。
  - targeted `ruff format --check` -> pass。
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
    -> wrote `artifacts/agent_evals/dashboard.md`。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這支撐目前 benchmark slice 的 thesis-candidate tool-call claim。
  - 仍不能宣稱 UI usability、Windows launcher、雙螢幕 / DPI、長時間 desktop session、human
    desktop acceptance、EEG training quality 或 product completion。
  - 最新要求的單一 UI-observable automated human-like walkthrough 尚未完成；現有 UI artifacts
    是 sliced walkthrough，下一輪需產生完整 screenshots / visible text / button state / workflow
    state / transcript / CommandResult / state snapshot artifact。

### 2026-05-04 UI-observable automated human-like walkthrough

- 做了什麼：
  - 新增 `scripts/dev/capture_human_like_product_walkthrough.py`，用真 Qt MainWindow、
    Data Interpretation dialog、ChatPanel 和 ApplicationService command spine 產生 consolidated
    automated human-like walkthrough。
  - 新增 `tests/unit/scripts/test_capture_human_like_product_walkthrough.py`，驗證 artifact schema、
    required phases、claim boundary、visible raw-syntax guard 和 Markdown report。
  - artifact 保存：
    - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`
    - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`
    - `artifacts/ui/human-like-walkthrough/*.png` (`20` screenshots)
    - `artifacts/ui/human-like-walkthrough/walkthrough-import.recipe.json`
- 覆蓋：
  - app startup、main window initial state、Dataset page 和 source selection。
  - Data Interpretation scan / preview / confirm metadata-label choices / apply / save recipe /
    reload recipe。
  - safe / needs_confirmation / blocked validation decision probes。
  - preprocess、epoch、dataset generation。
  - EEGNet CPU training readiness，不啟動長時間 training。
  - evaluation / visualization / saliency readiness。
  - ChatPanel empty state、normal message、missing-input clarification、blocked command、
    successful tool result summary、repeated open-close、narrow panel。
  - reset / new session confirmation boundary 和 missing-scan error recovery。
  - visible text snapshots、button enabled / disabled state、workflow state snapshots、
    CommandResult payloads、tool transcript、user-facing transcript、process/thread notes。
- 結果：
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py --output-dir artifacts/ui/human-like-walkthrough`
    -> exit `0`。
  - artifact summary：status `passed`、`26 / 26` phases、`20` screenshots、human desktop
    acceptance `not performed`。
  - resource notes：Python thread count `1` before close / after close；Qt active thread count `0`。
  - unit helper tests：`poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `5 passed`。
  - targeted `ruff check` / `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `git diff --check` -> pass。
  - manual screenshot spot-check：
    - Data Interpretation preview is nonblank and shows scan -> preview -> validate -> confirm ->
      apply -> save recipe, but table density still needs polish.
    - ChatPanel empty / success / narrow screenshots are nonblank; panel-level narrow capture keeps
      Send visible and wraps bubbles.
    - Eval dashboard report screenshot is readable.
- 不能宣稱：
  - 這是 automated UI-observable PyQt replay，不是真人 Windows desktop acceptance。
  - Windows launcher click-through、雙螢幕 / DPI、長時間 true local model desktop session 仍是
    remaining human verification。
  - walkthrough 截圖暴露下一輪 UI polish 方向：Data Interpretation table density、main-window
    narrow-with-assistant layout、analysis page compact controls。

### 2026-05-04 Walkthrough-driven UI polish

- 做了什麼：
  - 放大並重排 Data Interpretation preview / confirm dialog：metadata preview 改為全寬，
    label carrier / event / recipe trace stacked review surface，固定主要欄寬，避免 preview
    像擠在 debug panel 裡。
  - Training plot 重新調整 Matplotlib dark-theme 套用順序，空狀態標題 / 座標 / tick 不再是黑字。
  - Training history compact header 改成 `Epochs`，縮短前幾欄預設寬度，讓 800px walkthrough
    capture 的關鍵欄位完整可見。
  - Evaluation toolbar 改成 compact controls：combo width 收斂、spacing 縮小、`Show Percentage`
    改為 `Percent`。
  - Human-like walkthrough required phases 補上 `eval_dashboard_report`，artifact summary 從
    `26 / 25` 修成 `26 / 26`。
- evidence：
  - refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` / `.json`。
  - refreshed screenshots include `04-interpretation-preview.png`、`05-interpretation-confirm.png`、
    `10-training-readiness.png`、`11-analysis-readiness.png`、`17-assistant-narrow.png`。
  - artifact summary：status `passed`、`26 / 26` required phases、`20` screenshots、human desktop
    acceptance `not performed`。
- validation：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/training/test_metric_tab.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `62 passed`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `5 passed`。
  - targeted `ruff check` -> pass。
  - targeted `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py --output-dir artifacts/ui/human-like-walkthrough`
    -> exit `0`。
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
  - `git diff --check` -> pass。
- 不能宣稱：
  - 這是 automated UI-observable PyQt replay 和 screenshot-driven polish，不是真人 Windows
    launcher click-through、雙螢幕 / DPI 或長時間 true local model desktop acceptance。
  - Data Interpretation 仍缺 mature embedded label editor、raw event anchor / MAT variable editor
    和全格式 manual certification；legacy post-load label compatibility path 仍需繼續降權。

### 2026-05-04 ChatPanel reset boundary polish

- 做了什麼：
  - 修 `ChatPanel._clear_ui()`：清 conversation 時舊 message bubble 會立即 `hide()` 並 detach，
    不只 `deleteLater()`，避免 DeferredDelete 前舊 bubble 還可見。
  - 補 ChatPanel unit test，確認 append message 會隱藏 empty state，clear 後舊 bubble 立即不可見 /
    detached，empty state 才重新顯示。
  - human-like walkthrough 直接用 `ApplicationService` 執行 reset / recovery command 後，現在會刷新
    `AgentManager` workflow status，避免 reset 後主資料已清空但 ChatPanel / status bar 仍顯示
    `Ready to train`。
- evidence：
  - refreshed `artifacts/ui/human-like-walkthrough/18-reset-boundary.png` 不再顯示舊 bubbles，也不再
    顯示 stale `Ready to train`；可見狀態為 `No EEG files are open yet.` / `No EEG data open · Import files to begin`。
  - refreshed `19-error-recovery.png` 只顯示 recovery request / response，不顯示 empty-state overlap。
  - artifact summary 仍為 status `passed`、`26 / 26` required phases、`20` screenshots。
- validation：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py -q`
    -> `40 passed`。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `5 passed`。
  - targeted `ruff check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py --output-dir artifacts/ui/human-like-walkthrough`
    -> exit `0`。
- 不能宣稱：
  - 這修的是 automated walkthrough 暴露的 ChatPanel reset / status UI bug。
  - 仍不是真人 Windows desktop acceptance，也不是長時間 true local model conversation soak。

### 2026-05-04 Data Interpretation metadata apply to loaded data

- 做了什麼：
  - `ApplicationService._handle_apply_interpretation()` 現在會把 reviewed metadata 同步到已載入
    Raw wrapper：subject/session 寫入 `set_subject_name()` / `set_session_name()`，task/run 保存到
    `data_interpretation_metadata` runtime detail。
  - `apply_interpretation` diagnostics 新增 `metadata_apply`，讓 backend / artifact 能看到哪些 loaded
    files 收到 reviewed metadata。
  - Dataset table header / widths 改成 compact scan layout：`File`、`Subject`、`Session`、`Chan`、
    `Hz`、`Epochs`、`Events`，避免 applied state 把 `session-01` 或 events 截掉。
  - human-like walkthrough 的 tiny synthetic dataset 在 metadata 正確分成多 subject 後，改用 group
    training split，避免 individual split 在小 fixture 上產生 empty validation rollback。
- evidence：
  - backend unit test 覆蓋 Data Interpretation apply 後 loaded data subject/session/runtime detail
    會更新，diagnostics 會回傳 `metadata_apply`。
  - refreshed `artifacts/ui/human-like-walkthrough/06-interpretation-applied.png` 顯示 Dataset table
    applied state 為 `S01` / `session-01`，不是 `0 / 0`。
  - refreshed `10-training-readiness.png` 顯示 Start Training enabled；artifact command result 顯示
    `generate_dataset` ok、`dataset_count=1`。
- validation：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_apply_updates_loaded_metadata tests/unit/backend/application/test_application_service.py::test_data_interpretation_choices_flow_into_recipe -q`
    -> `2 passed`。
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `95 passed`。
  - script helper tests：`poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `5 passed`。
  - targeted `ruff check` / `ruff format --check` -> pass。
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py --output-dir artifacts/ui/human-like-walkthrough`
    -> exit `0`。
- 不能宣稱：
  - 這修的是 reviewed metadata propagation 和 visible Dataset table trust。
  - 仍不是 full BIDS entities editor、raw trigger selector、complex GDF/MAT anchor reconciliation 或
    full import wizard completion。

### 2026-05-04 Walkthrough observable evidence hardening

- 做了什麼：
  - `scripts/dev/capture_human_like_product_walkthrough.py` 現在會把 per-phase evidence 彙整到
    top-level `observable_evidence`，包含 visible text snapshots、button states、
    workflow snapshots、backend state snapshots 和 phase screenshot index。
  - 同一 artifact 新增 `ui_quality_review`，逐張 screenshot 記錄 exists / nonblank automated
    review，並保存 forbidden visible text findings 與 human design review boundary。
  - `validate_walkthrough_payload()` 會拒絕缺少 observable evidence、缺少 UI quality review 或
    UI quality automated checks 未通過的 artifact。
  - Markdown report 新增 `UI Quality Review` 和 `Observable Evidence` sections，reviewer 不必只讀
    raw JSON phases。
- evidence：
  - refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`：
    `observable_evidence.visible_text_snapshots=26`、`button_states=26`、
    `workflow_states=26`、`ui_quality_review.automated_checks_passed=True`。
  - refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` 顯示 UI quality review
    和 observable evidence counts。
  - artifact summary 仍是 status `passed`、`26 / 26` phases、`20` screenshots、human desktop
    acceptance `not performed`。
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `9 passed`。
  - `timeout 300s poetry run ruff check scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> pass。
  - `timeout 300s poetry run ruff format --check scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> pass。
  - `timeout 300s poetry run basedpyright scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py --output-dir artifacts/ui/human-like-walkthrough`
    -> exit `0`。
- 不能宣稱：
  - 這補強 automated UI-observable artifact 的可審查性，不是真人 Windows desktop acceptance。
  - screenshot nonblank / visible-text-clean 仍不等於真人確認 Windows launcher、雙螢幕 / DPI、
    長時間 local model desktop session 或完整產品 release。

### 2026-05-05 UI runtime service-success fallback cleanup

- 做了什麼：
  - 依 architecture / Data Interpretation / MCP adapter review skill 重新檢查 UI、agent、MCP 的
    ApplicationService boundary；MCP stdio server 和 automation adapter quick source read 顯示仍經
    `backend.application.automation` -> `ApplicationService.execute()`。
  - 修 Dataset panel direct file import：當 `_run_data_interpretation_import()` 未處理來源、但
    `LoadDataCommand` 回傳 successful `CommandResult` 時，UI 現在更新 panel 並顯示使用者訊息，不再
    再呼叫 `DatasetController.import_files()`。
  - 修 Preprocess reset：UI reset button 現在送 `ResetPreprocessCommand(confirmed=True)`；successful
    service result 不再再呼叫 `PreprocessController.reset_preprocess()`。
  - controller fallback 僅保留在 `execute_application_command()` 回傳 `None` 的 mock / legacy
    adapter 情境，避免 unit tests 的 incomplete mock state 誤觸真 service。
- red tests：
  - `tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_service_load_success_does_not_fallback_to_controller`
    初始失敗，證明 successful `LoadDataCommand` 後仍呼叫 controller import。
  - `tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_service_success_does_not_fallback_to_controller`
    初始失敗，證明 reset UI 仍直接呼叫 controller reset。
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_service_load_success_does_not_fallback_to_controller -q`
    -> `1 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_service_success_does_not_fallback_to_controller -q`
    -> `1 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/actions.py XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_ui_misc.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/dataset/test_panel.py`
    -> pass。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/dataset/test_panel.py -q`
    -> `85 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
  - Direct targeted `basedpyright` on the UI test files hit an unrelated pre-existing type issue in
    `tests/unit/ui/test_ui_misc.py` around `dlg.label_data_map`; use full `poetry run basedpyright`
    for the slice gate.
- 不能宣稱：
  - 這只關閉兩個明確 service-success fallback bypass，不代表所有 UI controller paths 已清空。
  - UI 仍保留 read-only panel refresh / dialog-local logic / mock compatibility controller path。
  - 仍需繼續盤點 training / visualization UI mutating calls、agent montage / UI routing edge cases
    和 Windows human desktop acceptance。

### 2026-05-05 Training sidebar destructive command cleanup

- 做了什麼：
  - 修 Training sidebar 重新 split 前的 destructive dataset cleanup：使用者確認後先走
    `ClearDatasetsCommand(confirmed=True)`，successful service result 不再呼叫
    `TrainingController.clean_datasets()`；adapter unavailable 的 mock / legacy `None` path 才 fallback。
  - 修 Clear History：現在先顯示 user confirmation，再走
    `ClearTrainingHistoryCommand(confirmed=True)`；successful service result 不再呼叫
    `TrainingController.clear_history()`。
  - 更新 `start_training_ui_action()` docstring，避免再把產品執行語意寫成 controller-first。
- red tests：
  - `tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_service_success_does_not_fallback_to_controller`
    初始失敗，證明 re-split cleanup 只直接呼叫 controller cleanup，service call 只出現在
    `GenerateDatasetCommand`。
  - `tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_service_success_does_not_fallback_to_controller`
    初始失敗，證明 Clear History 完全沒有呼叫 command adapter。
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_service_success_does_not_fallback_to_controller tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_service_success_does_not_fallback_to_controller -q`
    -> `2 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py`
    -> pass。
  - `timeout 300s poetry run ruff format --check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `40 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 不能宣稱：
  - 這只修 Training sidebar 兩個 destructive cleanup path；model/settings/start/stop 已 service-first，
    但 training UI 仍有 controller read-only checks 和 mock fallback。
  - 還不能宣稱所有 UI mutating controller paths 已清完，也不能替代 Windows human desktop
    acceptance。

### 2026-05-05 Data Interpretation format boundary extraction

- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_formats.py`，承接 GDF、EDF / BDF、
    EEGLAB、BrainVision、MNE FIF、MAT、CSV / TSV、TXT、BIDS events 和 XDF / LSL 的
    supported / needs-review / blocked capability taxonomy。
  - `data_interpretation.py` 改為匯入 shared constants 和 `format_capabilities()`，不再直接承接
    format matrix helper；檔案從 `1268` 行降到 `1131` 行。
  - 新增 focused unit test，鎖住 GDF needs-review、BIDS events external label review 和
    XDF / LSL blocked 邊界。
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_formats.py -q`
    初始紅燈：`ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_formats`。
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
    -> `5 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py`
    -> pass。
  - `timeout 300s poetry run ruff format --check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_formats.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_formats.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `80 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 不能宣稱：
  - 這是 Data Interpretation internal boundary cleanup，不是 mature import wizard completion。
  - Scanner、candidate builder、preview builder、validator、recipe serialization 仍在
    `data_interpretation.py`，後續還可繼續分割。

### 2026-05-06 Data Interpretation metadata boundary extraction

- scope：
  - Backend-only Data Interpretation internal boundary cleanup。
  - No UI / agent / MCP command shape changes.
- current call sites：
  - `scan_source_path()` builds per-file subject/session/task/run metadata.
  - `import_recipe_from_dict()` rebuilds serialized metadata.
  - `bids` summary is emitted in `ScanResult` and downstream state / automation envelopes.
- target boundary：
  - `data_interpretation_metadata.py` owns metadata dataclasses, BIDS entity resolution,
    filename-rule needs-confirmation inference, BIDS summary, and recipe metadata rehydration.
  - `data_interpretation.py` keeps lifecycle orchestration and imports the focused metadata helpers.
- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_metadata.py`。
  - Moved `MetadataFieldResolution` / `FileMetadataResolution` and metadata helper functions out of
    `data_interpretation.py`.
  - Added direct unit coverage for BIDS metadata, filename-rule confirmation, BIDS summary, and
    serialized metadata rehydration.
  - `data_interpretation.py` reduced from about `1131` lines to about `928` lines after this slice.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_metadata.py -q`
    initial failure: `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_metadata`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_metadata.py -q`
    -> `4 passed`。
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_metadata.py`
    -> pass。
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_metadata.py`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_preview_validate_requires_confirmation tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
    -> `11 passed`。
  - `timeout 300s poetry run ruff format --check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_metadata.py`
    -> pass after formatting the new metadata test file.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `84 passed`。
  - `timeout 300s poetry run ruff check .`
    -> pass。
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`。
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning。
  - `timeout 120s git diff --check`
    -> pass。
- 不能宣稱：
  - 這是 metadata parser / serializer boundary cleanup，不是 import wizard UX completion。
  - Recipe serialization, candidate / preview builder, validator, and label carrier planner still need
    future decomposition.

### 2026-05-06 Data Interpretation recipe boundary extraction

- scope：
  - Backend-only Data Interpretation internal boundary cleanup.
  - Public service imports remain compatible through `data_interpretation.py` re-exports.
- current call sites：
  - `DataInterpretationCommandService.save_interpretation_recipe()` builds recipes from applied
    interpretation state.
  - `reload_interpretation_recipe` loads recipe JSON and re-runs scan / preview / validation.
  - `backend.application.__init__` re-exports `ImportRecipe` from `data_interpretation`.
- target boundary：
  - `data_interpretation_recipe.py` owns `ImportRecipe`, JSON write/load, from-dict rehydration,
    and applied interpretation -> recipe conversion.
  - `data_interpretation.py` keeps lifecycle orchestration and re-exports public recipe names.
- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_recipe.py`。
  - Moved `ImportRecipe`, `load_import_recipe`, `import_recipe_from_dict`, and `build_import_recipe`
    out of `data_interpretation.py`.
  - Added direct unit coverage for recipe from-dict mapping, write/load roundtrip, and JSON-ready
    metadata serialization.
  - `data_interpretation.py` reduced from about `928` lines to about `822` lines after this slice.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py -q`
    initial failure: `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_recipe`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py -q`
    -> `3 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_recipe.py`
    -> pass after import re-export cleanup.
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_recipe.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply tests/unit/backend/application/test_application_service.py::test_data_interpretation_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
    -> `14 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `87 passed`.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is recipe serialization boundary cleanup, not a product-complete Data Interpretation wizard.
  - Scanner, candidate / preview builder, validator, and label carrier planner still remain in
    `data_interpretation.py`.

### 2026-05-06 Data Interpretation label carrier boundary extraction

- scope：
  - Backend-only Data Interpretation internal boundary cleanup.
  - No command shape, UI, agent, MCP, or recipe schema changes.
- current call sites：
  - `build_interpretation_candidate()` builds `label_carrier_plan` from scan carriers and wizard
    `label_carrier_choices`.
  - `_choice_recipe_trace()` records whether label carrier choices were supplied.
- target boundary：
  - `data_interpretation_label_carriers.py` owns label carrier choice normalization, MAT variable
    discovery, CSV / TSV / BIDS events column discovery, anchor candidates, time-model defaults,
    granularity defaults, and user-facing review reasons.
  - `data_interpretation.py` keeps lifecycle orchestration and imports the focused planner.
- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_label_carriers.py`。
  - Moved label carrier planner helpers and CSV / MAT parser helpers out of `data_interpretation.py`.
  - Added direct unit coverage for BIDS events user choices and path/name choice-key normalization.
  - `data_interpretation.py` reduced from about `822` lines to about `581` lines after this slice.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_label_carriers.py -q`
    initial failure: `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_label_carriers`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_label_carriers.py -q`
    -> `2 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_label_carriers.py`
    -> pass.
  - `timeout 300s poetry run ruff format --check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_label_carriers.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_label_carriers.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth -q`
    -> `16 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `89 passed`.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 120s git diff --check`
    -> pass.
- 不能宣稱：
  - This is label carrier planner boundary cleanup, not embedded label editor completion.
  - Scanner, candidate / preview builder, validator, and metadata override helper still remain in
    `data_interpretation.py`.

### 2026-05-05 Data Interpretation review boundary extraction

- scope：
  - Backend-only Data Interpretation internal boundary cleanup。
  - No command shape, UI, agent, MCP, automation, or recipe schema changes.
- current call sites：
  - `DataInterpretationCommandService.handle_preview_interpretation()` builds a reviewable preview
    from an interpretation candidate.
  - `DataInterpretationCommandService.handle_validate_interpretation()` emits the safe /
    needs-confirmation / blocked decision used by UI, agent, headless, and MCP command results.
- target boundary：
  - `data_interpretation_review.py` owns `InterpretationPreview`, `ValidationDecision`, candidate
    preview serialization, and validation decision construction.
  - `data_interpretation.py` keeps scanner / candidate lifecycle and re-exports public review names
    for compatibility.
- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_review.py`。
  - Moved `InterpretationPreview`, `ValidationDecision`, `build_interpretation_preview()`, and
    `validate_interpretation_candidate()` out of `data_interpretation.py`.
  - Added direct unit coverage for preview serialization and blocked / needs-confirmation / safe
    validation decisions.
  - `data_interpretation.py` reduced from about `581` lines to about `463` lines after this slice.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py -q`
    initial failure: `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_review`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py -q`
    -> `2 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_review.py`
    -> pass.
  - `timeout 300s poetry run ruff format --check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_review.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_review.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_preview_validate_requires_confirmation tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
    -> `6 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `91 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 120s git diff --check`
    -> pass.
- 不能宣稱：
  - This is review payload / validator boundary cleanup, not mature import wizard completion.
  - Scanner, candidate builder, and metadata override helper still remain in `data_interpretation.py`.

### 2026-05-05 Data Interpretation scanner boundary extraction

- scope：
  - Backend-only Data Interpretation internal boundary cleanup。
  - No command shape, UI, agent, MCP, automation, or recipe schema changes.
- current call sites：
  - `DataInterpretationCommandService.handle_scan_source()` calls `scan_source_path()` and stores
    `ScanResult` lifecycle state.
  - `reload_interpretation_recipe` re-runs scan / preview / validation through the same scanner.
- target boundary：
  - `data_interpretation_scan.py` owns `ScanResult`, source scanning, source kind classification,
    BIDS root detection, candidate file traversal, label carrier discovery, scan warnings, and
    blocked reason assembly.
  - `data_interpretation.py` keeps candidate building / metadata override / applied lifecycle and
    re-exports public scan names for compatibility.
- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_scan.py`。
  - Moved `ScanResult`, `scan_source_path()`, and scan helper functions out of
    `data_interpretation.py`.
  - Added direct unit coverage for BIDS file / label / metadata discovery, XDF blocked boundary,
    and explicit file source hint.
  - `data_interpretation.py` reduced from about `463` lines to about `286` lines after this slice.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_scan.py -q`
    initial failure: `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_scan`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_scan.py -q`
    -> `3 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_scan.py tests/unit/backend/application/test_data_interpretation_scan.py`
    -> pass after import sorting.
  - `timeout 300s poetry run ruff format --check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_scan.py tests/unit/backend/application/test_data_interpretation_scan.py`
    -> pass after formatting the new scan test file.
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_scan.py tests/unit/backend/application/test_data_interpretation_scan.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_scan.py tests/unit/backend/application/test_data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_preview_validate_requires_confirmation tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
    -> `21 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `94 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 120s git diff --check`
    -> pass.
- 不能宣稱：
  - This is source scanner boundary cleanup, not mature import wizard completion.
  - Candidate builder and metadata override helper still remain in `data_interpretation.py`.

### 2026-05-05 Data Interpretation candidate boundary extraction

- scope：
  - Backend-only Data Interpretation internal boundary cleanup。
  - No command shape, UI, agent, MCP, automation, or recipe schema changes.
- current call sites：
  - `DataInterpretationCommandService.handle_preview_interpretation()` builds an
    `InterpretationCandidate` from the latest `ScanResult`.
  - `reload_interpretation_recipe` reuses the same candidate builder with recipe choices.
- target boundary：
  - `data_interpretation_candidate.py` owns `InterpretationCandidate`, scan + user choices to
    candidate conversion, metadata overrides, event/class mapping, label-carrier choice trace, and
    candidate recipe trace.
  - `data_interpretation.py` keeps shared `InterpretationDecision`, `AppliedInterpretation`, and
    compatibility re-exports.
- 做了什麼：
  - 新增 `XBrainLab/backend/application/data_interpretation_candidate.py`。
  - Moved `InterpretationCandidate`, `build_interpretation_candidate()`, metadata override helpers,
    event/class choice normalization, and candidate recipe trace helper out of
    `data_interpretation.py`.
  - Added direct unit coverage for metadata override, event/class choices, label-carrier recipe
    trace, and empty selection blocking.
  - `data_interpretation.py` reduced from about `286` lines to about `75` lines after this slice.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py -q`
    initial failure: `ModuleNotFoundError: XBrainLab.backend.application.data_interpretation_candidate`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py -q`
    -> `2 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_candidate.py`
    -> pass.
  - `timeout 300s poetry run ruff format --check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_candidate.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_candidate.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_scan.py tests/unit/backend/application/test_data_interpretation_review.py tests/unit/backend/application/test_data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_preview_validate_requires_confirmation tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries tests/unit/backend/application/test_application_service.py::test_data_interpretation_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
    -> `25 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `96 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `466 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 120s git diff --check`
    -> pass.
- 不能宣稱：
  - This is candidate builder boundary cleanup, not mature import wizard completion.
  - `AppliedInterpretation` remains in `data_interpretation.py`; apply side effects still live in
    `DataInterpretationApplyService`.

### 2026-05-05 Agent legacy data-entry prompt downgrade

- scope：
  - Agent tool-surface / prompt-state cleanup。
  - No backend command shape, UI widget, MCP schema, or recipe schema changes.
- problem：
  - `load_data` / `attach_labels` had already been moved to a compatibility backend service, but
    `STAGE_CONFIG` and `ContextAssembler` could still present them as normal primary tools.
  - Backend capability policy could reintroduce a compatibility tool into the prompt even if a
    stage wanted Data Interpretation to be the primary data-entry language.
- target boundary：
  - Empty / Data Loaded / Preprocessed stage guidance presents Data Interpretation scan / preview /
    validate / apply / recipe as the data-entry path.
  - `ContextAssembler` intersects backend-enabled tools with the stage allowlist before prompt
    exposure.
  - Parser / confidence / verification can still recognize legacy compatibility tools through the
    schema taxonomy, so compatibility paths remain testable without becoming the primary prompt.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_assembler_stage.py -q`
    initially failed `7` tests because `load_data` / `attach_labels` were still exposed by stage
    config and backend policy could reintroduce a stage-filtered legacy tool.
- 做了什麼：
  - Removed `load_data` from the Empty stage tool list and changed Empty guidance to start the Data
    Interpretation workflow.
  - Removed `attach_labels` from Data Loaded / Preprocessed primary tools and rewrote label guidance
    around Data Interpretation preview / validation / recipe trace.
  - Added analysis-readiness tools to the Trained stage so trained state retains evaluation /
    visualization / saliency readiness.
  - Changed `ContextAssembler._application_allowed_tools()` to intersect backend capability policy
    with the current stage allowlist while preserving non-policy stage tools such as UI routing.
  - Changed confidence known-tool collection to use `TOOL_TAXONOMY`, keeping legacy tools
    recognizable outside primary stage prompts.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/test_confidence.py -q`
    -> `46 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/llm/pipeline_state.py XBrainLab/llm/agent/assembler.py XBrainLab/llm/agent/confidence.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/test_confidence.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/llm/pipeline_state.py XBrainLab/llm/agent/assembler.py XBrainLab/llm/agent/confidence.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/test_confidence.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/test_confidence.py -q`
    -> `32 passed`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `96 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
- 不能宣稱：
  - This is an agent prompt/tool-exposure downgrade, not full removal of legacy compatibility paths.
  - UI post-load label compatibility and MCP/client-facing language still need continued audit.
  - No new UI screenshot or local LLM rerun was produced in this slice.

### 2026-05-05 Automation / MCP legacy compatibility metadata

- scope：
  - Backend automation / MCP schema cleanup。
  - No MCP transport change, command execution path change, UI change, or command name removal.
- problem：
  - `COMMAND_TAXONOMY` already marked `load_data` / `attach_labels` / `import_labels` as
    `legacy_data_compatibility`, but command descriptions and MCP `tools/list` metadata did not
    clearly state they were non-primary workflow tools.
  - External MCP/headless clients could still see `Load Data` / `Attach Labels` as ordinary peer
    tools without a preferred Data Interpretation path.
- target boundary：
  - `AutomationCommandSpec` owns client-facing workflow metadata alongside command schema and live
    capability.
  - Legacy data-entry commands remain callable but expose `legacy_compatibility=True`,
    `primary_workflow=False`, and Data Interpretation preferred commands.
  - MCP `tools/list` mirrors the same truth through `x_xbrainlab`.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py::test_legacy_compatibility_commands_are_not_primary_mcp_workflow -q`
    initially failed with `AttributeError: 'AutomationCommandSpec' object has no attribute
    'legacy_compatibility'`.
- 做了什麼：
  - Added `legacy_compatibility`, `primary_workflow`, and `preferred_commands` to
    `AutomationCommandSpec`.
  - Added legacy command descriptions that explicitly say "Legacy compatibility" and prefer
    Data Interpretation scan / preview / validate / apply / recipe.
  - Added matching MCP `x_xbrainlab` metadata for external clients.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py::test_legacy_compatibility_commands_are_not_primary_mcp_workflow -q`
    -> `1 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/automation.py tests/unit/backend/application/test_automation.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/automation.py tests/unit/backend/application/test_automation.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py tests/integration/mcp/test_stdio_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py tests/integration/mcp/test_client_config.py -q`
    -> `12 passed`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `97 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/mcp -q`
    -> `3 passed`.
- 不能宣稱：
  - This is schema/taxonomy cleanup, not HTTP MCP or long-running job support.
  - It does not remove legacy commands from ApplicationService or UI compatibility flows.
  - No new Inspector screenshot or external human MCP client session was produced in this slice.

### 2026-05-05 Training start long-running confirmation

- scope：
  - UI / autonomy boundary cleanup for Training sidebar。
  - No backend command shape, training service, or agent tool change.
- problem：
  - Backend `train` capability exposes `requires_confirmation=True` for a long-running action.
  - ChatPanel agent path already pauses for confirmation, but the Training sidebar button could
    execute `TrainCommand` without presenting that boundary to the user.
- target behavior：
  - If backend `train` capability requires confirmation, the Start Training button asks a
    user-facing long-running confirmation before command execution.
  - If the user rejects, no `TrainCommand` is executed and controller fallback is not called.
  - If the user confirms and service returns success, controller fallback is not called.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_requires_confirmation_for_long_running_command tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_does_not_fallback_to_controller -q`
    initially failed because `QMessageBox.question` was not called for long-running `train`
    capability.
- 做了什麼：
  - Added a `Start Training` confirmation dialog in `TrainingSidebar.start_training_ui_action()`
    whenever `train` capability has `requires_confirmation` or `confirmation_required`.
  - Kept mock / legacy controller fallback only for cases where `execute_application_command()`
    returns `None`.
  - Added focused UI unit tests for rejection and service-success no-fallback behavior.
  - Captured automated Qt replay artifact:
    `artifacts/ui/training-start-confirmation/training-start-confirmation-dialog.png`,
    `.json`, and `.md`.
- validation：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_requires_confirmation_for_long_running_command tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_does_not_fallback_to_controller -q`
    -> `2 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Direct focused basedpyright on `tests/unit/ui/training/test_training_panel.py` still reports
    existing mock typing debt; full project basedpyright remains the authoritative gate.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `42 passed`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `97 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `468 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - Automated Qt replay artifact shows visible text `Start Training` /
    `Training can take time and use CPU/GPU resources. Start training now?`, enabled `Yes` / `No`
    buttons, nonblank screenshot, and empty command/controller transcript after choosing `No`.
- 不能宣稱：
  - This is automated Qt replay, not human Windows desktop acceptance.
  - This does not prove full button-driven training completion, evaluation, visualization, or
    saliency workflow.
  - MCP long-running job progress / cancel / recovery is still not implemented.

### 2026-05-05 MCP train readiness before job boundary

- scope：
  - MCP stdio adapter / ApplicationService capability boundary。
  - No MCP HTTP transport, job API, UI widget, command name, or automation schema change.
- problem：
  - Previous MCP hardening returned `long_running_job_required` for every stdio `train` call because
    `train` is a long-running capability.
  - That masked real backend readiness failures: a missing dataset / model / training option looked
    like only an MCP job API limitation.
- target behavior：
  - Unready stdio `train` returns the shared backend precondition reasons, including
    `Generate datasets before training`.
  - Backend-ready / enabled long-running `train` remains blocked from synchronous stdio execution
    with `long_running_job_required` and a job-boundary diagnostic.
  - The stdio walkthrough artifact states whether the job boundary was actually reached.
- red test：
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py::test_stdio_mcp_reports_precondition_before_long_running_job_boundary tests/unit/mcp/test_server.py::test_stdio_mcp_blocks_enabled_long_running_commands_until_job_api_exists -q`
    initially failed because unready `train` returned the old synchronous long-running block text
    instead of backend preconditions.
- 做了什麼：
  - Changed `MCPServer._call_tool()` to apply the stdio long-running block only when the backend
    capability is both `long_running` and enabled.
  - Added tests for both sides of the boundary: unready `train` precondition and ready/enabled
    `train` job-boundary block.
  - Updated `capture_mcp_stdio_walkthrough.py` and refreshed
    `artifacts/mcp/stdio-walkthrough.json` / `.md`; Markdown now shows
    `train result boundary: precondition` and `job boundary reached: False` for the default
    headless walkthrough.
- validation：
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py::test_stdio_mcp_reports_precondition_before_long_running_job_boundary tests/unit/mcp/test_server.py::test_stdio_mcp_blocks_enabled_long_running_commands_until_job_api_exists -q`
    -> `2 passed`.
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py -q`
    -> `8 passed`.
  - `poetry run ruff check XBrainLab/mcp/server.py scripts/dev/capture_mcp_stdio_walkthrough.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/mcp/server.py scripts/dev/capture_mcp_stdio_walkthrough.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 180s poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp`
    -> refreshed `artifacts/mcp/stdio-walkthrough.json` / `.md`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
    -> `10 passed`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
- 不能宣稱：
  - This is MCP stdio error-precedence hardening, not HTTP MCP or job progress / cancel /
    recovery support.
  - This is not desktop UI control certification; stdio MCP remains a headless ApplicationService
    session.

### 2026-05-05 Dataset sidebar capability truth

- scope：
  - UI/backend command truth alignment for Dataset sidebar。
  - No command schema, backend handler, MCP, agent, recipe, or screenshot artifact change.
- problem：
  - Real `Study` Dataset sidebar still used controller-local `has_data` / lock state for
    `Add Labels to Loaded Data` and Channel Selection preflight.
  - That could enable label compatibility or open a channel-selection dialog even when
    ApplicationService capability policy would block the command.
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_uses_backend_import_label_capability tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_uses_backend_preprocess_capability -q`
    initially failed because Add Labels stayed enabled in an empty real Study and Channel Selection
    opened the dialog instead of showing the backend `Load raw data before preprocessing.` reason.
- 做了什麼：
  - `DatasetSidebar.update_sidebar()` now reads `import_labels` capability for Add Labels enabled
    state and tooltip.
  - Channel Selection enabled state / tooltip and click preflight now read the backend `preprocess`
    capability when the sidebar is backed by a real `Study`.
  - Existing mock / legacy controller fallback remains for tests and non-Study compatibility paths.
- validation：
  - focused red tests after implementation -> `2 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_service_load_success_does_not_fallback_to_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_reviews_then_applies -q`
    -> `14 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py -q`
    -> `46 passed`.
  - `timeout 300s poetry run ruff format --check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `timeout 120s git diff --check`
    -> pass.
- 不能宣稱：
  - This is a Dataset sidebar capability alignment slice, not full UI product completion.
  - It does not replace human desktop acceptance, mature import wizard editor work, or a complete
    UI mutating-path audit.

### 2026-05-05 Dataset smart-parse capability truth

- scope：
  - UI/backend command truth alignment for Dataset Smart Parse。
  - No command schema, backend handler, MCP, agent, recipe, or screenshot artifact change.
- problem：
  - `open_smart_parser()` checked controller-local lock / has-data state before showing
    `SmartParserDialog`; real `Study` capability could still block `apply_smart_parse`.
  - This could let a UI dialog open even when ApplicationService would return
    `Load raw data before applying smart parse.`
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_uses_backend_capability -q`
    initially failed because `SmartParserDialog` was opened.
- 做了什麼：
  - Added a backend `apply_smart_parse` capability preflight before controller-local checks.
  - Kept existing mock / legacy non-Study behavior for compatibility tests.
- validation：
  - focused red + success path:
    `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_uses_backend_capability tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_success -q`
    -> `2 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py -q`
    -> `60 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one Dataset action capability alignment, not full UI product completion.
  - It does not prove Windows human desktop acceptance or complete remaining mutating-path audit.

### 2026-05-05 Dataset remove-files capability truth

- scope：
  - UI/backend command truth alignment for Dataset context-menu Remove Files。
  - No command schema, backend handler, MCP, agent, recipe, or screenshot artifact change.
- problem：
  - `_remove_files()` asked for user confirmation before checking whether backend capability policy
    allowed `remove_files`.
  - In a real `Study` empty/blocked state, this could ask the user to confirm an operation that the
    command layer would reject with `Load raw data before removing files.`
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_uses_backend_capability_before_confirm -q`
    initially failed because `QMessageBox.question()` was called.
- 做了什麼：
  - Added a backend `remove_files` capability preflight before the remove confirmation dialog.
  - Kept existing mock / legacy non-Study behavior for controller fallback tests.
- validation：
  - focused red + compatibility paths:
    `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_uses_backend_capability_before_confirm tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_context_menu_remove -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py -q`
    -> `61 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one context-menu action alignment, not complete UI product closure.
  - It does not prove human desktop acceptance or complete remaining mutating-path audit.

### 2026-05-05 Dataset batch-metadata capability truth

- scope：
  - UI/backend command truth alignment for Dataset context-menu batch metadata edits。
  - No command schema, backend handler, MCP, agent, recipe, or screenshot artifact change.
- problem：
  - `_batch_set()` opened the Subject / Session input dialog before checking whether backend
    capability policy allowed `update_metadata`.
  - In a real `Study` empty/blocked state, this could ask for metadata input that the command layer
    would reject with `Load raw data before updating metadata.`
- red test：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_uses_backend_capability_before_prompt -q`
    initially failed at `QInputDialog.getText()`, proving the prompt path was reached.
- 做了什麼：
  - Added a backend `update_metadata` capability preflight before the Subject / Session input
    dialog.
  - Kept existing mock / legacy non-Study behavior for controller fallback tests.
- validation：
  - focused red + compatibility paths:
    `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_uses_backend_capability_before_prompt tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_session tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_context_menu_session -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py -q`
    -> `62 passed`.
  - `timeout 300s poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass.
  - `timeout 300s poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 120s git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one context-menu metadata alignment, not complete UI product closure.
  - It does not prove human desktop acceptance or complete remaining mutating-path audit.

### 2026-05-05 Montage dialog capability truth

- scope：
  - UI/backend command truth alignment for AgentManager montage picker。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `open_montage_picker_dialog()` relied on a local `epoch_data` guard before opening the montage
    dialog, then executed `ApplyMontageCommand` after user acceptance.
  - That meant the blocked UX did not read the shared backend `apply_montage` capability reason,
    and tests still emphasized the UI-side preprocess-controller fallback.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker -q`
    initially failed because empty real `Study` showed `Error: No epoch data available for montage.`
    instead of `Create epochs before applying a montage.`
- 做了什麼：
  - Added `apply_montage` capability preflight before opening `PickMontageDialog` for real
    `Study` paths.
  - Added real `Study` success coverage proving accepted montage goes through
    `ApplyMontageCommand` and does not call the UI-side fallback controller.
  - Updated the AgentManager docstring to reflect command-layer primary behavior and mock /
    legacy fallback boundaries.
- validation：
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker -q`
    -> `5 passed`.
  - AgentManager UI regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep -q`
    -> `48 passed`.
  - backend command handler regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_montage_command_routes_confirmed_positions tests/unit/backend/application/test_analysis_service.py -q`
    -> `3 passed`.
  - `poetry run ruff check XBrainLab/ui/components/agent_manager.py tests/unit/ui/test_agent_manager_coverage.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one montage dialog alignment, not full visualization UI product acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path audit.

### 2026-05-05 Visualization sidebar montage capability truth

- scope：
  - UI/backend command truth alignment for Visualization sidebar `Set Montage`。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `ControlSidebar.set_montage()` checked `controller.has_epoch_data()` before reading backend
    capability policy.
  - In real runtime this could open a dialog while backend would block, or let stale
    controller-local state block an otherwise enabled `apply_montage` command.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_blocked_by_backend_capability tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_real_study_uses_application_service -q`
    initially failed: blocked real `Study` opened `PickMontageDialog`, and backend-ready real
    `Study` was stopped by controller-local `has_epoch_data()`.
- 做了什麼：
  - Added `apply_montage` capability preflight before `PickMontageDialog` for real `Study` paths.
  - Kept controller-local no-epoch warning only for mock / legacy non-Study paths.
  - Added real `Study` success coverage proving accepted sidebar montage uses
    `ApplyMontageCommand` and updates epoch channel positions through ApplicationService.
- validation：
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_blocked_by_backend_capability tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_real_study_uses_application_service -q`
    -> `2 passed`.
  - Visualization sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_dialogs_extra.py::TestControlSidebar -q`
    -> `10 passed`.
  - backend command handler regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_montage_command_routes_confirmed_positions tests/unit/backend/application/test_analysis_service.py -q`
    -> `3 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one visualization sidebar alignment, not full visualization UI product acceptance.
  - It does not prove desktop render, Windows human click-through, or complete remaining
    mutating-path audit.

### 2026-05-05 Training clear-history capability truth

- scope：
  - UI/backend command truth alignment for Training sidebar `Clear History` destructive action。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `TrainingSidebar.clear_history()` asked for destructive confirmation before checking backend
    `clear_training_history` capability.
  - In empty real `Study` state this could ask the user to confirm an impossible cleanup that the
    command layer would later reject.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_uses_backend_capability_before_confirm -q`
    initially failed because `QMessageBox.question()` was called.
- 做了什麼：
  - Added `clear_training_history` capability preflight before destructive confirmation for real
    `Study` paths.
  - Kept controller-local `is_training()` warning and controller fallback only for mock / legacy
    non-Study paths.
- validation：
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_uses_backend_capability_before_confirm -q`
    -> `1 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `43 passed`.
  - backend training command regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py tests/unit/backend/application/test_application_service.py::test_clear_datasets_and_training_history_commands_route_cleanup tests/unit/backend/application/test_application_service.py::test_evaluate_and_clear_history_block_when_trainer_has_no_plan_history tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `6 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one destructive-action boundary alignment, not full training UI product acceptance.
  - It does not prove long-running training human acceptance or complete remaining mutating-path
    audit.

### 2026-05-05 Reset preprocess capability truth

- scope：
  - UI/backend command truth alignment for Preprocess sidebar `Reset Preprocessing` lifecycle
    action。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `PreprocessSidebar.reset_preprocess()` called `check_data_loaded()`, which reads the
    `preprocess` edit capability.
  - After epoching or dataset generation, backend `preprocess` is intentionally blocked while
    backend `reset_preprocess` can still be enabled. The UI could therefore block the reset action
    with the wrong policy.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_uses_reset_capability_when_preprocess_locked -q`
    initially failed because the confirmation prompt was never reached.
- 做了什麼：
  - Added `reset_preprocess` capability preflight before reset confirmation.
  - Kept legacy `check_data_loaded()` only for mock / legacy non-Study paths.
  - Added blocked empty-state coverage and locked-but-resettable coverage.
- validation：
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_uses_reset_capability_when_preprocess_locked tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_blocked_by_reset_capability_before_confirm -q`
    -> `2 passed`.
  - Preprocess sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess/test_preprocess_panel.py -q`
    -> `31 passed`.
  - backend lifecycle regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_lifecycle_service.py tests/unit/backend/application/test_application_service.py::test_reset_preprocess_command_clears_downstream_training_plan tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `5 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one lifecycle reset boundary alignment, not full reset / new-session product
    acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Training configuration dialog capability truth

- scope：
  - UI/backend command truth alignment for Training sidebar model selection and training settings。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `select_model()` and `training_setting()` checked controller-local `is_training()` before
    opening dialogs, but did not read backend `configure_training` capability.
  - A stale controller-local false could open configuration dialogs while backend policy would
    reject the command because training is running.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_uses_backend_configure_capability_before_dialog tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_uses_backend_configure_capability_before_dialog -q`
    initially failed because both dialogs were opened.
- 做了什麼：
  - Added a shared `_configuration_blocked()` helper backed by `configure_training` capability for
    real `Study` paths.
  - Kept controller-local training-running warnings only for mock / legacy non-Study paths.
- validation：
  - focused red + dialog gate:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_uses_backend_configure_capability_before_dialog tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_uses_backend_configure_capability_before_dialog -q`
    -> `2 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `45 passed`.
  - backend configure-training smoke:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py::test_training_service_configures_model_and_options tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes tests/unit/backend/application/test_application_service.py::test_capability_policy_covers_all_declared_commands -q`
    -> `3 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one configuration-dialog boundary alignment, not full training setup UX or long-running
    training acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Stop training capability truth

- scope：
  - UI/backend command truth alignment for Training sidebar `Stop Training`。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `TrainingSidebar.stop_training()` returned early when controller-local `is_training()` was
    false and did not read backend `stop_training` capability.
  - A stale controller-local false could make Stop Training do nothing while backend state had an
    active training run.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_uses_backend_capability_when_controller_stale tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_blocked_by_backend_capability_before_command -q`
    initially failed: stale false skipped the command, and backend-disabled state still called the
    command path.
- 做了什麼：
  - Added `stop_training` capability preflight for real `Study` paths.
  - Kept controller-local early return only for mock / legacy non-Study paths.
- validation：
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_uses_backend_capability_when_controller_stale tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_blocked_by_backend_capability_before_command -q`
    -> `2 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `47 passed`.
  - backend stop-training smoke:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py::test_training_service_start_stop_and_clear_history tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes tests/unit/backend/application/test_application_service.py::test_capability_policy_covers_all_declared_commands -q`
    -> `3 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one stop-action boundary alignment, not full long-running training human acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Dataset inline metadata capability truth

- scope：
  - UI/backend command truth alignment for Dataset table inline Subject / Session metadata edits。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `DatasetPanel.on_item_changed()` executed `UpdateMetadataCommand` for real `Study` paths, but
    the table rendered Subject / Session cells as editable even when backend `update_metadata`
    capability was disabled by downstream state.
  - The user could edit text first, then get blocked by backend command failure, which made the UI
    feel inconsistent with shared capability policy.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_cells_use_backend_update_capability -q`
    initially failed because Subject / Session cells still had `ItemIsEditable`.
- 做了什麼：
  - `DatasetPanel.update_panel()` now reads `update_metadata` capability and renders Subject /
    Session cells read-only with the shared blocked reason when editing is disabled.
  - `on_item_changed()` now preflights the same capability before executing
    `UpdateMetadataCommand`, protecting programmatic item changes.
- validation：
  - focused red + editability:
    `poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_cells_use_backend_update_capability -q`
    -> `1 passed`.
  - Dataset panel / action regression:
    `poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_panel_minimal.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `65 passed`.
  - backend metadata command regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_data_table_service.py tests/unit/backend/application/test_application_service.py::test_metadata_update_command_routes_through_service tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `6 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one dataset table editability alignment, not full Data Interpretation wizard editor or
    dataset table UX acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Visualization saliency settings capability truth

- scope：
  - UI/backend command truth alignment for Visualization sidebar `Saliency Settings` dialog。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `ControlSidebar.set_saliency()` opened `SaliencySettingDialog` before checking backend
    `saliency` capability.
  - Empty real `Study` state could show a settings dialog even though the command layer would
    reject saliency readiness.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_blocked_by_backend_capability -q`
    initially failed because the dialog opened.
- 做了什麼：
  - Added `saliency` capability preflight before opening `SaliencySettingDialog` for real `Study`
    paths.
  - Kept mock / legacy non-Study dialog behavior and controller fallback.
- validation：
  - focused red + dialog gate:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_blocked_by_backend_capability -q`
    -> `1 passed`.
  - Visualization sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_dialogs_extra.py::TestControlSidebar -q`
    -> `11 passed`.
  - backend saliency command regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py::test_visualize_and_saliency_commands_return_typed_query_payloads tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `5 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one saliency settings dialog boundary alignment, not full saliency workflow UX or
    visualization desktop render acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Dataset clear-session capability truth

- scope：
  - UI/backend command truth alignment for Dataset sidebar `Clear Dataset` reset-session action。
  - No command schema, backend handler, MCP, agent tool, or screenshot artifact change.
- problem：
  - `DatasetSidebar.clear_dataset()` always asked for destructive confirmation before executing
    `ResetSessionCommand`.
  - Empty real `Study` state has no state to destroy, and backend `reset_session` capability marks
    confirmation as unnecessary.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_uses_reset_session_capability_before_confirm -q`
    initially failed because `QMessageBox.question()` was called.
- 做了什麼：
  - Added `reset_session` capability preflight and confirmation policy check before clearing.
  - Kept mock / legacy non-Study confirmation and controller fallback.
- validation：
  - focused red + confirmation boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_uses_reset_session_capability_before_confirm -q`
    -> `1 passed`.
  - Dataset sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar tests/unit/ui/dataset/test_panel.py::test_dataset_panel_clear_dataset tests/unit/ui/dataset/test_panel_minimal.py -q`
    -> `10 passed`.
  - backend lifecycle regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_lifecycle_service.py tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes tests/unit/backend/application/test_application_service.py::test_capability_policy_covers_all_declared_commands -q`
    -> `5 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> pass.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one reset-session confirmation boundary alignment, not full reset / new-session human
    desktop acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Data Interpretation recipe-save capability truth

- scope：
  - UI/backend command truth alignment for Data Interpretation recipe save prompts。
  - No backend command schema, agent tool, MCP tool, or screenshot artifact change.
- problem：
  - `_save_interpretation_recipe()` opened the file-save dialog before consulting backend
    `save_interpretation_recipe` capability.
  - Label import recipe trace updates could ask the user whether to save a recipe even when backend
    capability said recipe saving was blocked.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_save_interpretation_recipe_uses_backend_capability_before_file_dialog tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_offer_label_recipe_save_skips_confirmation_when_save_blocked -q`
    initially failed because the file dialog / save confirmation path remained reachable.
- 做了什麼：
  - Added a shared `save_interpretation_recipe` capability preflight before file-save dialog
    creation.
  - Skipped the label-import save confirmation when backend save capability is blocked, keeping the
    message scoped to session recipe trace.
  - Kept mock / legacy non-Study file dialog and command fallback behavior.
- validation：
  - focused red + capability boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_save_interpretation_recipe_uses_backend_capability_before_file_dialog tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_offer_label_recipe_save_skips_confirmation_when_save_blocked -q`
    -> red before implementation, then `2 passed`.
  - recipe save regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_saves_recipe_when_requested tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe -q`
    -> `2 passed`.
  - Dataset action regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `58 passed`.
  - backend recipe regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply -q`
    -> `3 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `102 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one recipe save confirmation-boundary cleanup, not full import wizard recipe UX
    acceptance.
  - It does not prove Windows human desktop click-through or complete remaining mutating-path
    audit.

### 2026-05-05 Training data-splitting capability truth

- scope：
  - Backend capability policy and Training sidebar command truth for dataset generation /
    clear-datasets boundaries。
  - No agent tool schema, MCP tool schema, Data Interpretation wizard, or screenshot artifact
    change.
- problem：
  - `TrainingSidebar.split_data()` used controller-local loaded/epoch/training checks before opening
    `DataSplittingDialog`, so a real `Study` path could open the dialog when backend
    `generate_dataset` capability was blocked.
  - Backend `clear_datasets` capability did not block while training was reported running.
- red test：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_generate_dataset_blocks_while_training_is_running tests/unit/backend/application/test_application_service.py::test_clear_datasets_blocks_while_training_is_running -q`
    initially failed because generate reached validation and clear succeeded.
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_uses_backend_generate_capability_before_dialog tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_allows_backend_replacement_boundary -q`
    initially failed because the dialog opened on a backend-blocked real `Study` state.
- 做了什麼：
  - Added backend capability blockers for `generate_dataset` and `clear_datasets` while training is
    running.
  - Added Training sidebar `generate_dataset` capability preflight before opening the splitting
    dialog.
  - Preserved the existing replacement boundary: if the only generate blocker is existing active
    datasets/trainer and backend `clear_datasets` is enabled, UI may still ask for destructive
    confirmation and run clear-then-generate.
  - Kept mock / legacy non-Study controller-local compatibility.
- validation：
  - focused backend red + policy boundary:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_generate_dataset_blocks_while_training_is_running tests/unit/backend/application/test_application_service.py::test_clear_datasets_blocks_while_training_is_running -q`
    -> red before implementation, then `2 passed`.
  - focused UI red + replacement boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_uses_backend_generate_capability_before_dialog tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_allows_backend_replacement_boundary -q`
    -> red before implementation, then `2 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
    -> `28 passed`.
  - backend dataset-generation regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_generate_dataset_blocks_when_dataset_already_exists tests/unit/backend/application/test_application_service.py::test_generate_dataset_blocks_while_training_is_running tests/unit/backend/application/test_application_service.py::test_clear_datasets_blocks_while_training_is_running tests/unit/backend/application/test_application_service.py::test_clear_datasets_and_training_history_commands_route_cleanup -q`
    -> `4 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one data-splitting capability boundary cleanup, not full training workflow human
    acceptance.
  - It does not prove long-running training resource cleanup, Windows launcher click-through, or
    complete UI-observable walkthrough coverage.

### 2026-05-05 Dataset Smart Parse source-of-truth cleanup

- scope：
  - UI command truth alignment for Dataset Smart Parse dialog gating。
  - No backend command schema, agent tool, MCP tool, or screenshot artifact change.
- problem：
  - `DatasetActionHandler.open_smart_parser()` first read backend `apply_smart_parse`
    capability, but after capability passed it still used controller-local `is_locked()` /
    `has_data()` checks before opening `SmartParserDialog`.
  - A stale controller state could therefore block a real `Study` path even when backend capability
    said Smart Parse was available.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_prefers_backend_capability_over_stale_controller -q`
    initially failed because the dialog did not open.
- 做了什麼：
  - Limited controller-local locked / has-data checks to mock / legacy non-Study paths.
  - Kept real `Study` blocked behavior on backend `apply_smart_parse` capability.
  - Kept controller fallback execution only when `execute_application_command()` returns `None`.
- validation：
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_prefers_backend_capability_over_stale_controller -q`
    -> red before implementation, then passed.
  - Smart Parse regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_prefers_backend_capability_over_stale_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_uses_backend_capability tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_success -q`
    -> `3 passed`.
  - Dataset action regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `59 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one Smart Parse source-of-truth cleanup, not full metadata editor or Data Interpretation
    wizard UX acceptance.
  - It does not prove Windows human desktop click-through or complete UI-observable walkthrough
    coverage.

### 2026-05-05 Dataset Channel Selection source-of-truth cleanup

- scope：
  - UI command truth alignment for Dataset sidebar Channel Selection dialog gating。
  - No backend command schema, agent tool, MCP tool, or screenshot artifact change.
- problem：
  - `DatasetSidebar.open_channel_selection()` first read backend `preprocess` capability, but after
    capability passed it still used controller-local `has_data()` / `is_locked()` checks before the
    confirmation and `ChannelSelectionDialog`.
  - A stale controller state could block a real `Study` path even when backend capability said
    preprocessing was available.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_prefers_backend_capability_over_stale_controller -q`
    initially failed because the channel-selection dialog did not open.
- 做了什麼：
  - Limited controller-local data / locked checks to mock / legacy non-Study paths.
  - Kept real `Study` blocked behavior on backend `preprocess` capability.
  - Kept controller fallback execution only when `execute_application_command()` returns `None`.
- validation：
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_prefers_backend_capability_over_stale_controller -q`
    -> red before implementation, then passed.
  - Channel Selection regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_uses_backend_preprocess_capability tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_accepted -q`
    -> `3 passed`.
  - Dataset sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
    -> `8 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one Channel Selection source-of-truth cleanup, not full preprocessing UX or Data
    Interpretation wizard acceptance.
  - It does not prove Windows human desktop click-through or complete UI-observable walkthrough
    coverage.

### 2026-05-05 Data Interpretation source-entry source-of-truth cleanup

- scope：
  - UI command truth alignment for main file import and folder/BIDS source import entry gates。
  - No backend command schema, agent tool, MCP tool, or screenshot artifact change.
- problem：
  - `DatasetActionHandler.import_data()` and `_can_start_interpretation()` first read backend
    capability, but after capability passed they still used controller-local `is_locked()` before
    opening file/folder source dialogs.
  - A stale controller lock state could block a real `Study` Data Interpretation source entry even
    when backend `scan_source` capability was available.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_prefers_backend_scan_capability_over_stale_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_folder_prefers_backend_scan_capability_over_stale_controller -q`
    initially failed because neither source dialog opened.
- 做了什麼：
  - Limited controller-local locked checks to mock / legacy non-Study paths for file and
    folder/BIDS Data Interpretation entry.
  - Kept real `Study` blocked behavior on backend Data Interpretation capability / apply policy.
  - Kept legacy file import fallback only when Data Interpretation and `LoadDataCommand` do not
    handle the source.
- validation：
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_prefers_backend_scan_capability_over_stale_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_folder_prefers_backend_scan_capability_over_stale_controller -q`
    -> red before implementation, then passed.
  - source entry regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_prefers_backend_scan_capability_over_stale_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_folder_prefers_backend_scan_capability_over_stale_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_locked tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_folder_source_uses_folder_or_bids_root -q`
    -> `4 passed`.
  - Dataset action regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `61 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one source-entry gate cleanup, not full Data Interpretation wizard UX or human desktop
    import acceptance.
  - It does not prove Windows human desktop click-through or complete UI-observable walkthrough
    coverage.

### 2026-05-05 Preprocess helper source-of-truth cleanup

- scope：
  - UI command truth alignment for shared Preprocess sidebar helper gates。
  - No backend command schema, agent tool, MCP tool, or screenshot artifact change.
- problem：
  - `PreprocessSidebar.check_lock()` and `check_data_loaded()` first read backend `preprocess`
    capability, but after capability passed they still used controller-local `is_epoched()` /
    `has_data()` checks.
  - Stale controller state could therefore block real `Study` preprocessing actions even when
    backend capability said preprocessing was available.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_lock_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_data_loaded_prefers_backend_capability_over_stale_controller -q`
    initially failed because both helper methods returned blocked.
- 做了什麼：
  - Limited controller-local epoched / has-data checks to mock / legacy non-Study paths.
  - Kept real `Study` blocked behavior on backend `preprocess` capability.
  - Preserved legacy warning behavior for non-Study fallback tests.
- validation：
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_lock_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_data_loaded_prefers_backend_capability_over_stale_controller -q`
    -> red before implementation, then passed.
  - Preprocess helper regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_lock_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_data_loaded_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_lock_locked tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_data_loaded_false -q`
    -> `4 passed`.
  - Preprocess sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
    -> `17 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one Preprocess helper gate cleanup, not full preprocessing workflow UI acceptance.
  - It does not prove signal/thread lifecycle cleanup or complete UI-observable walkthrough coverage.

### 2026-05-05 Dataset sidebar visible capability truth

- scope：
  - UI visible state alignment for Dataset sidebar source-entry and Smart Parse buttons。
  - No backend command schema, agent tool, MCP tool, or screenshot artifact change.
- problem：
  - `DatasetSidebar.update_sidebar()` still used controller-local `is_locked()` to set main import,
    folder import, recipe reload, and Smart Parse tooltip text.
  - Smart Parse stayed enabled on an empty real `Study` even though backend `apply_smart_parse`
    capability was blocked.
- red test：
  - `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_uses_backend_smart_parse_capability tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_lock -q`
    initially failed because Smart Parse was enabled and source tooltips showed stale locked text.
- 做了什麼：
  - Added live `scan_source`, `reload_interpretation_recipe`, and `apply_smart_parse` capability
    reads for Dataset sidebar visible button state.
  - Kept legacy controller-local tooltip behavior only when backend capabilities are unavailable.
- validation：
  - focused red + visible state boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_uses_backend_smart_parse_capability tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_lock -q`
    -> red before implementation, then passed.
  - Dataset sidebar capability regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_uses_backend_smart_parse_capability tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_lock tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_uses_backend_import_label_capability -q`
    -> `3 passed`.
  - Dataset sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
    -> `10 passed`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This is one visible-state cleanup, not full Dataset page visual design pass.
  - It does not prove UI-observable walkthrough screenshots or human desktop acceptance.

### 2026-05-05 Dataset sidebar replay artifact refresh

- scope：
  - UI-observable Data Interpretation replay evidence for Dataset sidebar visible button states。
  - No product code behavior change beyond replay helper artifact coverage.
- problem：
  - The previous Data Interpretation replay JSON only preserved import-label button state. It did
    not directly evidence the source-entry / recipe reload / Smart Parse visible-state capability
    cleanup.
- 做了什麼：
  - Added reusable `button_state()` and `dataset_sidebar_state()` helpers to
    `scripts/dev/capture_data_interpretation_replay.py`.
  - Replay JSON now records all Dataset sidebar button text / enabled / tooltip states for both
    empty and applied dataset phases.
  - Refreshed `artifacts/ui/data-interpretation-replay.json`.
- validation：
  - helper unit test:
    `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `2 passed`.
  - replay + Dataset sidebar regression:
    `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
    -> `12 passed`.
  - replay artifact:
    `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- evidence：
  - empty `smart_parse`: enabled `false`, tooltip `Load raw data before applying smart parse.`
  - applied `smart_parse`: enabled `true`, tooltip `Auto-extract Subject/Session from filenames`
  - source / folder / recipe buttons record backend-aligned visible state in
    `artifacts/ui/data-interpretation-replay.json`.
- 不能宣稱：
  - This is replay evidence for Dataset sidebar visible state, not full human desktop acceptance or
    full Data Interpretation wizard visual redesign.

### 2026-05-05 Recipe reload remap selector and table-fill polish

- scope：
  - Data Interpretation recipe reload UI for missing saved label/event carrier remap。
  - Dataset table / Data Interpretation preview table fit and color semantics。
  - Replay artifact evidence for remap dialog and applied Dataset table layout。
- problem：
  - Backend remap existed, but the wizard still dead-ended at a blocked reload dialog when a saved
    label/event carrier was missing and a replacement was available in the current scan.
  - The remap dialog showed contradictory blocked copy while enabling `Apply Remap`.
  - Dataset table could fill the panel by stretching the wrong column, squeezing filenames, and
    external labels were colored green like a success state.
- red / focused tests：
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_table_columns_fill_available_width tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_tables_fit_product_layout tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_label_carrier_remap -q`
    initially failed on header fill policy, green label color, wizard table policy, and remap copy.
- 做了什麼：
  - `data_interpretation_review.py` now includes `label_carrier_remap_options` in recipe reload
    preview summaries when a saved carrier is missing but current carriers are available.
  - `DataInterpretationPreviewDialog` shows a `Remap label carrier` selector in `Review Summary`,
    enables `Apply Remap`, returns `choices.label_carrier_remap`, and uses remap-specific user copy.
  - `DatasetActionHandler.reload_interpretation_recipe()` merges dialog remap choices into the saved
    recipe choices, then re-runs preview / validate before apply.
  - Dataset table columns remain interactive; resize handling allocates extra width to `File` so the
    main panel is filled without squeezing filenames.
  - External labels now use neutral text (`Labels (n)`) instead of green success coloring.
  - Replay JSON now records table `stretch_last_section`, `header_length`, `viewport_width`, and
    `column_widths`.
- validation：
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_table_columns_fill_available_width tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_tables_fit_product_layout tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_label_carrier_remap tests/unit/scripts/test_capture_data_interpretation_replay.py::test_table_state_records_rows_and_resize_modes -q`
    -> `5 passed`.
  - `timeout 300s env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_repreviews_blocked_label_carrier_remap -q`
    -> `29 passed`.
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/panel.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py tests/unit/scripts/test_capture_data_interpretation_replay.py`
    -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/panel.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - `git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `108 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `6 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
- evidence：
  - `artifacts/ui/data-interpretation-remap.png` shows the replacement selector, remap-specific copy,
    and `Apply Remap`.
  - `artifacts/ui/data-interpretation-applied.png` shows the Dataset table filling the main panel,
    filename readability preserved, and neutral `Events (6)` / `Labels (4)` text.
  - `artifacts/ui/data-interpretation-replay.json` records `header_length == viewport_width` and
    column widths `[492, 84, 112, 56, 64, 74, 112]` in the applied capture.
- 不能宣稱：
  - This is the simple renamed label/event carrier remap path, not a full recipe conflict editor or
    complex anchor reconciliation UX.
  - This is automated PyQt replay evidence, not human Windows desktop acceptance.

### 2026-05-05 Recipe reload EEG file remap selector

- scope：
  - Data Interpretation recipe reload conflict handling for saved EEG files renamed or replaced in
    the current scan。
  - Same wizard review surface as label-carrier remap; no new legacy import path.
- problem：
  - Saved selected EEG files missing from rescan were correctly blocked, but there was no explicit
    replacement path. Users could resolve a renamed label carrier, but not a renamed EEG file.
  - A recipe with both missing EEG file and missing label carrier needed visible selectors for both
    conflicts before `Apply Remap`.
- red / focused tests：
  - Focused backend/UI tests initially failed because `eeg_file_remap` did not clear selected-file
    blockers, review summaries had no `eeg_file_remap_options`, and blocked dialogs did not enable
    remap.
- 做了什麼：
  - `build_interpretation_candidate()` now normalizes `eeg_file_remap`, remaps selected EEG files,
    remaps saved metadata overrides onto the replacement file, and writes
    `choices:eeg_file_remap` to recipe trace.
  - `build_interpretation_preview()` now exposes `eeg_file_remap_options` next to
    `label_carrier_remap_options`.
  - `DataInterpretationPreviewDialog` now has `Remap EEG file` selector rows, requires every remap
    row to have a selected replacement before enabling `Apply Remap`, and returns
    `choices.eeg_file_remap`.
  - Dataset recipe reload action already merged arbitrary dialog choices, so EEG remap follows the
    same re-preview / re-validate path as label carrier remap.
  - Replay artifact now shows both EEG file and label carrier replacement selectors in
    `artifacts/ui/data-interpretation-remap.png`.
- validation：
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py::test_build_interpretation_candidate_remaps_saved_selected_eeg_file_choices tests/unit/backend/application/test_data_interpretation_review.py::test_build_interpretation_preview_summarizes_recipe_reload_diff tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_eeg_file_remap tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_eeg_file_remap tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_repreviews_blocked_eeg_file_remap -q`
    -> red before implementation, then `5 passed`.
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_review.py tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_eeg_file_remap tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_label_carrier_remap tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_eeg_file_remap tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_requires_each_remap_choice tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_label_carrier_remap tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_repreviews_blocked_eeg_file_remap tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_repreviews_blocked_label_carrier_remap -q`
    -> `16 passed`.
  - `poetry run ruff check ...` on touched backend/UI/script/test files -> pass.
  - `poetry run basedpyright ...` on touched product files -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - `git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `109 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
- evidence：
  - `artifacts/ui/data-interpretation-remap.png` shows `Remap EEG file`, `Remap label carrier`, and
    enabled `Apply Remap`.
  - `artifacts/ui/data-interpretation-replay.json` records both remap choices in
    `ui_state.remap_dialog.remap_choices`.
- 不能宣稱：
  - This is simple explicit file replacement, not automatic source-tree rename detection or
    multi-file matching heuristics.
  - This is not full recipe conflict editing, anchor reconciliation, or Windows human desktop
    acceptance.

### 2026-05-05 Agent/headless recipe remap schema truth

- scope：
  - Align Data Interpretation recipe reload remap with agent tool schema, headless automation schema,
    MCP tool specs, local tool-call prompt, normalizer, and deterministic eval.
  - No UI layout or backend apply behavior change in this slice.
- problem：
  - Backend/UI could handle `eeg_file_remap` / `label_carrier_remap`, but the agent/headless schema
    still treated `preview_interpretation.choices` as the older narrow metadata/label shape.
  - Without schema/eval coverage, assistant/MCP clients could miss the remap path or fall back to
    legacy `load_data` / `attach_labels` thinking.
- red / focused tests：
  - New focused tests initially failed because preview choices lacked `metadata_overrides`,
    `label_carrier_choices`, `eeg_file_remap`, and `label_carrier_remap`; automation/MCP command
    schema exposed `choices` as an unstructured object; verifier rejected remap mappings; normalizer
    left remap fields outside `choices`; deterministic eval failed the new remap cases.
- 做了什麼：
  - Added `data_interpretation_choice_schema.py` as the shared schema for
    `PreviewInterpretationCommand.choices`.
  - `BasePreviewInterpretationTool.parameters`, `command_specs()`, and `mcp_tool_specs()` now expose
    the same remap / label-carrier / metadata choices contract.
  - `normalize_tool_call()` now moves top-level remap fields into `choices` and extracts explicit
    "remap saved EEG file X to Y" / "remap label carrier X to Y" text into
    `choices.eeg_file_remap` / `choices.label_carrier_remap`.
  - Intent inference and deterministic/local eval prompts now treat recipe remap as
    `preview_interpretation`; missing saved/replacement pair asks clarification instead of guessing.
  - Deterministic eval cases increased to `121`, adding recipe reload EEG-file remap,
    label-carrier remap, and missing remap target.
- validation：
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py::TestDataInterpretationDefinitions::test_preview_choices_are_structured_for_labels_and_metadata tests/unit/backend/application/test_automation.py::test_preview_command_spec_exposes_recipe_remap_choices tests/unit/backend/application/test_automation.py::test_mcp_tool_specs_use_same_command_schema tests/unit/llm/agent/test_verification_layer.py::TestToolSchemaValidator::test_preview_choice_schema_accepts_recipe_remap_mappings tests/unit/llm/agent/test_tool_call_normalizer.py::test_moves_preview_recipe_remap_fields_into_choices tests/unit/llm/agent/test_tool_call_normalizer.py::test_extracts_recipe_eeg_remap_from_latest_preview_text tests/unit/llm/agent/test_tool_call_normalizer.py::test_extracts_recipe_label_carrier_remap_from_latest_preview_text tests/integration/agent/test_tool_call_eval.py::test_deterministic_tool_call_eval_passes_and_writes_artifacts tests/unit/scripts/test_run_local_tool_call_eval.py::test_prompt_includes_recipe_remap_choices_for_preview tests/unit/scripts/test_run_local_tool_call_eval.py::test_scores_recipe_eeg_file_remap_tool_call tests/unit/scripts/test_run_local_tool_call_eval.py::test_scores_recipe_remap_missing_target_as_clarification -q`
    -> red first, then `11 passed`.
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --repeat-count 3 --output-dir artifacts/agent_evals`
    -> wrote `artifacts/agent_evals/latest.json` / `.md`, deterministic `121 / 121`.
  - `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
    -> refreshed `artifacts/agent_evals/dashboard.md`; dashboard now shows deterministic `121`
    beside local `118` and warns that local models need rerun for new cases.
  - `poetry run ruff check XBrainLab/backend/application/automation.py XBrainLab/backend/application/data_interpretation_choice_schema.py XBrainLab/llm/agent/intent.py XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/definitions/dataset_def.py scripts/agent/evals/run_tool_call_eval.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/llm/tools/test_definitions.py tests/unit/backend/application/test_automation.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/integration/agent/test_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/backend/application/automation.py XBrainLab/backend/application/data_interpretation_choice_schema.py XBrainLab/llm/agent/intent.py XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/definitions/dataset_def.py scripts/agent/evals/run_tool_call_eval.py scripts/agent/evals/run_local_tool_call_eval.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/backend/application/test_automation.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `277 passed`.
  - `git diff --check`
    -> pass.
  - `timeout 300s poetry run ruff check .`
    -> pass.
  - `timeout 300s poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `110 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `477 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
- evidence：
  - `artifacts/agent_evals/latest.md` shows total cases `121`, pass `121`, recipe_reload family
    `3 / 3`.
  - `artifacts/agent_evals/dashboard.md` shows `recipe_reload` only in deterministic results and
    blocks a local thesis claim for the new cases until primary / fallback rerun.
- 不能宣稱：
  - Primary / fallback local LLM x3 have not yet been rerun on the remap-expanded `121` cases; the
    previous local artifact remains `118 / 118`.
  - This does not complete full recipe conflict editing, automatic rename matching, anchor
    reconciliation, or human desktop acceptance.

### 2026-05-05 Dataset / Data Interpretation table-fit polish

- scope：
  - Address UI review feedback that Dataset table columns visually shrink away from the main panel
    after data load, and that Data Interpretation preview/remap tables overflow or look too
    high-contrast.
  - No backend workflow, agent schema, or model-eval behavior change in this slice.
- problem：
  - Dataset table kept interactive columns but only assigned spare width to one column and allowed
    narrow viewport overflow.
  - Data Interpretation `QTreeWidget` tables were configured with fixed widths before final Qt
    layout, so the screenshot could show table headers ending early with unused panel space.
  - Review Summary row alternation could read as harsh striping in the dark theme.
- red / focused tests：
  - Added failing Dataset tests for wide and narrow panels requiring `header.length()` to match the
    table viewport while columns remain `Interactive`.
  - Added failing Data Interpretation dialog tests requiring file / label carrier / event /
    review trees to fill the viewport and avoid horizontal scroll at narrow width.
  - Kept a semantic assertion that `Events (n)` / `Labels (n)` are not success-green status
    indicators.
- 做了什麼：
  - Dataset table now scales all columns proportionally against the actual viewport, with a minimum
    column width floor and exact pixel distribution via shared `ui.table_sizing`.
  - Data Interpretation dialog now records base widths for each tree, uses interactive resize modes
    for every column, recomputes widths against the visible viewport, and runs a show-time refit
    after Qt layout completes.
  - Review Summary now uses explicit dark theme palette colors and lower-contrast alternating rows.
  - Refreshed `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-remap.png`,
    `artifacts/ui/data-interpretation-applied.png`, and
    `artifacts/ui/data-interpretation-replay.json`.
- validation：
  - Focused red tests failed first on old fixed-width behavior, then passed.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_table_sizing.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `29 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `3 passed`.
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> failed once with the existing WSLg / Wayland maximized-state protocol error.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; screenshots were manually reviewed for nonblank content, table fill, reduced
    striping, and no green event/label success color.
- evidence：
  - `artifacts/ui/data-interpretation-replay.json` records Dataset table
    `header_length=994`, `viewport_width=994`, resize modes all `Interactive`, and column widths
    `[321, 113, 150, 75, 86, 99, 150]`.
  - `artifacts/ui/data-interpretation-applied.png` shows the loaded Dataset table filling the
    left panel through the `Events` column.
  - `artifacts/ui/data-interpretation-preview.png` and
    `artifacts/ui/data-interpretation-remap.png` show metadata, label/event, and Review Summary
    headers filling their containers without horizontal overflow.
- 不能宣稱：
  - This is automated PyQt / Xvfb UI-observable evidence, not Windows Desktop human acceptance,
    dual-monitor / DPI acceptance, or complete import-wizard redesign.

### 2026-05-05 19:12 UI refresh bridge helper cleanup

- scope：
  - 收斂 UI observer refresh wiring 的重複寫法，作為 `UI Command Refresh Coordinator +
    Controller Fallback Audit` follow-up 的小保存點。
  - 同步 reviewer finding 到 current truth / now / roadmap：backend command spine 已大幅改善，
    但 UI refresh 仍是 mixed model，Data Interpretation 仍是 baseline wizard，不是 mature final
    import system。
- problem：
  - 前一個 observer refresh cleanup 已把 simple `event -> update_panel()` 改成
    `refresh_from_observer()`，但各 panel 仍重複 `_create_bridge(..., self.refresh_from_observer)`。
  - 這不會造成 product bug，但讓後續 audit 較容易回退成 panel-local refresh pattern。
- red / focused tests：
  - 新增 `BasePanel._create_refresh_bridge()` focused test，實作前會因 helper 不存在而失敗。
- 做了什麼：
  - 新增 `BasePanel._create_refresh_bridge(controller, event)`，統一委派到
    `_create_bridge(controller, event, self.refresh_from_observer)`。
  - Dataset / Preprocess / Training / Evaluation / Visualization panel 的 simple refresh bridges
    改用 `_create_refresh_bridge()`。
  - 保留 import-finished、training start/stop/config/history 和 live update loop 等 named callback
    handlers。
  - 更新 UI architecture、current truth、now、roadmap 和 implementation log，明確記錄 command
    spine 仍是 partially aligned，後續仍需 command-driven refresh coordinator 和 controller
    fallback audit。
- validation：
  - `poetry run pytest --capture=sys tests/unit/ui/core/test_base_panel.py::TestCreateBridge::test_create_refresh_bridge_uses_observer_refresh tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/test_refresh_coordinator.py -q`
    -> `20 passed`.
  - `poetry run ruff check XBrainLab/ui/core/base_panel.py XBrainLab/ui/panels/dataset/panel.py XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/training/panel.py XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/core/test_base_panel.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/core/base_panel.py XBrainLab/ui/panels/dataset/panel.py XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/training/panel.py XBrainLab/ui/panels/evaluation/panel.py XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/core/test_base_panel.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run mkdocs build --strict`
    -> pass with the existing MkDocs Material 2.0 advisory banner.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `930 passed`.
- 不能宣稱：
  - 這不是 full command-driven UI refresh closure。
  - 這不改變 Data Interpretation wizard maturity、Windows human desktop acceptance 或 local LLM
    eval claim。

### 2026-05-05 19:20 UI downstream analysis refresh scope

- scope：
  - Narrow `UI Command Refresh Coordinator + Controller Fallback Audit` slice。
  - 把 training / epoch / evaluation state changes 對 Evaluation / Visualization readiness 的刷新
    明確放進 `refresh_after_command()`。
- problem：
  - 前一版 coordinator 只在 `training_changed` 時刷新 Training panel，只在
    `evaluation_changed` / `visualization_changed` 時刷新對應 analysis panel。
  - Evaluation / Visualization panel 的 readiness 其實也取決於 training plan/history、epoch
    availability 和 evaluation result state；若只靠 controller observer 補刷新，command result
    scope 還是不完整。
- red / focused tests：
  - 新增 tests 要求：
    - `training_changed=True` refresh Training + Evaluation + Visualization。
    - `epoch_changed=True` refresh Preprocess + Training + Visualization。
    - `evaluation_changed=True` refresh Evaluation + Visualization。
  - 實作前三個測試都在 expected downstream panel call count 上 fail。
- 做了什麼：
  - 更新 `XBrainLab.ui.refresh_coordinator._panel_names_for()`：
    - `training_changed` 現在也刷新 `evaluation_panel` / `visualization_panel`。
    - `epoch_changed` / `preprocessed_changed` 現在會刷新 `visualization_panel` readiness。
    - `evaluation_changed` 現在也刷新 `visualization_panel` readiness。
  - 更新 current truth、UI architecture、now、roadmap 和 implementation log，保守標成 partial
    command-driven refresh improvement。
- validation：
  - `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py -q`
    -> `10 passed`.
  - `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_application_capabilities.py -q`
    -> `15 passed`.
  - `poetry run ruff check XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `git diff --check`
    -> pass.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `933 passed`.
- 不能宣稱：
  - 這不是 full command-driven UI refresh closure。
  - 這不移除 callback-specific observer handlers，也不證明 full train -> evaluate ->
    visualization desktop acceptance。

### 2026-05-05 19:26 UI observer refresh helper guard

- scope：
  - Tighten the static architecture guard after introducing `BasePanel._create_refresh_bridge()`。
  - No runtime UI behavior change in this slice.
- problem：
  - Previous guard blocked `_create_bridge(..., self.update_panel)` but still allowed future panels
    to duplicate `_create_bridge(..., self.refresh_from_observer)` directly.
  - That would bypass the helper boundary and make the observer refresh pattern harder to audit.
- red / focused tests：
  - Changed the architecture compliance unit test so direct
    `_create_bridge(..., self.refresh_from_observer)` must fail and `_create_refresh_bridge(...)`
    must pass.
  - The direct-refresh test failed before implementation with `len(violations) == 0`.
- 做了什麼：
  - `check_ui_observer_direct_update_bridges()` now also flags direct
    `_create_bridge(..., refresh_from_observer)` outside `base_panel.py`.
  - Violation text now tells future contributors to use `_create_refresh_bridge()` for simple
    observer refresh or a named callback handler for event-specific behavior.
  - Updated current truth, UI architecture, now, roadmap, and implementation log.
- validation：
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `8 passed`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> pass.
  - `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `git diff --check`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - 這不是 full command-driven UI refresh closure。

### 2026-05-05 19:32 UI legacy missing-result refresh guard

- scope：
  - Tighten post-command local refresh architecture compliance.
  - No runtime UI behavior change in this slice.
- problem：
  - The previous post-command guard correctly blocked service-success local refresh, but it skipped
    every failure / missing-result branch.
  - That meant a future mock / legacy compatibility branch could add `if result is None:
    self.update_panel()` directly instead of using the explicit legacy-result helper pattern.
- red / focused tests：
  - Added an architecture compliance unit test requiring direct local refresh inside
    `if result is None:` to fail.
  - The test failed before implementation with `len(violations) == 0`.
- 做了什麼：
  - Split `result.failed` and `result is None` handling in
    `check_ui_post_command_local_refreshes()`.
  - Failure branches may still skip the post-command local-refresh violation so UI can restore
    rejected edits or warning state.
  - Missing-result compatibility branches now get scanned unless they live inside an
    `*_after_legacy_result` helper.
  - Updated current truth, UI architecture, now, roadmap, and implementation log.
- validation：
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `9 passed`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> pass.
  - `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `git diff --check`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - 這不是 full controller fallback removal or UI refresh closure。

### 2026-05-05 19:35 Validation doc sync for UI refresh guard slices

- scope：
  - Documentation consistency after the latest UI refresh coordinator / fallback guard commits.
  - No runtime code change in this slice.
- 做了什麼：
  - Added a concise `docs/validation/README.md` entry mapping the recent downstream refresh scope,
    observer helper guard, and missing-result legacy refresh guard to concrete tests and claim
    boundaries.
  - Kept the claim conservative: stronger command-result refresh guardrails, not full
    command-driven UI refresh or human Windows acceptance.
- validation：
  - `git diff --check`
    -> pass.
  - `poetry run mkdocs build --strict`
    -> pass with existing MkDocs Material warning.
- 不能宣稱：
  - This docs sync is not product completion and adds no new runtime evidence.

### 2026-05-05 19:40 Data Interpretation event display polish

- scope：
  - Data Interpretation preview dialog visible text polish.
  - Preserve backend choice keys and recipe payload shape.
- problem：
  - Latest screenshot review showed the Event table exposing internal-looking `label_carrier` as
    visible first-layer text.
  - The label/event group title still said `Labels, Events, and Recipe Trace`, although recipe trace
    is now reviewed in the structured `Review Summary`.
- red / focused tests：
  - Added a UI test requiring visible event role names to show `Label carrier` / `Trial type` while
    `get_result()["choices"]["event_roles"]` keeps backend keys such as `label_carrier`.
  - Added a UI test assertion requiring the group title `Label and Event Interpretation`.
  - Both assertions failed before implementation.
  - Extended replay helper test then failed because it still searched the visible row by raw
    `trial_type` after the UI was humanized.
- 做了什麼：
  - Humanized event-role item text with `_event_role_display_name()`, while storing the original
    key in `_event_role_items`.
  - Added source-key tooltip for event-role rows.
  - Updated replay helper matching to use that source-field tooltip, so replay can operate the
    visible `Trial type` row while preserving backend `trial_type` choices.
  - Renamed the group title to `Label and Event Interpretation`.
  - Refreshed Data Interpretation replay artifacts.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `31 passed`.
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; refreshed `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-remap.png`, and
    `artifacts/ui/data-interpretation-replay.json`.
  - `git diff --check` -> pass.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
- evidence：
  - Screenshot review of `artifacts/ui/data-interpretation-preview.png` shows `Label carrier`,
    `Onset`, `Duration`, and `Trial type` rows, not visible `label_carrier`.
  - Replay JSON `dialog.event_rows` records `Label carrier`; backend payload still keeps
    `label_carrier` where it belongs.
  - Replay JSON `review_choices.event_roles.trial_type` is `class cue`, confirming the replay still
    changes the backend event-role choice through the humanized row.
- 不能宣稱：
  - This is UI-visible wording polish, not full mature import wizard editor, raw trigger selector,
    or Windows human desktop acceptance.

### 2026-05-05 19:52 Data Interpretation decision copy polish

- scope：
  - Data Interpretation preview dialog top-level decision copy.
  - Keep backend decision keys unchanged.
- problem：
  - The top status line still exposed backend-oriented wording such as
    `Validation needs confirmation before applying.`
  - Recipe remap blockers also used validation/remap language as the first user-facing instruction.
- red / focused tests：
  - Added decision-copy assertions requiring `Review and confirm these choices before applying.`,
    `Ready to apply.`, and a generic blocked message without raw `safe`.
  - Focused test first failed because the dialog still rendered `Validation needs confirmation`.
  - Full dialog suite then exposed two remaining remap-copy assertions still tied to old
    `label carrier remap` / `EEG file remap` wording.
- 做了什麼：
  - Replaced decision label copy with user-facing workflow instructions.
  - Updated remap-specific top status to ask for replacement EEG or label/event carrier files.
  - Refreshed Data Interpretation replay artifacts.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `18 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `21 passed`.
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; refreshed `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-remap.png`, and
    `artifacts/ui/data-interpretation-replay.json`.
- evidence：
  - Screenshot review of `artifacts/ui/data-interpretation-preview.png` shows
    `Review and confirm these choices before applying.`
  - Replay JSON `visible_text` contains the same copy and no `Validation needs` match.
- 不能宣稱：
  - This improves one visible status line; it is not full wizard UX completion, Windows human
    acceptance, or full blocked-state redesign.

### 2026-05-05 20:00 Dataset legacy loader boundary

- scope：
  - Dataset panel legacy raw-loader helper.
  - UI fallback study detection and architecture guard.
- problem：
  - `DatasetPanel.apply_loader()` still directly called `loader.apply(self.controller.study, ...)`
    from UI code.
  - `run_legacy_controller_fallback()` only detected `study` via widget/main-window context, so a
    panel constructed with a real controller but no main-window parent could incorrectly look like a
    legacy context.
- red / focused tests：
  - Added architecture guard tests requiring direct UI `loader.apply(...study...)` to fail outside
    legacy adapter functions.
  - Added UI capability test requiring `run_legacy_controller_fallback()` to refuse a real
    `controller.study` context; it failed before implementation.
- 做了什麼：
  - `find_study()` now checks `controller.study`.
  - `DatasetPanel.apply_loader()` now delegates to `_apply_legacy_loader()` through
    `run_legacy_controller_fallback()`.
  - Real `Study` runtime gets a user-facing warning to use Data Interpretation workflow instead of
    mutating through the raw loader.
  - Added `check_ui_direct_loader_apply()` to architecture compliance.
- validation：
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `11 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_application_capabilities.py -q`
    -> `6 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py -q`
    -> `12 passed`.
  - Combined focused regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_application_capabilities.py tests/unit/test_architecture_compliance.py -q`
    -> `29 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - Focused `ruff check` -> pass.
  - Focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`; baseline reduced by one existing
    optional-member entry for `DatasetPanel`.
- evidence：
  - `test_dataset_panel_apply_loader_refuses_real_study` asserts real runtime does not call
    `loader.apply()` and shows `Interpret Data Source` guidance.
  - Architecture compliance unit test asserts non-legacy UI `loader.apply(self.controller.study)`
    is rejected.
- 不能宣稱：
  - This closes one legacy raw-loader mutation bypass. It does not finish the full controller
    fallback audit, command-driven UI refresh coordinator, or human desktop acceptance.

### 2026-05-05 20:03 Human-like walkthrough artifact refresh

- scope：
  - Refresh consolidated automated UI-observable human-like walkthrough after Data Interpretation
    visible-copy and event-row polish.
- 做了什麼：
  - Ran `scripts/dev/capture_human_like_product_walkthrough.py` with the current UI.
  - Refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`,
    `human-like-walkthrough.md`, and changed screenshots.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`.
  - Artifact summary remains status `passed`, `26 / 26` required phases, `20` screenshots,
    `human_desktop_acceptance=not performed`.
  - Resource smoke remains `passed=True`; RSS growth `231876 KB` / limit `600000 KB`, Qt active
    thread `0`.
- evidence：
  - `human-like-walkthrough.json` visible text now contains
    `Review and confirm these choices before applying.`
  - Screenshot review of `04-interpretation-preview.png` shows the updated decision copy and no
    visible raw `label_carrier` / `trial_type` event-row names.
  - Screenshot review of `20-eval-dashboard.png` is nonblank and still shows the tool-call dashboard
    artifact.
- 不能宣稱：
  - This is automated PyQt replay evidence only. It does not replace Windows launcher /
    dual-monitor / DPI human acceptance, long local-model desktop session, or leak-proof soak.

### 2026-05-05 20:06 UI unit regression after fallback boundary

- scope：
  - Broad UI unit regression after `find_study()` started detecting `controller.study` and
    `DatasetPanel.apply_loader()` became legacy-only.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `937 passed in 107.57s`.
- evidence：
  - This covers the wider UI helper/panel unit suite beyond the focused fallback tests.
- 不能宣稱：
  - This is still automated unit regression, not human desktop acceptance or full command-driven UI
    refresh closure.

### 2026-05-05 20:12 ChatPanel composer placeholder polish

- scope：
  - ChatPanel bottom composer placeholder in docked / narrow panel screenshots.
- problem：
  - `12-assistant-empty.png` showed the old placeholder truncated as `Ask about data, prepro...`.
- red / focused tests：
  - Added a ChatPanel unit test requiring the composer placeholder to be
    `Ask about EEG workflow`, max length `24`, and no long `preprocessing, epoching` list.
  - The test failed before implementation against the old long placeholder.
  - Integration product walkthrough test then failed because it still expected the old
    `Ask about data` placeholder.
- 做了什麼：
  - Replaced the long placeholder with `Ask about EEG workflow`.
  - Refreshed the consolidated human-like walkthrough artifact.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py -q`
    -> `41 passed`.
  - `poetry run ruff check XBrainLab/ui/chat/panel.py tests/unit/ui/chat/test_chat_panel.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/chat/panel.py tests/unit/ui/chat/test_chat_panel.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`; refreshed consolidated screenshots and JSON/Markdown.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `55 passed`.
  - focused `ruff check` including `tests/integration/ui/test_product_walkthrough.py` -> pass.
  - focused `basedpyright` including `tests/integration/ui/test_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`.
- evidence：
  - `12-assistant-empty.png` and `17-assistant-narrow.png` now show the full
    `Ask about EEG workflow` placeholder.
  - Walkthrough JSON records `Ask about EEG workflow` in visible text and no old
    `Ask about data, prepro` match.
- 不能宣稱：
  - This is narrow composer polish only; it is not a complete ChatPanel product design pass,
    Windows human acceptance, or long local-model session verification.

### 2026-05-05 20:18 Reviewer architecture finding truth sync

- scope：
  - Preserve latest backend / UI refresh reviewer finding after the placeholder slice reached a
    commit boundary.
- 做了什麼：
  - Updated `docs/current.md`, `docs/planning/now.md`, `docs/planning/roadmap.md`, and
    `docs/records/implementation_log.md`.
  - Kept the finding as follow-up TODO rather than interrupting current validation/local eval
    closure.
- current truth：
  - Backend command spine is substantially improved but still only partially aligned with target.
  - UI refresh remains mixed: command-result coordinator baseline plus observer/manual/tab-switch /
    callback paths.
  - Product runtime mutating workflows must not silently fall back to controller mutation; remaining
    fallback is only acceptable as explicit mock / unit-test compatibility or isolated legacy
    adapter.
  - Data Interpretation remains a strengthened baseline wizard, not a mature final import system.
- 不能宣稱：
  - This documentation sync does not close the `UI Command Refresh Coordinator + Controller Fallback
    Audit` milestone, full controller fallback removal, mature import wizard, or human desktop
    acceptance.

### 2026-05-05 20:31 Navigation shared-status refresh coordinator slice

- scope：
  - Tab-switch refresh inside `XBrainLab.ui.refresh_coordinator`.
- current gap：
  - `MainWindow.switch_page()` delegated panel mapping to `refresh_after_navigation()`, but
    navigation only refreshed the selected workflow panel. Aggregate info panel and assistant
    backend status still depended on other refresh paths.
- red / focused test：
  - Updated `tests/unit/ui/test_refresh_coordinator.py` to require
    `refresh_after_navigation()` to refresh the selected panel plus aggregate info and assistant
    backend status.
  - Red result:
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py -q`
    -> `1 failed, 9 passed`; `info.update_calls == 0` before implementation.
- 做了什麼：
  - `refresh_after_navigation()` now calls `refresh_panel(selected_panel)`,
    `main_window.update_info_panel()`, and `agent_manager.refresh_backend_status()` through the
    same safe no-arg call boundary used by command refresh.
  - Updated UI architecture/current/now/validation/records docs.
- validation：
  - `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py -q`
    -> `10 passed`.
  - `poetry run ruff check XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_main_window_sync.py -q`
    -> `19 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is a small tab-switch shared-status cleanup. It does not close full command-driven UI
    refresh, controller fallback removal, observer callback classification, or human desktop
    acceptance.

### 2026-05-05 20:43 Dataset import-finished duplicate refresh cleanup

- scope：
  - Legacy Dataset controller import callback behavior.
- current gap：
  - `DatasetController.import_files()` emits `data_changed` on successful import, then emits
    `import_finished(success_count, errors)`.
  - `DatasetPanel` already refreshes from `data_changed`, but
    `DatasetActionHandler.on_import_finished()` also called `panel.update_panel()` when
    `success_count > 0`, causing a duplicate manual refresh on the legacy import path.
- red / focused test：
  - Updated `test_on_import_finished_success` to require no `panel.update_panel()` call and no
    warning on success-only completion.
  - Red result:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_on_import_finished_success -q`
    -> failed because `update_panel()` was called once.
- 做了什麼：
  - Removed success refresh from `DatasetActionHandler.on_import_finished()`.
  - Updated the docstring to state that successful legacy imports already emit `data_changed`, and
    that observer event owns panel refresh.
  - Kept error warning behavior unchanged.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_on_import_finished_success tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_on_import_finished_errors tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_on_import_finished_many_errors -q`
    -> `3 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `65 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is one observer callback cleanup. It does not remove controller observer events, close the
    full UI refresh coordinator audit, or replace human desktop acceptance.

### 2026-05-05 20:56 Observer shared-status refresh coordinator slice

- scope：
  - Simple observer refresh path through `BasePanel._create_refresh_bridge()`.
- current gap：
  - Simple observer refresh had been centralized to `BasePanel.refresh_from_observer()` but that
    method delegated only to `refresh_panel(self)`.
  - Backend observer events could refresh a panel while aggregate info panel and assistant backend
    status waited for another refresh path.
- red / focused test：
  - Added `refresh_after_observer` expectations in `tests/unit/ui/test_refresh_coordinator.py` and
    changed `BasePanel.refresh_from_observer()` delegation test to require the new coordinator path.
  - Red result:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py::test_refresh_from_observer_delegates_to_coordinator -q`
    -> import error because `refresh_after_observer` did not exist yet.
- 做了什麼：
  - Added `refresh_after_observer(context)` to `XBrainLab.ui.refresh_coordinator`.
  - Added `_refresh_shared_status(main_window)` and reused it from command, navigation, and observer
    refresh paths.
  - Updated `BasePanel.refresh_from_observer()` to call `refresh_after_observer(self)`.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py::test_refresh_from_observer_delegates_to_coordinator -q`
    -> `12 passed`.
  - `poetry run ruff check XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/core/base_panel.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/core/base_panel.py tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py tests/unit/ui/test_panel_event_bridges.py -q`
    -> `32 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is simple observer shared-status cleanup only. Callback-specific observer handlers,
    command-only refresh closure, full controller fallback removal, and human desktop acceptance
    remain open.

### 2026-05-05 21:08 Dataset import observer deduplication

- scope：
  - PreprocessPanel / TrainingPanel subscriptions to DatasetController events.
- current gap：
  - `DatasetController.import_files()` emits `data_changed` on success and then emits
    `import_finished(success_count, errors)`.
  - PreprocessPanel and TrainingPanel listened to both as simple refresh events, so one successful
    legacy import refreshed each panel twice.
- red / focused test：
  - Updated panel event bridge tests to model a successful legacy import as
    `data_changed` followed by `import_finished(1, [])`, and require one refresh.
  - Red result:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_panel_event_bridges.py::test_preprocess_panel_refreshes_once_for_successful_dataset_import tests/unit/ui/test_panel_event_bridges.py::test_training_panel_refreshes_once_for_successful_dataset_import -q`
    -> `2 failed`; both panels refreshed twice.
- 做了什麼：
  - Removed dataset `import_finished` simple refresh bridges from PreprocessPanel and TrainingPanel.
  - Kept dataset `data_changed` simple refresh bridges, which are the source of truth for successful
    legacy import state changes.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_panel_event_bridges.py::test_preprocess_panel_refreshes_once_for_successful_dataset_import tests/unit/ui/test_panel_event_bridges.py::test_training_panel_refreshes_once_for_successful_dataset_import -q`
    -> `2 passed`.
  - `poetry run ruff check XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/training/panel.py tests/unit/ui/test_panel_event_bridges.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/training/panel.py tests/unit/ui/test_panel_event_bridges.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_panel_event_bridges.py -q`
    -> `12 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This removes one duplicate observer refresh path. It does not classify all callback-specific
    observer handlers, remove controller observers, or complete UI command-refresh closure.

### 2026-05-05 21:20 InfoPanelService import refresh deduplication

- scope：
  - Aggregate info panel refresh subscriptions in `InfoPanelService`.
- current gap：
  - `InfoPanelService` subscribed to dataset `data_changed`, preprocess `preprocess_changed`, and
    dataset `import_finished`.
  - Successful legacy dataset import emits `data_changed` followed by `import_finished`, so aggregate
    info panels were updated twice for one successful import.
- red / focused test：
  - Added a Study-like observer stub test that registers a panel, emits `data_changed`, then
    `import_finished(1, [])`, and requires one `update_info()` call.
  - Red result:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_info_panel_service.py::test_successful_legacy_import_updates_info_once -q`
    -> failed because `update_info()` was called twice.
- 做了什麼：
  - Removed the dataset `import_finished` bridge from `InfoPanelService`.
  - Kept aggregate info refresh on dataset `data_changed` and preprocess `preprocess_changed`.
  - Kept Dataset action callback as the owner of import warning presentation.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_info_panel_service.py -q`
    -> `4 passed`.
  - `poetry run ruff check XBrainLab/ui/components/info_panel_service.py tests/unit/ui/components/test_info_panel_service.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/components/info_panel_service.py tests/unit/ui/components/test_info_panel_service.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - Corrected integration smoke path after a wrong node-id attempt:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration/ui/test_e2e_qtbot.py::TestInfoService -q`
    -> `2 passed`.
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is one aggregate info observer deduplication. It does not close all observer callbacks,
    product runtime fallback audit, or human desktop acceptance.

### 2026-05-05 21:31 Import-finished observer refresh guard

- scope：
  - Static architecture guard for the duplicate `import_finished` refresh pattern.
- current gap：
  - Dataset / Preprocess / Training / InfoPanelService duplicate refresh paths were cleaned up, but
    architecture compliance did not prevent a future simple refresh bridge from reintroducing
    `import_finished` as another success refresh source.
- red / focused tests：
  - Added tests requiring `check_ui_observer_direct_update_bridges()` to fail:
    `_create_refresh_bridge(self.controller, "import_finished")`
    and direct `QtObserverBridge(..., "import_finished", ...)`.
  - Red result:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_flags_import_finished_simple_refresh tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_flags_direct_import_finished_bridge -q`
    -> `2 failed`; no violations were reported.
- 做了什麼：
  - Added `_observer_bridge_uses_import_finished_simple_refresh()` and `_call_has_string_arg()` to
    `tests/architecture_compliance.py`.
  - The guard now reports that successful import state refresh is owned by `data_changed`, and that
    `import_finished` should use a named callback handler for warnings / event-specific behavior.
  - Named callback handlers such as DatasetPanel `on_import_finished` remain allowed.
- validation：
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_flags_import_finished_simple_refresh tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_flags_direct_import_finished_bridge tests/unit/test_architecture_compliance.py::test_observer_bridge_guard_allows_callback_handlers -q`
    -> `3 passed`.
  - `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> pass.
  - `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `13 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is a regression guard for one duplicate observer pattern. It does not close the full UI
    refresh coordinator audit, remove controller observer events, or complete product acceptance.

### 2026-05-05 Training high-level event shared-status refresh

- scope：
  - `TrainingPanel` high-level observer callbacks:
    `training_started`, `config_changed`, `training_stopped`, and `history_cleared`.
- current gap：
  - TrainingPanel callback-specific handlers updated the training UI, sidebar, log, or history but
    did not refresh aggregate info panel or assistant backend status in pure controller-event paths.
  - Simple observer refresh was already coordinator-backed, but these callback-specific events were
    intentionally outside the simple bridge.
- red / focused test：
  - Added
    `tests/unit/ui/training/test_training_panel.py::test_training_panel_high_level_events_refresh_shared_status`.
  - Red result before implementation:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py::test_training_panel_high_level_events_refresh_shared_status -q`
    -> failed because `XBrainLab.ui.panels.training.panel.refresh_shared_status` did not exist.
- 做了什麼：
  - Added `refresh_shared_status(context)` to `XBrainLab.ui.refresh_coordinator`, with the same
    main-window re-entrancy guard used by command and observer refresh.
  - Called `refresh_shared_status(self)` after TrainingPanel `config_changed`, `training_started`,
    `training_stopped`, and `history_cleared` handlers finish their event-specific UI updates.
  - Left high-frequency `training_updated` on the live training update loop.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py::test_training_panel_high_level_events_refresh_shared_status -q`
    -> `1 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py -q`
    -> `17 passed`.
  - `poetry run ruff check XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py XBrainLab/ui/panels/training/panel.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `git diff --check` -> pass.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is one callback-specific observer cleanup. It does not make UI refresh fully
    command-driven, remove controller observer events, complete controller fallback audit, or
    replace Windows human desktop acceptance.

### 2026-05-05 Navigation refresh re-entrancy guard

- scope：
  - `XBrainLab.ui.refresh_coordinator.refresh_after_navigation()`.
- current gap：
  - Command, observer, and shared-status refresh had same-main-window re-entrancy guards.
  - Navigation refresh refreshed the selected panel and shared status but did not guard nested
    refresh for the same main window.
- red / focused test：
  - Added
    `tests/unit/ui/test_refresh_coordinator.py::test_navigation_refresh_is_not_reentrant_for_same_main_window`.
  - Red result:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_navigation_refresh_is_not_reentrant_for_same_main_window -q`
    -> failed because the selected panel was refreshed twice during a nested navigation refresh.
- 做了什麼：
  - Added the `_REFRESHING_MAIN_WINDOWS` guard to `refresh_after_navigation()`.
  - Kept the existing selected-panel refresh plus aggregate info / assistant backend status refresh
    behavior for the outer navigation call.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_navigation_refresh_is_not_reentrant_for_same_main_window -q`
    -> `1 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_main_window_sync.py -q`
    -> `21 passed`.
  - `poetry run ruff check XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
- 不能宣稱：
  - This is one refresh coordinator hardening slice. It does not close full command-driven UI
    refresh, controller fallback audit, Data Interpretation wizard maturity, or human desktop
    acceptance.

### 2026-05-05 Agent mapped-tool ApplicationService boundary

- scope：
  - `LLMController._execute_tool_no_loop()` mapped workflow tool execution.
- current gap：
  - `execute_application_tool_command()` returned `None` when it could not build an
    ApplicationService command from tool params.
  - For real `Study` contexts, `LLMController` treated that `None` as permission to call the legacy
    real tool. This let a capability-enabled but malformed mapped tool bypass the command layer.
- red / focused test：
  - Reworked
    `tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_mapped_tool_missing_params_does_not_use_legacy_tool`.
  - Red result:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_mapped_tool_missing_params_does_not_use_legacy_tool -q`
    -> failed with `runtime` because the legacy tool was executed and raised the test AssertionError.
- 做了什麼：
  - If a real `Study` mapped workflow tool is capability-readable but cannot produce an
    ApplicationService command, `execute_application_tool_command()` now returns
    `ToolCommandResult.failure(...)` with `error_type=input`.
  - Explicit UI-request tools such as `set_montage` remain on the UI confirmation request path.
  - Mock / legacy non-Study paths still fall through to legacy tool execution for compatibility.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_mapped_tool_missing_params_does_not_use_legacy_tool -q`
    -> `1 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `184 passed`.
  - `poetry run ruff check XBrainLab/llm/agent/controller.py tests/unit/llm/agent/test_controller.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/llm/agent/controller.py tests/unit/llm/agent/test_controller.py`
    -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This hardens runtime safety for mapped tools. The local benchmark rerun is recorded in the
    release gate entry below; neither slice proves long autonomous ChatPanel operation or complete
    agent product acceptance.

### 2026-05-05 Local tool-call release gate and eval layering

- scope：
  - Refresh formal local tool-call benchmark artifacts after mapped-tool command boundary hardening.
  - Record the new eval gate policy so future small slices do not automatically trigger full
    primary / fallback x3 local eval.
- 做了什麼：
  - Deterministic artifact was already refreshed at
    `artifacts/agent_evals/latest.json` / `.md`, `121 / 121`.
  - Primary full x3 completed with `microsoft/Phi-4-mini-instruct`, `121 / 121`. It initially wrote
    to `artifacts/agent_evals/` root; the generated artifact was moved into
    `artifacts/agent_evals/local_primary/` and path metadata was corrected without rerunning.
  - Fallback full x3 completed with `microsoft/Phi-3.5-mini-instruct`, `121 / 121`, written to
    `artifacts/agent_evals/local_fallback/`.
  - Dashboard refreshed:
    `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`.
  - Added resource pressure artifact:
    `artifacts/agent_evals/local-eval-resource-pressure-2026-05-05.md` / `.json`.
- resource notes：
  - During fallback x3, RTX 5070 Ti showed `15764 MiB` used, `232 MiB` free, GPU util `99%`,
    process elapsed `38:40`, RSS `2330376 KB`.
  - Approximate fallback wall time was about `41 min`.
  - This is a high-pressure release / thesis gate on 16GB VRAM, not a default dev gate.
- gate policy：
  - Fast dev gate：deterministic eval, changed / failed cases only, repeat `1`, no fallback model.
  - Candidate gate：primary model, affected case families, repeat `1` or `2`.
  - Release / thesis gate：deterministic full suite, primary full x3, fallback full x3, dashboard
    refresh, resource pressure recorded.
- 不能宣稱：
  - This supports the saved `121` case tool-call benchmark slice only.
  - It does not prove human desktop acceptance, mature import wizard UX, MCP HTTP / long-running
    jobs, or long autonomous ChatPanel workflow.

### 2026-05-05 UI direct controller mutation guard

- scope：
  - Static architecture guard for product UI controller mutation bypasses outside explicit legacy
    fallback paths.
- current gap：
  - Existing guard caught controller mutation only in `result is None` fallback branches.
  - A future UI action could still call `controller.update_metadata()` or
    `self.controller.start_training()` directly outside that exact branch shape.
- red / focused tests：
  - Added tests requiring direct `controller.update_metadata(...)` and
    `self.controller.start_training()` to fail.
  - Added allow tests for `run_legacy_controller_fallback(...)`, named fallback helper functions,
    and non-controller UI methods such as `history_table.clear_history()`.
- 做了什麼：
  - Added `check_ui_direct_controller_mutations()` to `tests/architecture_compliance.py`.
  - The guard flags calls whose receiver is `controller` or `self.controller` and whose method is in
    the mutating controller fallback method list.
  - Explicit `run_legacy_controller_fallback()` calls and function names containing `legacy` or
    `fallback` remain allowed.
- validation：
  - `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `18 passed`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> pass.
  - `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
    -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This is a guardrail only. It does not complete full command-driven UI refresh, remove
    controller observer bridges, or replace human desktop acceptance.

### 2026-05-05 Data Interpretation replay table geometry evidence

- scope：
  - Strengthen UI-observable evidence for the user-reported Dataset table / Data Interpretation
    preview table fit issues.
  - No backend workflow or local LLM change.
- current gap：
  - `artifacts/ui/data-interpretation-replay.json` recorded Dataset table geometry, but preview and
    remap dialog trees only recorded visible rows.
  - That meant label/event/review table overflow had to be judged mostly from screenshots.
- red / focused test：
  - Added `test_tree_state_records_rows_and_fit_geometry`, requiring a Data Interpretation
    `QTreeWidget` state payload to include rows, interactive resize modes, no stretch-last-section,
    `header_length == viewport_width`, `horizontal_scrollbar_max == 0`, elide mode, and alternating
    row state.
- 做了什麼：
  - Added `tree_state()` to `scripts/dev/capture_data_interpretation_replay.py`.
  - Preview and remap dialog states now include table geometry for metadata, label carriers, event
    roles, and Review Summary.
  - Refreshed `artifacts/ui/data-interpretation-replay.json` and screenshots through the offscreen
    replay script.
- evidence：
  - Preview/remap dialog metadata, label carriers, events, and review summary all record
    `horizontal_scrollbar_max=0`.
  - Review Summary example: `header_length=972`, `viewport_width=972`, `column_widths=[179, 173, 620]`,
    `text_elide_mode=ElideRight`.
  - Dataset table remains `header_length=994`, `viewport_width=994`, `column_widths=[321, 113, 150, 75, 86, 99, 150]`.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py::test_tree_state_records_rows_and_fit_geometry -q`
    -> `1 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py -q`
    -> `34 passed`.
  - `poetry run ruff check scripts/dev/capture_data_interpretation_replay.py tests/unit/scripts/test_capture_data_interpretation_replay.py`
    -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py tests/unit/scripts/test_capture_data_interpretation_replay.py`
    -> `0 errors, 0 warnings, 0 notes`.
- 不能宣稱：
  - This strengthens automated UI artifact evidence only. It is not mature import wizard completion
    or human desktop acceptance.

### 2026-05-05 Human-like walkthrough table geometry gate

- scope：
  - Fold Dataset / Data Interpretation table geometry evidence into the consolidated human-like
    product walkthrough.
  - Fix the loaded Dataset table overflow caught by the new geometry gate.
  - No local LLM eval was run; this was a UI/evidence fast-dev slice.
- red / focused tests：
  - Added a test requiring `build_observable_evidence_summary()` to index per-phase
    `ui_geometry`.
  - Added a test requiring `build_ui_quality_review()` to fail an overflowing table/tree geometry
    row.
  - Added a DatasetPanel regression test for loaded rows settling without horizontal scrollbar.
  - Added a test ensuring UI quality failure blocks the walkthrough status, not only the validator.
- 做了什麼：
  - `scripts/dev/capture_human_like_product_walkthrough.py` now records `ui_geometry` notes for
    Dataset table, Data Interpretation preview / confirm / reload trees, and summarizes them under
    `observable_evidence.ui_geometry_snapshots`.
  - UI quality review now reports `table_geometry_review` with checked widgets, findings, width gap,
    header / viewport values, horizontal scrollbar state, resize modes, and column widths.
  - The walkthrough pass/fail summary now fails when automated UI quality fails.
  - `DatasetPanel` now refits table columns after Qt row-header / scrollbar geometry settles, and
    uses the full viewport without leaving a horizontal scrollbar.
  - `table_state()` now records horizontal scrollbar and elide-mode fields for table artifacts.
- refreshed artifacts：
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - Human-like walkthrough:
    `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md`.
  - Data Interpretation replay:
    `artifacts/ui/data-interpretation-replay.json`,
    `artifacts/ui/data-interpretation-applied.png`.
- evidence：
  - Human-like walkthrough status `passed`, `26 / 26` phases, `20` screenshots.
  - Human-like table geometry review checked `15` widgets with `0` findings.
  - Loaded Dataset table after apply: `header_length=509`, `viewport_width=510`,
    `horizontal_scrollbar_max=0`.
  - Data Interpretation replay Dataset table: `header_length=993`, `viewport_width=994`,
    `horizontal_scrollbar_max=0`.
- validation：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_table_sizing.py -q`
    -> `34 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
- 不能宣稱：
  - This proves automated PyQt replay geometry for the saved synthetic walkthrough, not human
    Windows desktop acceptance, dual-monitor / DPI, long local-model desktop sessions, or final
    Data Interpretation wizard completion.

### 2026-05-05 Observer event-scope refresh coordinator

- scope：
  - Move known backend observer events closer to the command-result refresh model.
  - Avoid repeated full panel refresh when multiple panels subscribe to the same observer event.
  - No local LLM eval was run; this was a UI architecture fast-dev slice.
- current gap：
  - `BasePanel._create_refresh_bridge()` centralized simple observer wiring, but
    `refresh_after_observer()` still refreshed only the panel that received the bridge.
  - Because Dataset / Preprocess / Training / Evaluation / Visualization can all subscribe to
    lifecycle events, making every bridge refresh downstream panels would duplicate work.
- red / focused tests：
  - Added tests requiring `data_changed` to refresh Dataset / Preprocess / Training through the
    coordinator when the DatasetPanel owner bridge receives it.
  - Added tests requiring `preprocess_changed` to refresh Preprocess / Training / Visualization
    through the coordinator when the PreprocessPanel owner bridge receives it.
  - Added secondary-subscriber tests requiring other subscribers of the same events to no-op instead
    of duplicating the central refresh.
  - Updated `BasePanel.refresh_from_observer()` tests so observer event names are passed to the
    coordinator.
  - Added training lifecycle tests requiring TrainingPanel owner callbacks to route
    `training_started` / `training_stopped` / `config_changed` / `history_cleared` through the same
    coordinator scope and secondary Evaluation / Visualization subscribers to no-op in full
    MainWindow context.
- 做了什麼：
  - `refresh_after_observer(context, event_name=...)` now routes known events via
    `ChangedState`-style panel scopes.
  - `BasePanel._create_refresh_bridge()` now wraps the observer callback and passes its event name
    into `refresh_from_observer()`.
  - TrainingPanel high-level callbacks now call `refresh_after_observer()` with their lifecycle event
    name after completing their event-specific UI update.
  - Unknown observer events still refresh the source panel plus shared status.
- validation：
  - `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/training/test_training_panel.py tests/unit/ui/test_main_window_sync.py -q`
    -> `66 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run mkdocs build --strict`
    -> pass with the existing MkDocs Material 2.0 advisory banner.
- 不能宣稱：
  - This is not full command-driven UI refresh closure. It does not remove controller observers,
    replace event-specific TrainingPanel callbacks, or complete human desktop acceptance.

### 2026-05-05 Local eval CLI resource preflight guard

- scope：
  - Prevent routine agent/tool verifier or UI slices from accidentally starting full primary /
    fallback x3 local eval under RTX 5070 Ti 16GB VRAM pressure.
  - Keep user-requested eval layering executable in code, not only in docs.
- red / focused tests：
  - Added tests that a fallback repeat-`3` full-suite gate under `232 MiB` free VRAM is blocked.
  - Added tests that the same high-pressure VRAM state still allows a changed-case repeat-`1`
    gate.
  - Added CLI test requiring `resource_preflight.json` to be written and local eval not to start
    when the full fallback gate is blocked.
- 做了什麼：
  - `scripts/agent/evals/run_local_tool_call_eval.py` now performs local eval resource preflight
    before `LLMEngine` startup.
  - Preflight records selected case count, gate type, model role, repeat count, cache usage,
    available disk, estimated model VRAM, and first `nvidia-smi` GPU memory row.
  - If repeat `3` full local eval sees high VRAM pressure, the CLI writes `resource_preflight.json`
    / `.md` and returns exit code `2`.
  - Successful local eval results now carry `resource_preflight` metadata into JSON / Markdown
    artifacts.
- validation：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py::test_resource_preflight_blocks_full_local_gate_under_vram_pressure tests/unit/scripts/test_run_local_tool_call_eval.py::test_resource_preflight_allows_changed_case_gate_under_vram_pressure tests/unit/scripts/test_run_local_tool_call_eval.py::test_cli_writes_preflight_artifact_and_aborts_full_fallback -q`
    -> `3 passed`.
  - `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py -q`
    -> `37 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run mkdocs build --strict`
    -> pass with the existing MkDocs Material 2.0 advisory banner.
- 不能宣稱：
  - This does not rerun local eval or update thesis benchmark scores. It only guards the local eval
    CLI from unsafe/default full-gate usage under high resource pressure.

### 2026-05-05 Legacy fallback refusal product language

- scope：
  - Keep controller fallback refusal as a product-runtime safety boundary, but stop surfacing raw
    internal wording if a real `Study` path ever reaches a mock/legacy fallback branch.
  - No local LLM eval was run; this is UI architecture/product-language hardening.
- red / focused tests：
  - Updated fallback refusal tests to require `could not safely complete` product wording.
  - Added assertion that the Preprocess reset error dialog does not show `refusing controller
    fallback` or `ApplicationService`.
- 做了什麼：
  - `run_legacy_controller_fallback()` now raises `LegacyControllerFallbackUnavailableError` with a
    user-facing safety message.
  - DatasetPanel legacy loader handling catches the dedicated exception type instead of string
    matching internal fallback text.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_application_capabilities.py::test_legacy_controller_fallback_refuses_real_study tests/unit/ui/test_application_capabilities.py::test_legacy_controller_fallback_refuses_real_controller_study tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_refuses_real_study_controller_fallback tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_refuses_real_study_controller_fallback tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_refuses_real_study_controller_fallback tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback tests/unit/ui/dataset/test_panel.py::test_dataset_panel_apply_loader_refuses_real_study -q`
    -> `8 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_application_capabilities.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_sidebars_and_components.py tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_ui_misc.py tests/unit/ui/test_agent_manager_coverage.py -q`
    -> `240 passed`.
  - `git diff --check`
    -> pass.
  - `poetry run ruff check .`
    -> pass.
  - `poetry run basedpyright`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - `poetry run mkdocs build --strict`
    -> pass with the existing MkDocs Material 2.0 advisory banner.
- 不能宣稱：
  - This does not remove legacy/mock fallback paths. It only keeps the refusal boundary user-facing
    if an impossible product fallback path is forced in tests or a runtime bug.

### 2026-05-05 Dataset sidebar neutral channel-selection action

- scope：
  - Address the screenshot-review concern that loaded Dataset view still had misleading green UI.
  - This slice specifically handles `Channel Selection`; `Events` / `Labels` semantic coloring was
    already muted in the table.
- red / focused test：
  - Added `test_channel_selection_uses_neutral_action_style`, which failed while
    `chan_select_btn` used `Stylesheets.BTN_SUCCESS`.
- 做了什麼：
  - Changed `DatasetSidebar.chan_select_btn` to use `Stylesheets.SIDEBAR_BTN`.
  - Kept button enablement and capability tooltip behavior unchanged.
- UI observable artifact：
  - First `xvfb-run` attempt failed in the environment with a Wayland protocol geometry error.
  - `QT_QPA_PLATFORM=xcb` was unavailable because `xcb-cursor0` / `libxcb-cursor0` is missing.
  - Re-ran with `QT_QPA_PLATFORM=offscreen` successfully:
    `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` shows status `passed`,
    `26 / 26` phases, `20` screenshots, UI quality checks passed, and resource smoke passed.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py::test_channel_selection_uses_neutral_action_style -q`
    -> `1 passed`.
- 不能宣稱：
  - This is automated PyQt/offscreen evidence, not Windows human desktop acceptance.
  - This does not close the mature Data Interpretation wizard or broader UI polish backlog.

### 2026-05-05 AgentManager / Visualization montage position normalizer

- scope：
  - Remove a duplicated command-argument truth between Visualization sidebar and AgentManager
    montage confirmation.
  - Keep `ApplyMontageCommand` arguments typed as JSON-safe float tuples before service execution.
- red / focused tests：
  - Added AgentManager real-`Study` test where dialog returns list positions; it failed because
    backend received `[[0, 0, 0], [1, 0, 0]]` instead of float tuples.
  - Added malformed vector test; it exposed that bad UI dialog output could proceed into the command
    path instead of being blocked at the UI adapter boundary.
- 做了什麼：
  - Added `XBrainLab/ui/montage_positions.py::normalize_montage_positions()`.
  - Reused the helper in Visualization `ControlSidebar.set_montage()` and
    `AgentManager.open_montage_picker_dialog()`.
  - AgentManager now shows a concise status-bar message for malformed position vectors and does not
    call ApplicationService in that case.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_normalizes_dialog_position_lists tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_rejects_malformed_position_vectors tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_real_study_uses_application_service -q`
    -> `4 passed`.
- 不能宣稱：
  - This is command argument boundary cleanup. It does not certify interactive desktop 3D rendering
    or the full visualization workflow.

### 2026-05-05 Visualization observer events routed through coordinator

- scope：
  - Continue `UI Command Refresh Coordinator + Controller Fallback Audit` with a narrow observer
    cleanup slice.
  - Route `montage_changed` / `saliency_changed` through the same coordinator owner-scope pattern as
    dataset / preprocess / training events.
- red / focused tests：
  - Added coordinator test where a helper context with `panel=visualization_panel` receives
    `saliency_changed`; it failed because the visualization panel was not refreshed.
  - Added secondary-context test for `montage_changed`; it failed because unknown events refreshed
    the wrong source panel.
  - Added VisualizationPanel bridge tests for `montage_changed` and `saliency_changed`; both failed
    because the panel did not subscribe to its controller events.
- 做了什麼：
  - Added `montage_changed` and `saliency_changed` routes to `refresh_coordinator`.
  - Added VisualizationPanel owner bridges for both visualization controller events.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_visualization_observer_uses_visualization_scope_from_helper_context tests/unit/ui/test_refresh_coordinator.py::test_secondary_visualization_observer_does_not_duplicate_central_scope tests/unit/ui/test_panel_event_bridges.py::test_visualization_panel_refreshes_on_montage_changed tests/unit/ui/test_panel_event_bridges.py::test_visualization_panel_refreshes_on_saliency_changed -q`
    -> `4 passed`.
- 不能宣稱：
  - This is not full command-driven UI refresh closure; high-frequency training live updates and
    remaining manual/event-specific refreshes still need ownership/audit.

### 2026-05-06 MainWindow shared info refresh uses InfoPanelService

- scope：
  - Make the refresh coordinator's shared info refresh real in product MainWindow, not only in
    test doubles.
- red / focused tests：
  - Added `test_update_info_panel_uses_info_service`; it failed because
    `MainWindow.update_info_panel()` only checked `self.info_panel`, while product MainWindow owns
    `self.info_service`.
  - Added legacy fallback coverage for injected contexts without `info_service`.
- 做了什麼：
  - `MainWindow.update_info_panel()` now calls `InfoPanelService.notify_all()` when available.
  - Kept direct `info_panel.update_info()` as a legacy / injected fallback.
- validation：
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_main_window_sync.py::test_update_info_panel_uses_info_service tests/unit/ui/test_main_window_sync.py::test_update_info_panel_keeps_legacy_direct_panel_fallback -q`
    -> `2 passed`.
- 不能宣稱：
  - This does not complete command-driven UI refresh; it fixes one shared status dispatch gap.

### 2026-05-06 Preprocess legacy shared status through coordinator

- scope：
  - Continue `UI Command Refresh Coordinator + Controller Fallback Audit` with a small compatibility
    refresh cleanup.
  - Keep Preprocess service-success paths coordinator-owned while making retained mock / legacy
    epoch-reset shared-status refresh use the same coordinator helper.
- red / focused test：
  - Added `TestPreprocessSidebar.test_open_epoching_legacy_result_refreshes_shared_status`.
  - It failed because the legacy/mock epoching path called `main_window.update_info_panel()` directly
    and did not refresh assistant backend status.
- 做了什麼：
  - Replaced Preprocess sidebar's direct legacy shared-info helper with
    `refresh_shared_status(self)`.
  - Kept local panel refresh limited to explicit legacy/mock `result is None` helper paths; real
    `Study` service-success paths remain handled by `execute_application_command()` /
    `refresh_after_command()`.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_legacy_result_refreshes_shared_status -q`
    -> failed on missing `agent_manager.refresh_backend_status()`.
  - After fix:
    same focused test -> `1 passed`.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_panel_event_bridges.py -q`
    -> `55 passed`.
- 不能宣稱：
  - This does not complete full command-driven UI refresh or remove all callback-specific refresh
    paths.

### 2026-05-06 Data Interpretation selector and review contrast polish

- scope：
  - Address user-visible Data Interpretation preview polish without changing backend recipe values.
  - Keep table geometry / elide behavior, but reduce raw-looking selector text and harsh Review
    Summary striping.
  - Follow-up within the same UI concern: give the label-carrier `Format` column enough product-width
    space for common names such as `BIDS events`.
- red / focused tests：
  - Updated `test_data_interpretation_preview_dialog_tables_fit_product_layout` to require visible
    label-field selector text `Trial type` while preserving `currentData() == "trial_type"`.
  - The test initially failed because the selector still showed raw `trial_type` and the style sheet
    still used `#252525` as the Review Summary alternate background.
- 做了什麼：
  - `DataInterpretationPreviewDialog._text_choices()` now humanizes displayed label / anchor choice
    labels while keeping the raw value as combo data.
  - Lowered `InterpretationReviewSummary` alternate row color from `#252525` to `#232323`.
  - Rebalanced label-carrier table column weights from `(150, 145, 70, 115, 105, 105, 110, 140)` to
    `(145, 145, 110, 115, 105, 100, 105, 157)`, so `Format` has a useful visible width while the
    table still fills the viewport.
  - Updated existing selector tests to interact with visible user-facing combo labels, while still
    asserting raw recipe choices are saved.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_tables_fit_product_layout -q`
    -> failed on missing `#232323` and raw selector display.
  - After fix:
    same focused test -> `1 passed`.
  - Follow-up red/green:
    added a product-width assertion requiring the label-carrier `Format` column to be at least
    `96px`; it failed at `73px` before the column-weight change and passed after the fix.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py::test_dataset_panel_refits_table_after_loaded_rows_settle tests/unit/ui/dataset/test_panel.py::test_dataset_panel_events_column_uses_semantic_text_and_muted_color -q`
    -> `20 passed`.
  - UI replay:
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; refreshed `artifacts/ui/data-interpretation-preview.png`,
    `data-interpretation-remap.png`, `data-interpretation-applied.png`, and
    `data-interpretation-replay.json`.
  - Human-like walkthrough:
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`; `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` shows status
    `passed`, `26 / 26` phases, `20` screenshots, table geometry checked for `15` widgets with
    `0` findings, and resource smoke passed.
- 不能宣稱：
  - This does not close mature Data Interpretation wizard completion, recipe diff UX, complex
    GDF/MAT anchor reconciliation, XDF/LSL parser work, or Windows human desktop acceptance.

### 2026-05-06 Dataset table main-panel fill evidence

- scope：
  - Follow up on the user screenshot where loaded Dataset rows looked like they only filled a narrow
    left block while the main panel still had empty space before the sidebar.
  - Add evidence for the table widget boundary itself, not only `header_length == viewport_width`.
- red / focused tests：
  - Added `test_table_state_records_main_panel_fill_gap`; it failed because `table_state()` did not
    accept `panel` / `right_boundary` and could not record table-to-sidebar gaps.
  - Added `test_build_ui_quality_review_flags_table_gap_to_sidebar`; it failed because the
    human-like walkthrough quality review ignored a `right_gap_to_boundary` underfill even when
    header / viewport geometry looked healthy.
- 做了什麼：
  - `table_state()` now records `widget_width`, `panel_width`, `table_right_x`,
    `right_boundary_x`, and `right_gap_to_boundary` when a panel and sidebar boundary are supplied.
  - The human-like walkthrough UI quality review now marks table geometry as failed when a recorded
    table-to-content-boundary gap exceeds the existing width tolerance.
  - Refreshed UI replay / walkthrough artifacts; `artifacts/ui/data-interpretation-replay.json`
    records `widget_width=1020`, `table_right_x=1020`, `right_boundary_x=1020`, and
    `right_gap_to_boundary=0` for the 1280px loaded Dataset capture.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py::test_table_state_records_main_panel_fill_gap tests/unit/scripts/test_capture_human_like_product_walkthrough.py::test_build_ui_quality_review_flags_table_gap_to_sidebar -q`
    -> failed on missing `table_state(..., panel=..., right_boundary=...)` support and no underfill
    finding.
  - After fix:
    same focused test command -> `2 passed`.
  - UI replay:
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - Human-like walkthrough:
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`; walkthrough status remains `passed`.
- 不能宣稱：
  - This is an automated layout guard and artifact refresh. It does not replace Windows / DPI /
    multi-monitor human desktop acceptance.

### 2026-05-06 UI table / eval-gate handoff

- scope：
  - Preserve current truth for the next runner after the UI table polish / geometry guard slice.
  - Re-state the user's eval layering policy so routine UI/backend changes do not trigger full
    primary/fallback x3 local eval under 16GB VRAM pressure.
- 做了什麼：
  - Added `artifacts/goal/continuation-2026-05-06-ui-table-eval-handoff.md`.
  - The handoff lists latest validated commits, expected protected dirty files, validation already
    run, no-local-eval boundary for this slice, remaining product blockers, and suggested next
    slices.
- 不能宣稱：
  - This is an operational handoff only; it does not advance product completion by itself.

### 2026-05-06 Visualization sidebar montage fallback boundary

- scope：
  - Continue `UI Command Refresh Coordinator + Controller Fallback Audit` with a small
    Visualization sidebar mutating-path cleanup.
  - Remove a silent `Set Montage` no-op when `execute_application_command()` unexpectedly returns
    `None`.
- red / focused tests：
  - Added `test_sidebar_set_montage_legacy_result_uses_controller_fallback`; it failed because the
    `result is None` branch returned before calling `VisualizationController.set_montage()`.
  - Added `test_sidebar_set_montage_refuses_real_study_controller_fallback`; it failed because a
    real `Study` missing-result path did not raise the product-runtime fallback refusal boundary.
- 做了什麼：
  - `ControlSidebar.set_montage()` now wraps the missing-result branch in
    `run_legacy_controller_fallback(self, lambda: self.controller.set_montage(...))`.
  - Mock / legacy contexts retain compatibility behavior and refresh via the existing
    `_on_update_after_legacy_result(result)` helper.
  - Real `Study` contexts cannot silently mutate the controller if the command adapter fails to
    return a `CommandResult`.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_legacy_result_uses_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_refuses_real_study_controller_fallback -q`
    -> failed on no fallback call and no refusal.
  - After fix:
    same focused test command -> `2 passed`.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_panel_event_bridges.py -q`
    -> `46 passed`.
- 不能宣稱：
  - This does not complete full controller fallback removal, command-driven UI refresh closure,
    visualization render acceptance, or human Windows desktop verification.

### 2026-05-06 Dataset import does not bypass Data Interpretation command surface

- scope：
  - Keep file import aligned with the product rule that Data Interpretation is the primary data
    entry path.
  - Preserve legacy direct load only for mock / legacy contexts where no ApplicationService
    command surface is visible.
- red / focused test：
  - Added
    `TestDatasetActionHandler.test_import_data_does_not_bypass_interpretation_when_command_surface_exists`.
  - It failed because `_run_data_interpretation_import()` returning `False` caused
    `import_data()` to call `LoadDataCommand` even when `scan_source` capability existed.
- 做了什麼：
  - `DatasetActionHandler.import_data()` now checks the already-read `scan_source` capability before
    direct-load fallback.
  - If Data Interpretation command-sequence handling returns unavailable in a command-capable path,
    the UI shows `Interpretation unavailable` and does not execute `LoadDataCommand` or
    `controller.import_files`.
  - Mock / legacy import fallback remains unchanged when `scan_source` capability is absent.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_does_not_bypass_interpretation_when_command_surface_exists -q`
    -> failed because `LoadDataCommand` was called.
  - After fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_does_not_bypass_interpretation_when_command_surface_exists tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_service_load_success_does_not_fallback_to_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_success -q`
    -> `3 passed`.
- 不能宣稱：
  - This does not remove direct-load compatibility or complete mature Data Interpretation wizard /
    recipe UX work.

### 2026-05-06 Training model selection command-truth cleanup

- scope：
  - Continue `UI Command Refresh Coordinator + Controller Fallback Audit` on a narrow Training
    sidebar path.
  - Remove the service-success dependency on stale controller echo state after
    `ConfigureTrainingCommand`.
- red / focused test：
  - Added
    `TestTrainingSidebar.test_select_model_service_success_does_not_read_stale_controller`.
  - It failed because `select_model()` still called `TrainingController.get_model_holder()` after
    a successful service command and treated a stale `None` as failure.
- 做了什麼：
  - `TrainingSidebar.select_model()` now stores the selected model name before dispatching
    `ConfigureTrainingCommand`.
  - Service-success path displays success from the command result and selected model holder.
  - Legacy fallback path still reads `controller.get_model_holder()` to verify the old controller
    mutation applied in mock / non-`Study` compatibility contexts.
  - Added an architecture compliance guard that flags service-success reads of
    `controller.get_model_holder()` after `execute_application_command()`, while allowing the
    explicit legacy fallback branch.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_service_success_does_not_read_stale_controller -q`
    -> failed because `get_model_holder()` was called.
  - After fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_service_success_does_not_read_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_accepted -q`
    -> `2 passed`.
  - Architecture guard red gate before checker implementation:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_post_command_controller_echo_guard_flags_service_success_echo tests/unit/test_architecture_compliance.py::test_post_command_controller_echo_guard_allows_legacy_branch -q`
    -> failed with missing `check_ui_post_command_controller_echoes`.
  - After checker implementation:
    same architecture unit command -> `2 passed`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
- local eval：
  - Not run. This is a UI command-truth cleanup, so it stays under the fast dev gate and does not
    justify full primary/fallback x3 local eval.
- 不能宣稱：
  - This does not finish controller fallback removal, command-driven UI refresh closure, or human
    training workflow acceptance.

### 2026-05-06 Continuation handoff refresh after fallback/echo slices

- scope：
  - Keep the continuation artifact current after new validated local commits.
  - Preserve the user's fast / candidate / release eval gate policy so routine UI/backend changes do
    not trigger full primary/fallback x3 local eval under 16GB VRAM pressure.
- 做了什麼：
  - Updated `artifacts/goal/continuation-2026-05-06-ui-table-eval-handoff.md` with latest commits:
    visualization montage fallback boundary, Data Interpretation file-import fallback boundary,
    Training model-selection command truth, and the post-command controller echo architecture guard.
  - Added the focused validation commands already run for those slices.
- local eval：
  - Not run. This is a handoff/current-truth artifact update after UI/architecture slices.
- 不能宣稱：
  - This is continuity documentation only; it does not close product completion blockers.

### 2026-05-06 Training split replacement capability-truth cleanup

- scope：
  - Continue `UI Command Refresh Coordinator + Controller Fallback Audit` on Training data
    splitting.
  - Prevent stale controller state from skipping the destructive replacement confirmation and
    `ClearDatasetsCommand` in real `Study` paths.
- red / focused test：
  - Added
    `TestTrainingSidebar.test_split_data_uses_backend_replacement_boundary_when_controller_stale`.
  - It failed because `split_data()` checked `TrainingController.has_datasets()` /
    `get_trainer()` after the dialog; a stale `False` controller echo skipped
    `QMessageBox.question()` and did not dispatch `ClearDatasetsCommand`.
- 做了什麼：
  - Added `TrainingSidebar._should_clear_datasets_before_split()`.
  - Real `Study` path now uses backend `generate_dataset` / `clear_datasets` capabilities to decide
    whether an existing generated dataset / trainer can be replaced.
  - Mock / legacy path keeps the existing controller reads because no ApplicationService capability
    is available there.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_uses_backend_replacement_boundary_when_controller_stale -q`
    -> failed because the confirmation prompt was not called.
  - After fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_uses_backend_replacement_boundary_when_controller_stale tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_allows_backend_replacement_boundary tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_service_success_does_not_fallback_to_controller -q`
    -> `3 passed`.
- local eval：
  - Not run. This is a Training sidebar capability-truth cleanup and stays under the fast dev gate.
- 不能宣稱：
  - This does not complete full controller fallback removal, command-driven UI refresh closure, or
    human training workflow acceptance.

### 2026-05-06 Start Training capability-truth cleanup

- scope：
  - Continue Training sidebar command-truth cleanup.
  - Prevent stale controller running state from silently blocking an enabled backend `train`
    capability.
- red / focused test：
  - Added
    `TestTrainingSidebar.test_start_training_prefers_backend_capability_over_stale_controller`.
  - It failed because `start_training_ui_action()` returned without calling
    `execute_application_command()` when `TrainingController.is_training()` was stale `True`,
    despite backend `train` capability being enabled.
- 做了什麼：
  - Added `TrainingSidebar._should_start_training()`.
  - Command-capable path now uses backend `train` capability truth for start gating.
  - No-capability mock / legacy path still checks `TrainingController.is_training()`.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_prefers_backend_capability_over_stale_controller -q`
    -> failed because no command was executed.
  - After fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_does_not_fallback_to_controller tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_ui_action -q`
    -> `3 passed`.
- local eval：
  - Not run. This is a Training sidebar capability-truth cleanup and stays under the fast dev gate.
- 不能宣稱：
  - This does not complete long-running training acceptance, resource behavior verification, or
    human desktop click-through.

### 2026-05-06 Capability-gated readiness architecture guard

- scope：
  - Add a static guard for the pre-command stale-controller readiness pattern fixed in recent
    Training sidebar slices.
  - Make Training split legacy readiness checks syntactically explicit.
- red / focused test：
  - Added architecture compliance tests for capability-gated controller readiness.
  - Initial test command failed because `check_ui_capability_gated_controller_readiness` did not
    exist yet.
- 做了什麼：
  - Added `check_ui_capability_gated_controller_readiness()` to `tests/architecture_compliance.py`.
  - The guard flags `controller.is_training()`, `controller.has_datasets()`, and
    `controller.get_trainer()` in functions that use `get_command_capability()`, unless the read is
    under an explicit `capability is None` legacy branch.
  - Rewrote `TrainingSidebar.split_data()` to store `generate_capability` once and make its
    no-capability legacy checks explicit.
  - Rewrote `_should_clear_datasets_before_split()` and `_should_start_training()` so controller
    readiness reads are only inside explicit no-capability branches.
- validation：
  - Red gate before checker implementation:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_controller_gate_after_capability tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_allows_explicit_legacy_none_branch tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_ignores_non_capability_legacy_function -q`
    -> failed with missing checker import.
  - After checker implementation:
    same architecture unit command -> `3 passed`.
  - `poetry run python tests/architecture_compliance.py` initially flagged
    `TrainingSidebar.split_data()` inline capability check; after the explicit `generate_capability`
    cleanup it passed with `Architecture compliant!`.
- local eval：
  - Not run. This is a static architecture guard / Training UI cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete controller fallback removal or prove all controller read paths are gone.

### 2026-05-06 Preprocess epoch capability-truth cleanup

- scope：
  - Fix a Preprocess sidebar command-gating mismatch where `open_epoching()` could be blocked by
    `preprocess` capability despite `create_epoch` being enabled.
- red / focused test：
  - Added
    `TestPreprocessSidebar.test_open_epoching_uses_epoch_capability_not_preprocess_block`.
  - It failed because `open_epoching()` called `check_lock()` after confirming `create_epoch`
    capability was enabled; `check_lock()` showed the `preprocess` blocked reason
    `Load raw data before preprocessing.`
- 做了什麼：
  - `open_epoching()` now uses `create_epoch` capability as the authoritative command gate.
  - `check_lock()` / `check_data_loaded()` remain only for no-capability mock / legacy paths.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_epoch_capability_not_preprocess_block -q`
    -> failed because warning was shown and no command was executed.
  - After fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_epoch_capability_not_preprocess_block tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_accepted tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_legacy_result_refreshes_shared_status -q`
    -> `3 passed`.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess -q`
    -> `61 passed`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` ->
    `23 passed`.
    `poetry run mkdocs build --strict` -> passed.
- local eval：
  - Not run. This is a Preprocess UI command-gate cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete full preprocessing / epoching UI walkthrough or real-data manual
    acceptance.

### 2026-05-06 Training readiness guard extension

- scope：
  - Extend the stale-controller readiness architecture guard to Training readiness echo methods.
  - Keep `TrainingSidebar.check_ready_to_train()` readable as service-capability branch versus
    no-capability legacy branch.
- red / focused test：
  - Added
    `test_capability_readiness_guard_flags_validate_ready_after_capability`.
  - It initially failed because `check_ui_capability_gated_controller_readiness()` did not flag
    `controller.validate_ready()` inside a capability conditional expression.
  - After extending the guard, `poetry run python tests/architecture_compliance.py` flagged
    `TrainingSidebar.check_ready_to_train()` as expected.
- 做了什麼：
  - Added `validate_ready`, `has_model`, and `has_training_option` to the capability-gated
    readiness guard method set.
  - Rewrote `TrainingSidebar.check_ready_to_train()` to read `controller.validate_ready()` only
    inside the explicit `train_capability is None` legacy branch.
- validation：
  - Red gate before guard extension:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_validate_ready_after_capability -q`
    -> failed with `0` violations.
  - After guard extension:
    same architecture unit command -> `1 passed`.
  - Red product guard before UI cleanup:
    `poetry run python tests/architecture_compliance.py` -> flagged
    `XBrainLab/ui/panels/training/sidebar.py:179` for `controller.validate_ready()`.
  - After UI cleanup:
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` ->
    `24 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_panel.py -q`
    -> `50 passed`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run mkdocs build --strict` -> passed.
- local eval：
  - Not run. This is a static architecture guard / Training UI readiness cleanup under the fast dev
    gate.
- 不能宣稱：
  - This does not complete command-driven UI refresh coordinator, full controller read removal, or
    human desktop training acceptance.

### 2026-05-06 Dataset sidebar capability-first render cleanup

- scope：
  - Continue the UI command/capability truth audit in a small Dataset sidebar slice.
  - Prevent real `Study` sidebar rendering from reading stale `DatasetController.is_locked()` /
    `has_data()` before applying backend capability truth.
- red / focused tests：
  - Added `test_capability_readiness_guard_flags_lock_state_after_capability`.
  - It failed because the architecture guard did not flag `controller.is_locked()` after
    `get_command_capability()`.
  - Strengthened
    `TestDatasetSidebar.test_update_sidebar_prefers_backend_capabilities_over_stale_lock` to assert
    `is_locked()` / `has_data()` are not called when backend capabilities are present; it failed
    because `update_sidebar()` called `is_locked()` unconditionally.
- 做了什麼：
  - Added `is_locked` and `has_data` to the capability-gated controller state guard.
  - Rewrote `DatasetSidebar.update_sidebar()` so lock/data controller reads only occur inside
    explicit no-capability legacy branches for source import, recipe reload, channel selection,
    smart parse, and label import controls.
- validation：
  - Red guard before checker extension:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_lock_state_after_capability -q`
    -> failed with `0` violations.
  - Red product test before UI cleanup:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_lock -q`
    -> failed because `controller.is_locked()` was called once.
  - After guard extension:
    `poetry run python tests/architecture_compliance.py` -> flagged
    `XBrainLab/ui/panels/dataset/sidebar.py` for `is_locked()` and `has_data()` reads.
  - After UI cleanup:
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_lock tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_lock_state_after_capability -q`
    -> `2 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar tests/unit/ui/dataset/test_dataset_sidebar.py -q`
    -> `16 passed`.
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` ->
    `25 passed`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run mkdocs build --strict` -> passed.
- local eval：
  - Not run. This is a Dataset sidebar render / architecture guard cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete the UI refresh coordinator, all controller read removal, or human desktop
    Data Interpretation acceptance.

### 2026-05-06 Evaluation panel query display gate

- scope：
  - Continue UI/backend truth alignment for readonly analysis rendering.
  - Prevent a real `Study` Evaluation panel from showing stale injected controller plans when
    ApplicationService says evaluation is blocked / unavailable.
- red / focused test：
  - Added
    `test_evaluation_panel_uses_application_query_before_stale_controller_plans`.
  - It failed because `EvaluationPanel.update_panel()` called stale
    `EvaluationController.get_plans()` even after `EvaluateCommand` returned
    `Create a training plan before evaluating results.`
- 做了什麼：
  - Added `_application_query_blocks_display()` and `_show_no_data_available()` helpers.
  - `update_panel()` now clears to `No Data Available` before controller plan rendering when a real
    `EvaluateCommand` result is failed or reports an unavailable evaluation summary.
  - Mock / legacy contexts still use the existing controller-backed rendering path when
    `execute_application_command()` returns `None`.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_uses_application_query_before_stale_controller_plans -q`
    -> failed because `stale_controller.get_plans()` was called.
  - After fix:
    same focused command -> `1 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py -q`
    -> `8 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_panel_event_bridges.py -q`
    -> `22 passed`.
  - Static gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed.
- local eval：
  - Not run. This is an Evaluation panel readonly query display cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete Visualization query-result rendering, analysis screenshot acceptance, or
    full UI refresh coordinator closure.

### 2026-05-06 Visualization panel query display gate

- scope：
  - Continue UI/backend truth alignment for readonly analysis rendering.
  - Prevent real `Study` Visualization controls from showing stale injected controller trainers when
    ApplicationService says visualization is blocked / unavailable.
- red / focused test：
  - Added
    `test_visualization_panel_uses_application_query_before_stale_controller_trainers`.
  - It failed because `VisualizationPanel.update_panel()` called stale
    `VisualizationController.get_trainers()` after `VisualizeCommand` returned
    `Create epochs, complete training, or configure saliency before opening visualization views.`
- 做了什麼：
  - Added visualization query display helpers for blocked/unavailable results.
  - `refresh_combos()` now queries `VisualizeCommand(view="summary")` and clears plan/run controls
    before controller trainer rendering when ApplicationService blocks visualization.
  - `on_update()` now shows the user-facing command message instead of continuing to stale
    controller plan/run resolution when the query is blocked.
  - Mock / legacy contexts still use the controller-backed rendering path when
    `execute_application_command()` returns `None`.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_uses_application_query_before_stale_controller_trainers -q`
    -> failed because `ctrl.get_trainers()` was called.
  - After fix:
    same focused command -> `1 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `27 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_evaluation_panel_redesign.py -q`
    -> `35 passed`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes` and refreshed the baseline from
    115 to 112 existing suppressed errors.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed.
- local eval：
  - Not run. This is a Visualization panel readonly query display cleanup under the fast dev gate.
- 不能宣稱：
  - This does not certify saliency/canvas screenshot acceptance, full analysis workflow UX, or
    human desktop rendering.

### 2026-05-06 Visualization export query gate

- scope：
  - Continue analysis UI query-truth cleanup in the Visualization sidebar.
  - Prevent `Export Saliency` from opening on stale trainer lists when ApplicationService says
    saliency output is unavailable.
- red / focused test：
  - Added `test_sidebar_export_saliency_uses_query_before_stale_trainers`.
  - It failed because `export_saliency()` called `panel.get_trainers()` before any backend saliency
    readiness query.
- 做了什麼：
  - `export_saliency()` now runs readonly `SaliencyCommand()` first.
  - If the command fails or reports `saliency_available=False`, the sidebar shows
    `Export Saliency Blocked` and does not read trainers or open the export dialog.
  - Legacy/mock contexts where `execute_application_command()` returns `None` keep the existing
    controller-backed export path.
- validation：
  - Red gate before fix:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_export_saliency_uses_query_before_stale_trainers -q`
    -> failed because `panel.get_trainers()` was called.
  - After fix:
    same focused command -> `1 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py -q`
    -> `11 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `38 passed`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed.
- local eval：
  - Not run. This is a Visualization sidebar query gate cleanup under the fast dev gate.
- 不能宣稱：
  - This does not certify saliency export file contents, saliency canvas correctness, or human
    desktop visualization acceptance.

### 2026-05-06 Tool-call eval gate reminder sync

- scope：
  - Align validation / roadmap docs with the current local-eval operating rule after the user's
    reminder not to run full primary/fallback x3 during routine slices.
- 做了什麼：
  - Kept the existing three-tier gate: fast dev deterministic changed/failed cases, candidate
    primary affected families, release/thesis full deterministic + primary x3 + fallback x3.
  - Strengthened the docs that RTX 5070 Ti 16GB fallback x3 is a high-pressure release/thesis gate,
    and that `nvidia-smi` VRAM saturation should block/defer full fallback x3 rather than being
    treated as normal slowness.
- validation：
  - `git diff --check docs/validation/README.md docs/planning/roadmap.md docs/records/worklog.md`
    -> passed.
  - `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
- local eval：
  - Not run. This is documentation / validation-boundary synchronization under the fast dev gate.
- 不能宣稱：
  - This does not refresh benchmark artifacts or update thesis accuracy claims.

### 2026-05-06 Visualization saliency settings query defaults

- scope：
  - Continue analysis UI query-truth cleanup after the saliency export gate.
  - Prevent Saliency Settings dialog defaults from being populated by stale
    `VisualizationController.get_saliency_params()` when a readonly ApplicationService query is
    available.
- red / focused tests：
  - Added
    `test_capability_readiness_guard_flags_saliency_params_after_capability`; it failed because
    architecture compliance did not yet treat `get_saliency_params()` as a stale capability-gated
    controller read.
  - Added `test_sidebar_set_saliency_uses_query_defaults_before_stale_controller`; it failed
    because `set_saliency()` read the stale controller params before opening the dialog.
- 做了什麼：
  - Added `get_saliency_params` to the capability-gated controller state guard.
  - `ControlSidebar.set_saliency()` now runs readonly `SaliencyCommand()` with `refresh=False` to
    populate dialog defaults from command diagnostics.
  - Controller saliency-param reads remain only through the mock / legacy fallback helper when the
    query result is unavailable.
- validation：
  - Red gates before implementation:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_saliency_params_after_capability -q`
    -> failed with `0` violations.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_uses_query_defaults_before_stale_controller -q`
    -> failed because `controller.get_saliency_params()` was called.
  - After implementation:
    same focused commands -> `1 passed` each.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py -q`
    -> `12 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `39 passed`.
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `26 passed`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - Static gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
- local eval：
  - Not run. This is a Visualization UI query-truth cleanup under the fast dev gate.
- 不能宣稱：
  - This does not certify saliency result contents, full Visualization UX, or human desktop
    rendering.

### 2026-05-06 Visualization montage channel query defaults

- scope：
  - Continue analysis UI query-truth cleanup for Visualization sidebar setup dialogs.
  - Prevent `Set Montage` from populating the montage picker with stale
    `VisualizationController.get_channel_names()` when ApplicationService state is available.
- red / focused tests：
  - Added `test_capability_readiness_guard_flags_channel_names_after_capability`; it failed because
    architecture compliance did not yet treat `get_channel_names()` as a stale capability-gated
    controller read.
  - Added `test_sidebar_set_montage_uses_query_channels_before_stale_controller`; it failed because
    `set_montage()` read the stale controller channel list before opening the dialog.
- 做了什麼：
  - Added `get_channel_names` to the capability-gated controller state guard.
  - `ControlSidebar.set_montage()` now queries `QueryStateCommand(query="state")` with
    `refresh=False` and opens the montage picker with `state.epoch.channel_names`.
  - Controller channel-name reads remain only through the mock / legacy fallback helper when the
    query result is unavailable.
- validation：
  - Red gates before implementation:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_channel_names_after_capability -q`
    -> failed with `0` violations.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_uses_query_channels_before_stale_controller -q`
    -> failed because `controller.get_channel_names()` was called.
  - After implementation:
    same focused commands -> `1 passed` each.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py -q`
    -> `13 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `40 passed`.
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `27 passed`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - Static gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
- local eval：
  - Not run. This is a Visualization UI query-truth cleanup under the fast dev gate.
- 不能宣稱：
  - This does not certify montage placement quality, full Visualization UX, saliency render output,
    or human desktop rendering.

### 2026-05-06 Dataset smart-parse filename query defaults

- scope：
  - Continue UI/backend truth alignment for Dataset action dialogs.
  - Prevent Smart Parser from using stale `DatasetController.get_filenames()` when ApplicationService
    state is available.
- tests：
  - Added `test_capability_readiness_guard_flags_filenames_after_capability`.
  - Strengthened
    `test_open_smart_parser_prefers_backend_capability_over_stale_controller` so the dialog file
    list comes from `QueryStateCommand(query="state")` diagnostics and controller filenames are not
    read.
- 做了什麼：
  - Added `get_filenames` to the capability-gated controller state guard.
  - `DatasetActionHandler.open_smart_parser()` now queries `state.raw.files` through
    `QueryStateCommand(query="state")` with `refresh=False` before opening `SmartParserDialog`.
  - Controller filename reads remain only through the mock / legacy fallback helper when the query
    result is unavailable.
- validation：
  - Focused gates:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_filenames_after_capability -q`
    -> `1 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_prefers_backend_capability_over_stale_controller -q`
    -> `1 passed`.
  - Regression gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py::test_dataset_panel_smart_parse -q`
    -> `67 passed`.
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `28 passed`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - Static gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
- local eval：
  - Not run. This is a Dataset UI query-truth cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete all Dataset dialog population paths, mature Data Interpretation wizard
    certification, or human desktop acceptance.

### 2026-05-06 Training settings state snapshot defaults

- scope：
  - Continue UI/backend truth alignment for Training configuration dialogs.
  - Prevent Training Settings dialog defaults from using stale
    `TrainingController.get_training_option()` when ApplicationService state is available.
- red / focused test：
  - Added
    `test_training_setting_uses_state_snapshot_defaults_before_stale_controller`.
  - It failed before implementation because `TrainingSettingDialog` read
    `controller.get_training_option()` during construction.
- 做了什麼：
  - `TrainingSidebar.training_setting()` now queries `QueryStateCommand(query="state")` with
    `refresh=False` and passes `state.training.training_option` into the dialog.
  - `TrainingSettingDialog` accepts an `initial_option` snapshot and loads epoch / batch size /
    learning rate / repeat / optimizer / device / checkpoint / output directory defaults without
    reading the controller.
  - Controller training-option reads remain only for query-unavailable mock / legacy dialog paths.
- validation：
  - Red gate before implementation:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_uses_state_snapshot_defaults_before_stale_controller -q`
    -> failed because `controller.get_training_option()` was called.
  - After implementation:
    same focused command -> `1 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
    -> `34 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_setting.py tests/unit/ui/test_dialogs_extra.py::TestTrainingSettingDialog -q`
    -> `12 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_panel.py tests/unit/ui/training/test_training_setting.py -q`
    -> `60 passed`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - Static gates:
    `git diff --check` -> passed.
    `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py XBrainLab/ui/dialogs/training/training_setting_dialog.py tests/unit/ui/test_sidebars_and_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py XBrainLab/ui/dialogs/training/training_setting_dialog.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
- local eval：
  - Not run. This is a Training UI dialog default cleanup under the fast dev gate.
- 不能宣稱：
  - This does not verify long-running training, GPU resource behavior, or human desktop training
    acceptance.

### 2026-05-06 Preprocess sidebar capability-first render

- scope：
  - Continue UI/backend truth alignment for sidebar render state.
  - Prevent Preprocess sidebar refresh from reading stale
    `PreprocessController.get_preprocessed_data_list()` when backend capabilities are available.
- red / focused test：
  - Added `test_update_sidebar_prefers_backend_capabilities_over_stale_preprocessed_list`.
  - It failed before implementation because `PreprocessSidebar.update_sidebar()` unconditionally
    read `controller.get_preprocessed_data_list()`.
- 做了什麼：
  - `PreprocessSidebar.update_sidebar()` now treats visible `preprocess` / `create_epoch`
    capabilities as the render source of truth and avoids the stale controller preprocessed-list
    read in real command-capable contexts.
  - The controller preprocessed-list read remains only for no-capability mock / legacy render
    compatibility.
- validation：
  - Focused gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_preprocessed_list -q`
    -> `1 passed`.
  - Sidebar regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
    -> `22 passed`.
- local eval：
  - Not run. This is a Preprocess sidebar render cleanup under the fast dev gate and does not
    justify primary/fallback x3 local eval.
- 不能宣稱：
  - This does not complete full preprocessing workflow UX, command-driven UI refresh closure, or
    human desktop acceptance.

### 2026-05-06 Preprocess render controller-read architecture guard

- scope：
  - Add a static regression guard for the Preprocess sidebar render cleanup.
  - Prevent future capability-backed UI paths from re-reading stale
    `PreprocessController.get_preprocessed_data_list()` outside an explicit no-capability legacy
    branch.
- red / focused test：
  - Added
    `test_capability_readiness_guard_flags_preprocessed_list_after_capability`.
  - Red gate failed with `0` violations, proving the architecture checker did not yet cover this
    controller read.
- 做了什麼：
  - Added `get_preprocessed_data_list` to
    `UI_CAPABILITY_GATED_CONTROLLER_READINESS_METHODS`.
  - Updated `PreprocessSidebar.update_sidebar()` to use explicit `preprocess_capability is None`
    and `epoch_capability is None` branches for legacy render-state fallback.
  - Updated `open_epoching()` to get dialog data through
    `QueryStateCommand(query="data_lists", include_objects=True)` in command-capable contexts.
    `PreprocessController.get_preprocessed_data_list()` remains only for no-capability mock /
    legacy dialog population.
- validation：
  - Red gate:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_capability_readiness_guard_flags_preprocessed_list_after_capability -q`
    -> failed with `0` violations.
  - After implementation:
    same focused command -> `1 passed`.
  - Focused UI gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_preprocessed_list tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_epoch_capability_not_preprocess_block tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_query_data_list_before_stale_controller -q`
    -> `3 passed`.
  - Architecture gate:
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
- local eval：
  - Not run. This is a static architecture guard under the fast dev gate.
- 不能宣稱：
  - This does not prove all controller read paths are gone; it prevents this specific stale
    Preprocess render read from returning.

### 2026-05-06 Preprocess panel render query source

- scope：
  - Continue UI read-side command-truth cleanup for the Preprocess page.
  - Move Preprocess panel history / preview / plotter refresh away from direct controller
    preprocessed-list reads in real `Study` contexts.
- red / focused test：
  - Added `test_update_panel_uses_query_data_lists_before_stale_controller`.
  - Red gate failed because `PreprocessPanel.update_panel()` unconditionally called
    `controller.get_preprocessed_data_list()`.
- 做了什麼：
  - `PreprocessPanel.update_panel()` and `update_plot_only()` now query
    `QueryStateCommand(query="data_lists", include_objects=True)` with `refresh=False`.
  - The queried preprocessed / original objects are passed into
    `PreprocessPlotter.plot_sample_data(data_list=..., original_data_list=...)`.
  - `PreviewWidget.request_plot_update` now routes through `PreprocessPanel.update_plot_only()`,
    so user control changes use the same query-backed render source.
  - Direct controller list reads remain only for no-ApplicationService mock / legacy rendering.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_panel_uses_query_data_lists_before_stale_controller -q`
    -> failed on `controller.get_preprocessed_data_list()`.
  - Focused pass:
    same command -> `1 passed`.
  - Preprocess panel / plotter regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_plotter.py -q`
    -> `37 passed`.
  - Focused type gate:
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_panel.py`
    -> `0 errors, 0 warnings, 0 notes`; baseline count dropped by `1`.
- local eval：
  - Not run. This is a Preprocess UI render-source cleanup under the fast dev gate.
- 不能宣稱：
  - This does not certify plot visual quality, large-data plotting performance, memory cleanup, or
    full command-driven UI refresh closure.

### 2026-05-06 Aggregate Info query-failure boundary

- scope：
  - Continue UI shared-refresh truth cleanup.
  - Prevent real `Study` aggregate info refresh from falling back to controller list reads when
    the ApplicationService data-list query fails.
- red / focused test：
  - Added `test_real_study_query_failure_does_not_fallback_to_controller_lists`.
  - Red gate failed because `InfoPanelService._query_data_lists()` logged the failed query and then
    read `DatasetController.get_loaded_data_list()` / `PreprocessController.get_preprocessed_data_list()`.
- 做了什麼：
  - `InfoPanelService._query_data_lists()` now returns empty loaded / preprocessed lists for real
    `Study` query failures and logs execution exceptions.
  - Controller-list fallback remains only for mock / legacy non-`Study` contexts.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_info_panel_service.py::test_real_study_query_failure_does_not_fallback_to_controller_lists -q`
    -> failed on stale controller list read.
  - Focused pass:
    same command -> `1 passed`.
  - Info panel regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_info_panel_service.py tests/unit/ui/components/test_info_panel.py -q`
    -> `11 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/components/info_panel_service.py tests/unit/ui/components/test_info_panel_service.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/components/info_panel_service.py tests/unit/ui/components/test_info_panel_service.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a shared UI refresh truth cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete the full UI refresh coordinator closure or all controller read-path
    cleanup; it removes one aggregate-info query failure fallback.

### 2026-05-06 Dataset table render query source

- scope：
  - Continue UI read-side command-truth cleanup for the Dataset page.
  - Move Dataset table row rendering away from direct controller loaded-list reads in real `Study`
    contexts.
- red / focused test：
  - Added `test_update_panel_uses_query_data_list_before_stale_controller`.
  - Red gate failed because `DatasetPanel.update_panel()` unconditionally called
    `controller.get_loaded_data_list()`.
- 做了什麼：
  - `DatasetPanel.update_panel()` now queries
    `QueryStateCommand(query="data_lists", include_objects=True)` with `refresh=False`.
  - Direct `DatasetController.get_loaded_data_list()` rendering fallback remains only for
    no-ApplicationService mock / legacy contexts.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_update_panel_uses_query_data_list_before_stale_controller -q`
    -> failed on `controller.get_loaded_data_list()`.
  - Focused pass:
    same command -> `1 passed`.
  - Dataset panel regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py -q`
    -> `14 passed`.
  - Focused type gate:
    `poetry run basedpyright XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
    -> `0 errors, 0 warnings, 0 notes`; baseline count dropped by `1`.
- local eval：
  - Not run. This is a Dataset UI render-source cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete all Dataset action-helper list reads, label import target selection, or
    full Data Interpretation wizard UX acceptance.

### 2026-05-06 Label import target selection from table rows

- scope：
  - Continue Dataset read-side controller cleanup in the post-load label compatibility path.
  - Avoid re-reading loaded files from the controller after the Dataset table already owns the
    selected row objects.
- red / focused test：
  - Added `test_import_label_uses_table_user_role_before_stale_controller_list`.
  - Red gate failed because `_get_target_files_for_import()` called
    `controller.get_loaded_data_list()`.
- 做了什麼：
  - `_get_target_files_for_import()` now first resolves selected/all-row target files from the
    Dataset table's column-0 `Qt.UserRole` data.
  - The controller loaded-list read remains as a mock / legacy fallback when table row objects are
    unavailable.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_uses_table_user_role_before_stale_controller_list -q`
    -> failed on `controller.get_loaded_data_list()`.
  - Focused pass:
    same command -> `1 passed`.
  - Dataset action regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `67 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a Dataset label compatibility UI cleanup under the fast dev gate.
- 不能宣稱：
  - This does not make post-load label import the primary workflow or complete the import wizard
    embedded label editor.

### 2026-05-06 Channel Selection dialog query source

- scope：
  - Continue Dataset sidebar read-side command-truth cleanup.
  - Move Channel Selection dialog data population away from direct controller loaded-list reads in
    real command-capable contexts.
- red / focused test：
  - Added `test_open_channel_selection_uses_query_data_before_stale_controller`.
  - Red gate failed because `DatasetSidebar.open_channel_selection()` called
    `controller.get_loaded_data_list()` after backend capability allowed the action.
- 做了什麼：
  - `DatasetSidebar.open_channel_selection()` now queries
    `QueryStateCommand(query="data_lists", include_objects=True)` with `refresh=False` before
    opening `ChannelSelectionDialog`.
  - `DatasetController.get_loaded_data_list()` remains only for no-capability mock / legacy dialog
    population.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_uses_query_data_before_stale_controller -q`
    -> failed on `controller.get_loaded_data_list()`.
  - Focused pass:
    same command -> `1 passed`.
  - Dataset sidebar regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
    -> `11 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a Dataset sidebar UI cleanup under the fast dev gate.
- 不能宣稱：
  - This does not complete all Dataset controller read-path cleanup or Data Interpretation wizard
    acceptance.

### 2026-05-06 Evaluation object-payload render source

- scope：
  - Continue analysis UI read-side command-truth cleanup.
  - Prevent a successful real `Study` evaluation query from rendering stale injected controller
    plans, pooled metrics, or summary text.
- red / focused test：
  - Added `test_analysis_service_can_return_ui_evaluation_objects`.
  - Added `test_evaluation_panel_uses_application_payload_before_stale_controller`.
  - Red gates failed because `EvaluateCommand` had no object payload option and
    `EvaluationPanel.update_panel()` still called `controller.get_plans()` after a successful
    service query.
- 做了什麼：
  - Added optional `EvaluateCommand.include_objects`.
  - `AnalysisCommandService.handle_evaluate()` now includes `plan_objects`,
    `pooled_eval_results`, and `model_summaries` when object payloads are requested.
  - `EvaluationPanel.update_panel()` requests that payload and uses it for plan list, average
    metrics, and summary rendering before falling back to controller reads.
  - `include_objects` is UI-only for `EvaluateCommand`: automation / MCP schemas hide it, and
    `build_command_from_payload()` rejects it so external clients cannot request non-serializable
    UI object payloads.
  - Controller reads remain for mock / legacy contexts where no service query payload exists.
  - `.basedpyright/baseline.json` dropped by `3` after optional-controller typing was cleaned in
    the touched panel.
- validation：
  - Red gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py::test_analysis_service_can_return_ui_evaluation_objects -q`
    -> failed on missing `include_objects`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_uses_application_payload_before_stale_controller -q`
    -> failed on stale `controller.get_plans()`.
  - Focused pass:
    same commands -> `1 passed` each.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/ui/test_evaluation_panel_redesign.py -q`
    -> `12 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/backend/application/analysis_service.py XBrainLab/backend/application/commands.py XBrainLab/ui/panels/evaluation/panel.py tests/unit/backend/application/test_analysis_service.py tests/unit/ui/test_evaluation_panel_redesign.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/backend/application/analysis_service.py XBrainLab/backend/application/commands.py XBrainLab/ui/panels/evaluation/panel.py tests/unit/backend/application/test_analysis_service.py tests/unit/ui/test_evaluation_panel_redesign.py`
    -> `0 errors, 0 warnings, 0 notes`; baseline count dropped from `110` to `107`.
  - Automation guard:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py::test_automation_rejects_evaluation_ui_object_payload_flag tests/unit/backend/application/test_automation.py::test_mcp_tool_specs_use_same_command_schema -q`
    -> `2 passed`.
    `poetry run ruff check XBrainLab/backend/application/automation.py tests/unit/backend/application/test_automation.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/backend/application/automation.py tests/unit/backend/application/test_automation.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `112 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py -q`
    -> `9 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a UI/backend query-truth cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify evaluation screenshots, full analysis UX, or all remaining
    Evaluation/Visualization controller read paths.

### 2026-05-06 Visualization object-payload render source

- scope：
  - Continue analysis UI read-side command-truth cleanup after Evaluation object payloads.
  - Prevent a successful real `Study` visualization query from rendering stale injected controller
    trainers or averaged records.
- red / focused test：
  - Added `test_analysis_service_can_return_ui_visualization_objects`.
  - Added `test_visualization_panel_uses_application_payload_before_stale_controller`.
  - Expanded automation schema guard tests to cover `visualize.include_objects`.
  - Red gates failed because `VisualizeCommand` had no object payload option and
    `VisualizationPanel.refresh_combos()` still called `controller.get_trainers()` after a
    successful service query.
- 做了什麼：
  - Added optional `VisualizeCommand.include_objects`.
  - `AnalysisCommandService.handle_visualize()` now includes `trainer_objects` and
    `averaged_records` when object payloads are requested.
  - `VisualizationPanel.refresh_combos()` and average-run rendering use that service payload before
    falling back to controller reads.
  - `include_objects` is UI-only for `VisualizeCommand`: automation / MCP schemas hide it, and
    `build_command_from_payload()` rejects it.
  - Controller reads remain for mock / legacy contexts where no service query payload exists.
  - `.basedpyright/baseline.json` dropped by `2` after dynamic test-widget typing was cleaned in
    the touched Visualization panel tests.
- validation：
  - Red gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py::test_analysis_service_can_return_ui_visualization_objects -q`
    -> failed on missing `include_objects`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_uses_application_payload_before_stale_controller -q`
    -> failed on stale `controller.get_trainers()`.
  - Focused pass:
    same commands -> `1 passed` each.
  - Automation guard:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py::test_automation_rejects_ui_object_payload_flag tests/unit/backend/application/test_automation.py::test_mcp_tool_specs_use_same_command_schema -q`
    -> `3 passed`.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_automation.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `44 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/backend/application/analysis_service.py XBrainLab/backend/application/automation.py XBrainLab/backend/application/commands.py XBrainLab/ui/panels/visualization/panel.py tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_automation.py tests/unit/ui/test_visualization_panel_redesign.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/backend/application/analysis_service.py XBrainLab/backend/application/automation.py XBrainLab/backend/application/commands.py XBrainLab/ui/panels/visualization/panel.py tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_automation.py tests/unit/ui/test_visualization_panel_redesign.py`
    -> `0 errors, 0 warnings, 0 notes`; baseline count dropped from `107` to `105`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `114 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `28 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a UI/backend query-truth cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify saliency map / spectrogram / topomap / 3D canvas screenshot acceptance or
    full analysis workflow UX.

### 2026-05-06 Training history query render source

- scope：
  - Continue UI read-side command-truth cleanup for the Training panel.
  - Prevent real `Study` training history rendering from using stale injected
    `TrainingController.get_formatted_history()`.
- red / focused test：
  - Added `QueryStateCommand(query="training_history")` assertions to
    `test_query_state_service_returns_summary_and_capabilities`.
  - Added `test_training_panel_uses_application_history_before_stale_controller`.
  - Red gates failed because `training_history` was not a known query and Training panel did not
    import / call `execute_application_command`.
- 做了什麼：
  - Added `StateSnapshotService.training_history()` and
    `QueryStateCommandService` handling for `query="training_history"`.
  - Query diagnostics include serializable row summaries by default and plan/record objects only
    when `include_objects=True`.
  - `TrainingPanel.update_loop()` now requests
    `QueryStateCommand(query="training_history", include_objects=True)` with `refresh=False`.
  - `TrainingController.get_formatted_history()` remains only for query unavailable mock / legacy
    paths.
- validation：
  - Red gates:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py::test_query_state_service_returns_summary_and_capabilities -q`
    -> failed on unknown `training_history`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py::test_training_panel_uses_application_history_before_stale_controller -q`
    -> failed on missing `execute_application_command` import path.
  - Focused pass:
    same commands -> `1 passed` each.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py tests/unit/ui/training/test_training_panel.py -q`
    -> `20 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/backend/application/state_service.py XBrainLab/ui/panels/training/panel.py tests/unit/backend/application/test_state_service.py tests/unit/ui/training/test_training_panel.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/backend/application/state_service.py XBrainLab/ui/panels/training/panel.py tests/unit/backend/application/test_state_service.py`
    -> `0 errors, 0 warnings, 0 notes`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `114 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py -q`
    -> `18 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a Training panel read-side cleanup under the fast dev gate; it does not
    justify primary/fallback x3 local eval.
- 不能宣稱：
  - This does not remove the high-frequency training observer loop, certify long-running training
    resource cleanup, or complete all Training sidebar controller fallback audit work.

### 2026-05-06 Visualization export trainer payload source

- scope：
  - Continue Visualization read-side command-truth cleanup for Export Saliency.
  - Prevent saliency export from using stale `panel.get_trainers()` /
    `VisualizationController.get_trainers()` after service-backed saliency readiness passes.
- red / focused test：
  - Added
    `test_sidebar_export_saliency_uses_service_trainer_payload_before_panel_fallback`.
  - Red gate failed because `export_saliency()` called `panel.get_trainers()` after the saliency
    query gate.
- 做了什麼：
  - `ControlSidebar.export_saliency()` now requests
    `VisualizeCommand(view="summary", include_objects=True)` after `SaliencyCommand` confirms
    export readiness.
  - The export dialog receives service-backed `trainer_objects` in real `Study` contexts.
  - `panel.get_trainers()` / `VisualizationController.get_trainers()` remain only in
    query-unavailable mock / legacy fallback through `run_legacy_controller_fallback()`.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_export_saliency_uses_service_trainer_payload_before_panel_fallback -q`
    -> failed on `panel.get_trainers()` fallback.
  - Focused pass:
    same command -> `1 passed`.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py -q`
    -> `14 passed`.
  - Focused lint/type/architecture:
    `poetry run ruff check XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
    -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py -q`
    -> `42 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a UI read-source cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify saliency export file contents, saliency canvas screenshots, or full
    Visualization product UX.

### 2026-05-06 Training split dialog context query

- scope：
  - Continue Training split read-source cleanup after backend replacement capability truth.
  - Prevent real `Study` Data Splitting dialog initialization from reading stale
    `TrainingController.get_epoch_data()` / `get_dataset_generator()`.
- red / focused tests：
  - Added `dataset_generation_context` assertions to
    `test_query_state_service_returns_summary_and_capabilities`.
  - Added `test_split_data_passes_service_epoch_context_to_dialog`.
  - Red gates failed because `query_state` did not recognize `dataset_generation_context`, and
    `split_data()` constructed `DataSplittingDialog` without service-backed epoch/generator kwargs.
- 做了什麼：
  - `QueryStateCommandService` now handles `query="dataset_generation_context"` with serializable
    `epoch_available` / `generator_exists` fields and optional UI objects when
    `include_objects=True`.
  - `TrainingSidebar.split_data()` queries that context with `refresh=False` before opening
    `DataSplittingDialog`.
  - `DataSplittingDialog` accepts explicit `epoch_data` / `dataset_generator` and falls back to
    controller reads only when those values are not supplied by the caller.
- validation：
  - Red gates:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py::test_query_state_service_returns_summary_and_capabilities -q`
    -> failed on unknown `dataset_generation_context`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_passes_service_epoch_context_to_dialog -q`
    -> failed because no `epoch_data` kwarg reached `DataSplittingDialog`.
  - Focused pass:
    same commands -> `1 passed` each.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/test_data_splitting.py tests/unit/ui/dialogs/test_data_splitting.py -q`
    -> `114 passed`.
  - Focused lint/type/architecture:
    `poetry run ruff check XBrainLab/backend/application/state_service.py XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py XBrainLab/ui/panels/training/sidebar.py tests/unit/backend/application/test_state_service.py tests/unit/ui/test_sidebars_and_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/backend/application/state_service.py XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py XBrainLab/ui/panels/training/sidebar.py tests/unit/backend/application/test_state_service.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `114 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_state_service.py tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/test_data_splitting.py tests/unit/ui/dialogs/test_data_splitting.py -q`
    -> `114 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a UI/backend query-source cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not redesign the Data Splitting dialog UX, remove all Training sidebar fallback
    paths, or certify long-running dataset-generation thread cleanup.

### 2026-05-06 Data Splitting preview worker cleanup

- scope：
  - Improve focused thread/job lifecycle cleanup for Data Splitting preview generation.
  - Prevent dialog close and repeated preview restarts from only interrupting the active
    `DatasetGenerator` without waiting for the Python worker thread.
- red / focused tests：
  - Added `test_close_stops_timer_and_generator` assertion that close calls worker `join()`.
  - Added `test_preview_interrupts_and_joins_previous_worker`.
  - Red gates failed because `closeEvent()` / `preview()` called `set_interrupt()` but never joined
    the preview worker.
- 做了什麼：
  - Added bounded preview-worker cleanup to `DataSplittingPreviewDialog`.
  - `preview()` now interrupts and short-joins the previous preview worker before starting a new
    generator.
  - `closeEvent()` now stops the timer, interrupts the generator, and short-joins the worker before
    delegating to Qt close handling.
- validation：
  - Red gates:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_data_splitting.py::TestDataSplittingPreviewDialogSplitters::test_close_stops_timer_and_generator -q`
    -> failed because `join()` was not called.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_data_splitting.py::TestDataSplittingPreviewDialogSplitters::test_preview_interrupts_and_joins_previous_worker -q`
    -> failed because `join()` was not called.
  - Focused pass:
    same commands -> `1 passed` each.
  - Regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_data_splitting.py tests/unit/ui/dialogs/test_data_splitting.py tests/unit/ui/dataset/test_data_splitting.py tests/unit/ui/test_panels_and_dialogs.py -q`
    -> `105 passed`.
  - Focused lint/type/architecture:
    `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py tests/unit/ui/test_data_splitting.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py tests/unit/ui/test_data_splitting.py`
    -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py`
    -> `Architecture compliant!`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_data_splitting.py tests/unit/ui/dialogs/test_data_splitting.py tests/unit/ui/dataset/test_data_splitting.py tests/unit/ui/test_panels_and_dialogs.py -q`
    -> `105 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a UI thread lifecycle cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This is not a long-running dataset-generation soak test, memory leak proof, or full PyQt worker
    lifecycle certification.

### 2026-05-06 Visualization 3D plotter widget cleanup

- scope：
  - Continue focused visualization/saliency resource cleanup after training and dataset preview
    lifecycle slices.
  - Prevent `Saliency3DPlotWidget.clear_plot()` from only detaching layout children without
    scheduling ordinary child widgets for Qt deletion.
  - Keep this as a fast dev gate slice; no local LLM primary/fallback eval was run.
- red / focused tests：
  - Added `test_clear_plot_schedules_child_widgets_for_deletion`.
  - Red gate failed because a temporary child `QLabel` was detached but not scheduled for
    `deleteLater()`.
- 做了什麼：
  - `clear_plot()` now stores the active plotter, detaches every layout child, schedules non-plotter
    child widgets for `deleteLater()`, then closes / deletes the plotter via runtime-safe method
    checks and clears `plotter_widget`.
  - Avoided double-delete by letting the plotter-specific block own plotter close/delete while the
    layout loop handles other children.
  - `.basedpyright/baseline.json` dropped by one suppressed `QtInteractor.close` attribute error.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot_schedules_child_widgets_for_deletion -q`
    -> failed because `label.deleted` stayed `False`.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot_schedules_child_widgets_for_deletion tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
    -> `3 passed`.
  - Visualization regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/components/test_plot_figure_window.py -q`
    -> `59 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py tests/unit/ui/test_visualization.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py tests/unit/ui/test_visualization.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Slice gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with the existing MkDocs Material advisory.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a UI widget lifecycle cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify interactive desktop 3D / PyVista render, OpenGL soak behavior, full
    Visualization product UX, or human Windows desktop acceptance.

### 2026-05-06 Preprocess re-reference dialog query source

- scope：
  - Continue UI command truth cleanup from the remaining controller-read audit.
  - Prevent command-capable `open_rereference()` from opening `RereferenceDialog` with stale
    `PreprocessController.get_preprocessed_data_list()` data.
- red / focused tests：
  - Added `test_open_rereference_uses_query_data_list_before_stale_controller`.
  - Red gate failed because `open_rereference()` called the stale controller getter before opening
    the dialog.
- 做了什麼：
  - Extracted `_preprocessed_data_list_for_dialog()` from the epoching query helper.
  - `open_epoching()` still uses the helper with `Epoching Blocked`.
  - `open_rereference()` now calls the same `QueryStateCommand(query="data_lists",
    include_objects=True)` helper before constructing `RereferenceDialog`.
  - Controller list reads remain only when no command capability exists and
    `execute_application_command()` returns `None`, preserving mock / legacy compatibility.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_uses_query_data_list_before_stale_controller -q`
    -> failed because `PreprocessController.get_preprocessed_data_list()` was called.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_uses_query_data_list_before_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_accepted tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_query_data_list_before_stale_controller -q`
    -> `3 passed`.
  - Preprocess regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess -q`
    -> `65 passed`.
  - Focused lint/type/architecture:
    `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
- local eval：
  - Not run. This is a UI command-source cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not finish all Preprocess dialog read-source audits, full preprocessing workflow UI
    acceptance, or long-running preprocessing resource validation.

### 2026-05-06 Preprocess PSD stale-result guard

- scope：
  - Add an observable UI responsiveness guard for async Preprocess PSD rendering.
  - Prevent an older QThreadPool PSD worker result from writing into the frequency plot after a
    newer `plot_sample_data()` call has already started.
- red / focused tests：
  - Added `test_stale_psd_result_does_not_update_latest_plot`.
  - Red gate failed because the first captured PSD result handler still plotted into
    `plot_freq` after a second plot generation had started.
- 做了什麼：
  - Added `_plot_generation` to `PreprocessPlotter`.
  - Each `plot_sample_data()` increments the generation and captures it for the PSD result handler.
  - The handler returns without touching the UI if the result is stale.
  - Tightened two existing test assertions with `y is not None` so focused basedpyright can verify
    the touched test file without widening the baseline.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py::test_stale_psd_result_does_not_update_latest_plot -q`
    -> failed because stale handler called `plot_freq.plot()`.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py::test_stale_psd_result_does_not_update_latest_plot tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_async_psd tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_time_domain -q`
    -> `3 passed`.
  - Preprocess regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py tests/unit/ui/preprocess tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
    -> `45 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a UI async render guard under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not cancel running PSD workers, prove long-running preprocessing performance, or
    certify memory leak behavior.

### 2026-05-06 SinglePlotWindow close cleanup

- scope：
  - Continue focused UI resource cleanup for repeated plot window open/close.
  - Ensure the base Matplotlib plot dialog closes the actual embedded figure, not only the original
    `plot_number`, and releases Qt canvas / toolbar references.
- red / focused tests：
  - Added `test_close_releases_current_figure_and_qt_widgets`.
  - Red gate failed because `closeEvent()` did not call `plt.close()` for the external figure passed
    through `set_figure()`, and left `figure_canvas` / `toolbar` references populated.
- 做了什麼：
  - Added `_close_current_figure()` to close `fig_param["fig"]` and any remaining `plot_number`.
  - Added `_release_canvas_widgets()` to remove canvas / toolbar from the layout, detach them,
    schedule `deleteLater()`, and clear references.
  - `closeEvent()` now runs both helpers before delegating to Qt close handling.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_close_releases_current_figure_and_qt_widgets -q`
    -> failed because the external figure was not passed to `plt.close()`.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_close_releases_current_figure_and_qt_widgets tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_creates tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_has_figure_canvas -q`
    -> `3 passed`.
  - Plot window regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestSinglePlotWindow tests/unit/ui/components/test_plot_figure_window.py tests/unit/ui/dialogs/test_dialogs_structure.py::TestDialogStructure::test_single_plot_window_init -q`
    -> `19 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/components/single_plot_window.py tests/unit/ui/test_ui_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/components/single_plot_window.py tests/unit/ui/test_ui_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a UI resource cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not prove long-run Matplotlib memory trends, full visualization soak behavior,
    interactive desktop 3D render, or human Windows desktop acceptance.

### 2026-05-06 Saliency 2D canvas cleanup

- scope：
  - Continue visualization resource cleanup after plot-window and 3D widget cleanup.
  - Remove duplicated Map / Spectrogram / Topomap figure-replacement code that closed figures but
    did not detach / deleteLater the old Matplotlib canvas.
- red / focused tests：
  - Added `test_close_releases_figure_and_canvas`.
  - Added `test_replace_figure_releases_previous_canvas`.
  - Red gates failed because close left `canvas` populated and `_replace_figure()` did not exist.
- 做了什麼：
  - Added `BaseSaliencyView._close_current_figure()`, `_release_canvas()`, and `_replace_figure()`.
  - `closeEvent()` now closes the current figure, detaches canvas, schedules `deleteLater()`, and
    clears references.
  - Map / Spectrogram / Topomap update paths now call the shared `_replace_figure()` helper instead
    of duplicating partial canvas replacement code.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_close_releases_figure_and_canvas tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_replace_figure_releases_previous_canvas -q`
    -> failed because `canvas` remained set and `_replace_figure()` was missing.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_close_releases_figure_and_canvas tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_replace_figure_releases_previous_canvas tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_update_plot_no_eval tests/unit/ui/test_visualization.py::TestSaliencySpectrogramWidget::test_update_plot_no_eval tests/unit/ui/test_visualization.py::TestSaliencyTopographicMapWidget::test_update_plot_no_eval -q`
    -> `5 passed`.
  - Visualization regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/components/test_plot_figure_window.py -q`
    -> `61 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py XBrainLab/ui/panels/visualization/saliency_views/map_view.py XBrainLab/ui/panels/visualization/saliency_views/spectrogram_view.py XBrainLab/ui/panels/visualization/saliency_views/topomap_view.py tests/unit/ui/test_visualization.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py XBrainLab/ui/panels/visualization/saliency_views/map_view.py XBrainLab/ui/panels/visualization/saliency_views/spectrogram_view.py XBrainLab/ui/panels/visualization/saliency_views/topomap_view.py tests/unit/ui/test_visualization.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a UI resource cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify full saliency workflow UX, long-run visualization memory trends,
    interactive desktop 3D render, or human Windows desktop acceptance.

### 2026-05-06 ConfusionMatrixWidget cleanup

- scope：
  - Continue evaluation / visualization widget cleanup with a focused Evaluation tab component.
  - Ensure confusion matrix plot replacement and plan=None clearing release old widgets and figure
    references.
- red / focused tests：
  - Added `test_update_none_releases_previous_canvas_and_children`.
  - Red gate failed because a temporary child label was detached but not scheduled for
    `deleteLater()`, and `fig` / `canvas` references stayed populated after `update_plot(None)`.
- 做了什麼：
  - Added `_clear_plot_widgets()` to detach and `deleteLater()` all plot-layout child widgets and
    clear `canvas`.
  - Added `_close_current_figure()` to close the current Matplotlib figure and clear `fig`.
  - `update_plot()` and `closeEvent()` now use those helpers before drawing a new confusion matrix
    or message.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_none_releases_previous_canvas_and_children -q`
    -> failed because `temporary_label.deleted` stayed `False`.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_none_releases_previous_canvas_and_children tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_creates tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_plot_no_data -q`
    -> `3 passed`.
  - Evaluation regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/test_ui_components.py::TestConfusionMatrix tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
    -> `29 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/evaluation/confusion_matrix.py tests/unit/ui/test_ui_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/evaluation/confusion_matrix.py tests/unit/ui/test_ui_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a UI resource cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify full Evaluation tab UX, long-run memory trend behavior, or human desktop
    acceptance.

### 2026-05-06 MetricsBarChart close cleanup

- scope：
  - Continue Evaluation tab Matplotlib widget cleanup after ConfusionMatrixWidget.
  - Ensure the per-class metrics chart releases its figure / canvas on widget close.
- red / focused tests：
  - Added `test_close_releases_figure_and_canvas`.
  - Red gate failed because `MetricsBarChartWidget` inherited QWidget close behavior and never
    called `plt.close()` or cleared canvas references.
- 做了什麼：
  - Added `_release_canvas()` and `_close_current_figure()` to `MetricsBarChartWidget`.
  - `closeEvent()` now detaches / `deleteLater()` the canvas, closes the current figure, and clears
    `fig` / `canvas` / `ax` references.
  - `update_plot()` now returns quietly if the widget has already released its plotting resources.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_close_releases_figure_and_canvas -q`
    -> failed because `plt.close()` was not called.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_close_releases_figure_and_canvas tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_creates tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_update_plot_no_data tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_update_plot_layout_failure_is_not_logged_as_error -q`
    -> `4 passed`.
  - Evaluation regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/test_ui_components.py::TestConfusionMatrix tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
    -> `30 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/panels/evaluation/metrics_bar_chart.py tests/unit/ui/test_ui_components.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/panels/evaluation/metrics_bar_chart.py tests/unit/ui/test_ui_components.py`
    -> `0 errors, 0 warnings, 0 notes`.
- local eval：
  - Not run. This is a UI resource cleanup under the fast dev gate; it does not justify
    primary/fallback x3 local eval.
- 不能宣稱：
  - This does not certify full Evaluation tab UX, long-run memory trend behavior, or human desktop
    acceptance.

### 2026-05-06 Explicit local eval gate guard

- scope：
  - Turn the user's local eval tiering reminder into an executable CLI guard.
  - Full primary/fallback x3 should remain a release / thesis evidence gate, not something routine
    UI/backend/prompt slices can start by accident.
- red / focused tests：
  - Added `test_resource_preflight_requires_release_gate_for_full_suite_x3`.
  - Added `test_cli_requires_explicit_release_gate_before_full_local_x3`.
  - Red gate failed because `build_local_eval_resource_preflight()` had no `eval_gate` argument
    and the CLI would start full local x3 under normal VRAM pressure.
- 做了什麼：
  - Added `--eval-gate fast|candidate|release|thesis` to
    `scripts/agent/evals/run_local_tool_call_eval.py`; default is `candidate`.
  - Full-suite repeat `3` local eval now requires `--eval-gate release` or `--eval-gate thesis`.
  - If default candidate gate or high VRAM pressure blocks the run, the CLI writes
    `resource_preflight.json` / `.md` before any local model is loaded.
  - Preflight artifacts and local eval markdown now include the declared eval gate.
- validation：
  - Red gate:
    `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py::test_resource_preflight_requires_release_gate_for_full_suite_x3 tests/unit/scripts/test_run_local_tool_call_eval.py::test_cli_requires_explicit_release_gate_before_full_local_x3 -q`
    -> failed as expected.
  - Focused pass:
    `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py::test_resource_preflight_requires_release_gate_for_full_suite_x3 tests/unit/scripts/test_run_local_tool_call_eval.py::test_cli_requires_explicit_release_gate_before_full_local_x3 tests/unit/scripts/test_run_local_tool_call_eval.py::test_resource_preflight_blocks_full_local_gate_under_vram_pressure tests/unit/scripts/test_run_local_tool_call_eval.py::test_resource_preflight_allows_changed_case_gate_under_vram_pressure tests/unit/scripts/test_run_local_tool_call_eval.py::test_cli_writes_preflight_artifact_and_aborts_full_fallback -q`
    -> `5 passed`.
  - Local eval runner regression:
    `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py -q`
    -> `39 passed`.
  - Focused lint/type:
    `poetry run ruff check scripts/agent/evals/run_local_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> `All checks passed!`.
    `poetry run basedpyright scripts/agent/evals/run_local_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `40 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `489 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `7 passed`.
- local eval：
  - Not run. This is a runner guard / validation policy slice; no formal benchmark claim is being
    refreshed.
- 不能宣稱：
  - This does not refresh deterministic or local model benchmark artifacts.
  - Human desktop acceptance, import wizard maturity, and product completion remain open.

### 2026-05-06 Data Interpretation Review Summary row clipping

- scope：
  - Continue the user-reported Data Interpretation preview polish after table-fit and contrast
    fixes.
  - Ensure `Review Summary` scrolls cleanly without exposing half-visible text rows.
- red / focused tests：
  - Added `test_data_interpretation_preview_dialog_review_summary_shows_whole_rows`.
  - Red gate first failed because five review rows could exceed the viewport; after the first height
    adjustment, refreshed screenshot still showed a sixth row clipped at the bottom, so the test was
    tightened to catch partial visible rows when there are more rows than the visible summary area.
- 做了什麼：
  - Added `_fit_review_tree_height()` to size the dialog `Review Summary` tree to complete rows.
  - The summary shows up to five complete rows and uses vertical scrolling for additional rows,
    without leaving a partial row visible at the bottom.
  - Added `partial_visible_tree_rows()` and vertical scrollbar metadata to
    `scripts/dev/capture_data_interpretation_replay.py`.
  - Updated the UI product walkthrough test fakes to accept production dialog context kwargs
    (`epoch_data`, `initial_option`, and future dialog context fields).
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_review_summary_shows_whole_rows -q`
    -> failed on clipped review rows.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_review_summary_shows_whole_rows -q`
    -> `1 passed`.
  - Dialog / replay / walkthrough regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `27 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/integration/ui/test_product_walkthrough.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/integration/ui/test_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - UI-observable replay:
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; refreshed `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-remap.png`, and `artifacts/ui/data-interpretation-replay.json`.
    Manual screenshot review confirmed the preview `Review Summary` now shows whole rows only.
    Replay JSON records preview `Review Summary` `partial_visible_rows=[]`,
    `vertical_scrollbar_max=4`; remap `Review Summary` `partial_visible_rows=[]`,
    `vertical_scrollbar_max=0`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- local eval：
  - Not run. This is a UI replay / visual polish slice; fast dev gate is sufficient.
- 不能宣稱：
  - This does not complete mature Data Interpretation wizard UX, full real-data manual
    certification, Windows desktop acceptance, or product completion.

### 2026-05-06 Training updated refresh route

- scope：
  - Continue `UI Command Refresh Coordinator + Controller Fallback Audit` with a focused observer
    route cleanup.
  - Bring live `training_updated` refresh into the same owner-scoped coordinator path as the other
    training lifecycle events.
- red / focused tests：
  - Added `test_training_updated_observer_uses_training_owner_scope`.
  - Red gate failed because `training_updated` was missing from `_OBSERVER_EVENT_REFRESH_ROUTES`,
    so only TrainingPanel refreshed and Evaluation / Visualization readiness stayed untouched.
- 做了什麼：
  - Added `training_updated` to the central refresh route with `ChangedState(training_changed=True)`.
  - The TrainingPanel owner now refreshes Training / Evaluation / Visualization plus aggregate info
    and assistant backend status for live training updates.
- validation：
  - Red gate:
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_training_updated_observer_uses_training_owner_scope -q`
    -> failed as expected on missing Evaluation / Visualization refresh.
  - Focused pass:
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py::test_training_updated_observer_uses_training_owner_scope tests/unit/ui/test_refresh_coordinator.py::test_training_lifecycle_observer_uses_training_owner_scope tests/unit/ui/test_refresh_coordinator.py::test_secondary_training_lifecycle_observer_does_not_duplicate_central_scope -q`
    -> `3 passed`.
  - UI refresh regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/training/test_training_panel.py -q`
    -> `54 passed`.
  - Focused lint/type:
    `poetry run ruff check XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> `All checks passed!`.
    `poetry run basedpyright XBrainLab/ui/refresh_coordinator.py tests/unit/ui/test_refresh_coordinator.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- local eval：
  - Not run. This is UI refresh coordinator logic under the fast dev gate.
- 不能宣稱：
  - This does not complete full command-driven UI refresh coordination, remove all observer paths,
    or close controller fallback audit.

### 2026-05-06 Human-like clipped-row quality gate

- scope：
  - Fold the Data Interpretation `Review Summary` partial-row evidence into the consolidated
    human-like walkthrough quality gate.
  - Prevent future artifacts from passing when a captured table/tree widget shows a half-visible
    row at the viewport edge.
- red / focused tests：
  - Added `test_build_ui_quality_review_flags_clipped_table_rows`.
  - Red gate failed as expected because `build_table_geometry_review()` ignored
    `partial_visible_rows`.
- 做了什麼：
  - Extended shared `table_state()` with `vertical_scrollbar_max` and `partial_visible_rows`.
  - Added `partial_visible_table_rows()` alongside the existing tree partial-row helper.
  - Updated human-like `build_table_geometry_review()` to include
    `shows_only_complete_rows`, fail on clipped visible rows, and expose
    `clipped_row_findings` in JSON / Markdown.
  - Refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md` /
    screenshots and `artifacts/ui/data-interpretation-replay.json`.
- validation：
  - Red gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py::test_build_ui_quality_review_flags_clipped_table_rows -q`
    -> failed as expected with no geometry finding.
  - Focused pass:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py::test_build_ui_quality_review_flags_clipped_table_rows -q`
    -> `1 passed`.
  - Script unit regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
    -> `16 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `5 passed`.
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `21 passed`.
  - Focused lint/type:
    `poetry run ruff check scripts/dev/capture_data_interpretation_replay.py scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> `All checks passed!`.
    `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py scripts/dev/capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - UI-observable replay:
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`; latest artifact status `passed`, checked `15` table/tree widgets,
    geometry findings `0`, clipped-row findings `0`.
    `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; Dataset table artifact now also records `vertical_scrollbar_max=0` and
    `partial_visible_rows=[]`.
  - Static / docs gates:
    `git diff --check` -> passed.
    `poetry run ruff check .` -> `All checks passed!`.
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
    `poetry run mkdocs build --strict` -> passed with existing MkDocs Material advisory.
  - Agent / backend smoke:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    -> `20 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- local eval：
  - Not run. This is UI artifact quality gating under the fast dev gate; no formal benchmark claim
    changed.
- 不能宣稱：
  - This does not prove mature import-wizard UX, Windows human desktop acceptance, dual-monitor /
    DPI behavior, or long real local-model sessions.
