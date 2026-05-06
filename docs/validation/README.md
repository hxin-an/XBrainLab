# XBrainLab Validation

最後更新：`2026-05-06`

## 這份文件的用途

這份文件整理 XBrainLab 的驗證策略。

重點不是列出所有測試，而是回答：

- 哪些測試代表哪些可信度？
- 哪些 evidence 可以支撐 thesis claim？
- 哪些只是 engineering smoke？
- 現在有哪些驗證還不能信？

## 目前狀態

`artifacts/quality/latest.*` 已可引用作為今天的 fast engineering evidence，但 `2026-05-02`
人工產品驗收修正了它的可信邊界：fast engineering evidence 不能代表 AI Assistant
已達可用產品狀態。使用者實際打開 assistant 後曾發現 chat UI 仍像 debug dock，且輸入
`hello` 沒有 assistant 回覆。該 blocker 已完成第一輪 targeted 修復和 product tests；
後續 assistant product audit follow-up 又修掉 top chip dump、Retry transcript pollution、
raw tool output 外洩、窄 dock bubble wrapping 和 legacy remote runtime 產品入口暴露。
但仍不能用 dashboard PASS、local runtime smoke 或 deterministic eval 直接宣稱完整 release
closure。

## Evidence 分層與 Claim Boundary

本文件把 UI / backend / 人工驗收分成三層，避免把可重跑 script 擴張成真人產品驗收：

| Evidence 層級 | 可支撐的 claim | 不能支撐的 claim |
| --- | --- | --- |
| Backend replay | `ApplicationService / Command API` contract、state transition、typed result、capability / autonomy policy 可重跑。 | 不能證明使用者看得到、按得到或 UI 文案合理。 |
| UI-observable automated walkthrough | automated replay 透過真 Qt UI path 產生 screenshots、visible text、button state、workflow state、transcript 和 backend state snapshot，可證明主要 UI path 在 replay 條件下可操作。 | 不能等同真人 Windows desktop acceptance，也不能證明雙螢幕、DPI、launcher、長時間 local model session 都可用。 |
| Human desktop acceptance | 真人從 Windows desktop launcher 在實際螢幕 / DPI / GPU / local model session 操作並確認。 | 這層目前仍未完成；未完成前不能宣稱 product-complete。 |

Tool-call eval 另採分層 gate，避免每個小修都消耗完整 local benchmark：

| Gate | 使用時機 | 模型 / 重跑策略 |
| --- | --- | --- |
| Fast dev gate | verifier、normalizer、prompt、case wording、UI refresh 等日常切片。 | deterministic eval；只跑 changed / failed cases；repeat `1`；不跑 fallback model。 |
| Candidate gate | 需要真 local model 檢查受影響 case family。 | primary model；affected case families；repeat `1` 或 `2`。 |
| Release / thesis gate | 更新正式 benchmark claim 或 thesis evidence artifact。 | deterministic full suite；primary full suite x3；fallback full suite x3；dashboard refresh；記錄 VRAM / latency / resource pressure。 |

`scripts/agent/evals/run_local_tool_call_eval.py` now performs a CLI resource preflight before
loading the local model. It records disk/cache and `nvidia-smi` VRAM state in the result artifact;
full-suite repeat-`3` local eval also requires explicit `--eval-gate release` or
`--eval-gate thesis`. If the CLI is left on its default candidate gate, or if a release/thesis full
local gate sees high VRAM pressure, it writes `resource_preflight.json` / `.md` and exits before
starting the model. This guard is for local eval execution only; routine development still should
use deterministic changed cases or primary subsets. On the target RTX 5070 Ti 16GB machine, full
fallback x3 is a release / thesis evidence gate only. If `nvidia-smi` shows VRAM near saturation,
do not start a full fallback x3 run; record the resource state and use the fast dev or candidate
gate until a formal benchmark claim is being refreshed.

2026-05-06 explicit local eval gate guard:

- `run_local_tool_call_eval.py` now blocks full-suite repeat `3` local eval on the default
  candidate gate even when VRAM is normal. Formal runs must pass `--eval-gate release` or
  `--eval-gate thesis`.
- Focused evidence:
  `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py -q`
  -> `39 passed`; `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  -> `489 passed`; `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
- Claim boundary: no local LLM benchmark was rerun for this guard slice, so no thesis score claim
  changed.

最新使用者要求的「單一 automated human-like walkthrough」已新增：
`scripts/dev/capture_human_like_product_walkthrough.py` 產出
`artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md` 和 `20` 張 screenshots。
artifact 覆蓋 startup、Data Interpretation wizard、recipe reload、preprocess、epoch、dataset、
training readiness、analysis readiness、ChatPanel empty / normal / clarification / blocked /
success / narrow、reset / new session boundary、error recovery 和 eval dashboard report。
最新 artifact summary 是 status `passed`、`26 / 26` required phases、`20` screenshots。UI polish
後已刷新 screenshots；reset / new-session boundary 截圖也已確認不再顯示 stale chat bubbles
或 stale `Ready to train` workflow status。最新 metadata apply slice 也讓 applied-state Dataset
table 顯示 reviewed `S01` / `session-01`，且 training readiness 回到 dataset-ready / Start Training
enabled。最新 artifact 另有 top-level `observable_evidence` / `ui_quality_review`：`26`
個 phase 都有 visible text、button state、workflow/backend snapshot index，`20` 張 screenshot
全數 nonblank，visible text raw tool / schema / traceback leakage findings 為 `0`。最新
ChatPanel evidence hardening 也讓 visible text snapshots 收到 chat bubble `QTextBrowser` 內容：
normal / clarification / blocked / successful / narrow-panel phases 的 JSON 現在包含使用者與
assistant 氣泡文字，且 top-level `chatpanel.visible_messages` 會在 reset 前保存可見訊息。這支撐
automated PyQt replay 的主要 UI 操作路徑，但仍不能
替代 human desktop acceptance。
同一 walkthrough 現在也把 process/thread resource notes 納入 pass/fail smoke：artifact
`pass_fail_summary.resource_smoke` 會檢查 replay close 後 Python thread count 是否回落、
Qt thread pool 是否仍 active，以及 `ru_maxrss` high-water delta 是否超過 smoke threshold。
最新 offscreen artifact 顯示 resource smoke `passed=True`、RSS growth `231884 KB` /
limit `600000 KB`、Qt active thread `0`，且 visible text 已刷新到
`Review and confirm these choices before applying.` / `Ask about EEG workflow`。這只能抓明顯 cleanup regression，不是
leak-proof soak test，也不能替代長時間 local model / training desktop session。
最新 eval dashboard screenshot 也已改成 product-style HTML report：walkthrough 會把
`artifacts/agent_evals/dashboard.md` 的 Markdown tables 轉成深色 styled tables 後截圖，避免
UI-observable evidence 顯示 raw pipe table / debug text dump；同時把 Thesis Claim Boundary
提升到 screenshot 第一屏，明確標示 benchmark slice 不能代表 UI usability、Windows launcher
coverage 或 product completion。這是 artifact presentation gate，不是新的 tool-call benchmark run。
最新 Dataset sidebar polish 後也已刷新同一 walkthrough artifact；`Channel Selection` 改為中性
sidebar action，不再用 success-green 表示一個尚未執行且會修改資料的操作。`Clear Dataset`
也改由 backend state query 決定 availability：empty startup / reset boundary 截圖和 JSON
button state 都顯示 disabled + `No dataset to clear.` tooltip，Data Interpretation apply 後才
enabled；disabled danger / success / warning button tokens 也改成中性灰色，避免 disabled action
仍像可按。
同輪 artifact 也驗證 assistant empty-state / status visible text 只顯示 Data Interpretation
主線 `Scan data source`，不再把 legacy `load_data` / `attach_labels` 轉成新使用者主流程提示。
最新 Dataset table geometry guard 又把 `right_gap_to_boundary` 納入 replay / walkthrough
artifact。`artifacts/ui/data-interpretation-replay.json` 目前記錄 `widget_width=1020`、
`table_right_x=1020`、`right_boundary_x=1020`、`right_gap_to_boundary=0`，證明 1280px
capture 中載入資料後 table widget 直接貼齊 sidebar；human-like walkthrough 的較窄 capture
同樣記錄 `right_gap_to_boundary=0`。這是 automated layout evidence，仍需真人桌面驗收判斷
整體視覺品質。
最新 clipped-row geometry gate 把同一 evidence 提升到 consolidated human-like walkthrough
quality review：`table_state()` 現在也保存 `vertical_scrollbar_max` / `partial_visible_rows`，
`build_table_geometry_review()` 會在任何 captured table/tree widget 出現半截 visible row 時 failed。
最新 `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` 顯示 table geometry checked
`15` widgets、geometry findings `0`、clipped row findings `0`；這仍是 offscreen PyQt automated
evidence，不是 Windows human desktop acceptance。
ChatPanel composer polish follow-up gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py -q`
-> `55 passed`。

Local model downloader lifecycle gate:
`poetry run pytest --capture=sys tests/unit/llm/core/test_downloader.py tests/unit/llm/test_coverage_boost.py::TestDownloadWorkerRun tests/unit/llm/test_misc_coverage.py::TestModelDownloaderCoverage tests/unit/test_llm_backend.py::TestDownloader -q`
-> `27 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/test_local_bootstrap_validation.py -q`
-> `25 passed`。This supports bounded QThread / subprocess cleanup for model download cancel /
dialog teardown. It is not a long-running local model soak, GPU leak proof, or human desktop
acceptance.

Local runtime shutdown lifecycle gate:
`poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py tests/unit/llm/core/test_backend_local.py tests/unit/llm/core/test_engine_hotswap.py -q`
-> `37 passed`；
`poetry run pytest --capture=sys tests/unit/llm/agent/test_worker.py tests/unit/llm/test_worker_coverage.py tests/unit/llm/agent/test_worker_timeout.py -q`
-> `39 passed`；
`poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_controller_cov.py tests/unit/llm/agent/test_controller_integration.py -q`
-> `99 passed`。This supports backend unload / engine close / worker shutdown contract and
controller close wiring. It is still not GPU leak-proof soak evidence or human desktop acceptance.

Training force-clean lifecycle gate:
`poetry run pytest --capture=sys tests/unit/backend/training/test_trainer.py tests/unit/backend/test_training_manager.py -q`
-> `40 passed`；
`poetry run pytest --capture=sys tests/unit/backend/controller/test_training_controller.py tests/unit/backend/application/test_training_service.py tests/unit/backend/application/test_lifecycle_service.py -q`
-> `19 passed`；
`poetry run pytest --capture=sys tests/integration/backend -q`
-> `7 passed`。This supports bounded force-clean thread handling and preserving the trainer handle
on cleanup timeout. It is not long-running training soak evidence.

Data Splitting dialog explicit-context gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_data_splitting.py::TestDataSplittingDialog::test_real_study_requires_explicit_service_context -q`
-> `1 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/test_data_splitting.py tests/unit/ui/test_data_splitting.py tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
-> `114 passed`。This supports the boundary that real `Study` Data Splitting dialogs require
explicit service-backed epoch/generator context instead of reading stale TrainingController data.
Mock / legacy dialog fallback remains. This does not redesign the split UX or prove long-running
dataset-generation behavior.

Visualization 3D widget cleanup gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot_schedules_child_widgets_for_deletion tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_clear_plot tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
-> `3 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/components/test_plot_figure_window.py -q`
-> `59 passed`。This supports the 3D saliency widget child / plotter cleanup contract and the
existing headless blocked-before-QtInteractor behavior. It is not interactive desktop 3D / PyVista
render acceptance, OpenGL soak evidence, or human Windows desktop verification.

Preprocess re-reference dialog query-source gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_uses_query_data_list_before_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_rereference_accepted tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_query_data_list_before_stale_controller -q`
-> `3 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess -q`
-> `65 passed`。This supports query-backed dialog data for command-capable re-reference and
epoching paths. It does not prove the full Preprocess UI workflow or all remaining controller read
audits are complete.

Preprocess PSD stale-result gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py::test_stale_psd_result_does_not_update_latest_plot tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_async_psd tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_time_domain -q`
-> `3 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_plotter.py tests/unit/ui/preprocess tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
-> `45 passed`。This supports stale-result rejection for async PSD plot workers. It does not prove
worker cancellation, long-running preprocessing performance, or memory leak behavior.

Preprocess plotter render query-source gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_data_query.py tests/unit/ui/preprocess/test_preprocess_plotter.py -q`
-> `25 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
-> `70 passed`。This supports service-backed `QueryStateCommand(query="data_lists",
include_objects=True)` as the shared render source for Preprocess panel and plotter refresh. The
controller data-list read remains only for query-unavailable mock / legacy fallback. It does not
prove plot visual quality, large-data plotting performance, or full preprocessing workflow UX.

Visualization failed-query trainer fallback gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_get_trainers_does_not_fallback_after_failed_query -q`
-> `1 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
-> `47 passed`。This supports `VisualizationPanel.get_trainers()` refusing stale controller trainers
after ApplicationService visualization query failure. It does not prove visualization UX acceptance,
interactive 3D rendering, or post-training desktop human verification.

SinglePlotWindow close cleanup gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_close_releases_current_figure_and_qt_widgets tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_creates tests/unit/ui/test_ui_components.py::TestSinglePlotWindow::test_has_figure_canvas -q`
-> `3 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestSinglePlotWindow tests/unit/ui/components/test_plot_figure_window.py tests/unit/ui/dialogs/test_dialogs_structure.py::TestDialogStructure::test_single_plot_window_init -q`
-> `19 passed`。This supports Matplotlib figure close and Qt canvas / toolbar cleanup for the base
plot dialog. It does not prove long-run memory trends, full visualization soak behavior, or human
desktop acceptance.

Saliency 2D canvas cleanup gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_close_releases_figure_and_canvas tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_replace_figure_releases_previous_canvas tests/unit/ui/test_visualization.py::TestSaliencyMapWidget::test_update_plot_no_eval tests/unit/ui/test_visualization.py::TestSaliencySpectrogramWidget::test_update_plot_no_eval tests/unit/ui/test_visualization.py::TestSaliencyTopographicMapWidget::test_update_plot_no_eval -q`
-> `5 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/components/test_plot_figure_window.py -q`
-> `61 passed`。This supports shared figure/canvas close and replacement cleanup for 2D saliency
views. It does not prove full saliency workflow UX, long-run visualization memory trends,
interactive desktop 3D render, or human desktop acceptance.

ConfusionMatrixWidget cleanup gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_none_releases_previous_canvas_and_children tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_creates tests/unit/ui/test_ui_components.py::TestConfusionMatrix::test_update_plot_no_data -q`
-> `3 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/test_ui_components.py::TestConfusionMatrix tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
-> `29 passed`。This supports figure/canvas cleanup for confusion matrix update / clear paths. It
does not prove full Evaluation tab UX, long-run memory trend behavior, or human desktop acceptance.

MetricsBarChart close cleanup gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_close_releases_figure_and_canvas tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_creates tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_update_plot_no_data tests/unit/ui/test_ui_components.py::TestMetricsBarChart::test_update_plot_layout_failure_is_not_logged_as_error -q`
-> `4 passed`；
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/test_ui_components.py::TestConfusionMatrix tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
-> `30 passed`。This supports close cleanup for the per-class metrics chart figure / canvas. It
does not prove full Evaluation tab UX, long-run memory trend behavior, or human desktop acceptance.

Data Interpretation review-row polish gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/integration/ui/test_product_walkthrough.py -q`
-> `27 passed`；
`QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
refreshed `artifacts/ui/data-interpretation-preview.png`,
`artifacts/ui/data-interpretation-remap.png`, and
`artifacts/ui/data-interpretation-replay.json`。The replay JSON records
`partial_visible_rows=[]` for both preview and remap `Review Summary` trees. This supports the
automated PyQt replay claim that the review summary no longer shows clipped rows in this fixture;
it does not prove mature import-wizard UX or Windows human desktop acceptance.

Data Interpretation selector-fit polish gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_label_selectors_fit_review_text tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_shows_label_carrier_matches tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_manual_label_target_mapping tests/unit/scripts/test_capture_data_interpretation_replay.py::test_apply_replay_review_choices_updates_event_role_selector -q`
-> `4 passed`；
`QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
refreshed the preview/remap screenshots and replay JSON. The artifact now shows compact visible
target labels such as `sub-01 run-2`, full `Needs review` selector text in the remap dialog, and
full backend `target_file=sub-01_task-mi_run-2_raw.fif` preserved in `review_choices` /
`label_apply.file_mapping`. This supports the captured fixture only; it does not certify every
real-data label carrier naming pattern.

Human-like clipped-row quality gate:
`QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
-> `21 passed`；
`QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
refreshed `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md` and screenshots。
The walkthrough quality review now fails on captured `partial_visible_rows`; latest artifact records
`15` checked table/tree widgets, `0` geometry findings, and `0` clipped-row findings. This supports
automated artifact quality gating only; it does not replace human Windows launcher / DPI /
dual-monitor verification.

Training updated refresh route gate:
`poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/training/test_training_panel.py -q`
-> `54 passed`。This supports the central coordinator route for `training_updated` refreshing
Training / Evaluation / Visualization and shared status from the TrainingPanel owner. It does not
complete full command-driven UI refresh coordination or remove observer/manual refresh paths.

目前 fast engineering artifact 狀態是：

- generated at: `2026-05-04 04:07:48 UTC+08:00`
- workspace: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- overall: `PASS`

`ai-assistant-open.png` 已接受 `(1684, 800)` product redesign approved baseline。最新
UI baseline capture 結果：

- `7 UI artifacts match approved references`
- `max mean diff 0.114`
- `max changed 0.66%`
- fast dashboard after assistant product audit follow-up: `PASS`

最新 fast dashboard summary：

- Ruff Lint：`PASS`
- Basedpyright：`PASS`，`0 errors, 0 warnings, 0 notes`
- Architecture Compliance：`PASS`
- Startup Smoke：`PASS`
- UI Baseline Capture：`PASS`
- UI Dialog Acceptance：`PASS`
- UI Unit Suite：`831 passed`
- Real-Data IO Integration：`31 passed, 8 warnings`

同輪或 supervisor final closure 已通過：

- `git diff --check`
- `poetry run ruff check .`
- `poetry run basedpyright`
- `poetry run mkdocs build --strict`
- `poetry run python tests/architecture_compliance.py`
- UI product / geometry gate：`121 passed`
- agent / backend command gate：`225 passed`
- backend + IO integration：`33 passed, 8 warnings`
- full pipeline integration：`70 passed, 4 warnings`
- LLM / local settings / script unit gate：`674 passed`
- deterministic tool-call eval refresh：commit `e5454c7 test: refresh agent eval artifact`
  tracked `artifacts/agent_evals/latest.json`

這些 closure gates 修正並覆蓋了先前 fast dashboard fail：

- local-disabled assistant startup 現在有 visible reason。
- confirmation transcript 不再暴露 raw tool names。
- montage apply 不再 bypass command surface。
- `run.py` assistant startup path 維持 local-only。
- UI baseline geometry 已穩定。
- UI unit legacy runtime expectations 已改成 remote switch fail-closed / active local deletion block。
- deterministic agent eval artifact 已刷新。

2026-05-05 UI command refresh coordinator / fallback guard follow-up:

- downstream command-result refresh scope:
  - `refresh_after_command()` now refreshes Evaluation / Visualization readiness when
    `CommandResult.changed_state` reports training / epoch / evaluation changes.
  - focused gate:
    `poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_application_capabilities.py -q`
    -> `15 passed`.
  - UI unit regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q`
    -> `933 passed`.
- observer refresh helper guard:
  - architecture compliance now fails new direct `_create_bridge(..., self.update_panel)` and
    `_create_bridge(..., self.refresh_from_observer)` panel call sites; simple observer refresh must
    use `BasePanel._create_refresh_bridge()`.
  - architecture compliance also fails new `import_finished` simple refresh bridges; import-finished
    handling must use a named callback for warnings or event-specific behavior.
  - `BasePanel.refresh_from_observer()` now delegates to `refresh_after_observer()`, which refreshes
    the event source panel plus aggregate info and assistant backend status.
  - latest event-scope follow-up maps known observer events through central changed-state scopes:
    `data_changed` from the DatasetPanel owner bridge refreshes Dataset / Preprocess / Training;
    `preprocess_changed` from the PreprocessPanel owner bridge refreshes Preprocess / Training /
    Visualization; `training_started` / `training_stopped` / `config_changed` / `history_cleared`
    from TrainingPanel callbacks refresh Training / Evaluation / Visualization. Secondary
    subscribers no-op to avoid duplicate refresh in full MainWindow context.
  - focused gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/core/test_base_panel.py tests/unit/ui/test_panel_event_bridges.py tests/unit/ui/training/test_training_panel.py tests/unit/ui/test_main_window_sync.py -q`
    -> `66 passed`.
  - architecture guard gate:
    `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
    -> `13 passed`.
- missing-result legacy refresh guard:
  - architecture compliance now distinguishes `result.failed` UI restore from `result is None`
    compatibility branches. Missing-result branches may not directly call panel-local refresh
    methods outside explicit `*_after_legacy_result` helpers.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
- navigation shared-status refresh:
  - `refresh_after_navigation()` now refreshes the selected workflow panel plus aggregate info and
    assistant backend status, keeping tab-switch refresh inside the shared coordinator boundary.
  - `refresh_after_navigation()` also has same-main-window re-entrancy protection, matching command
    and observer refresh safety behavior.
  - focused gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_refresh_coordinator.py tests/unit/ui/test_main_window_sync.py -q`
    -> `21 passed`.
- Dataset import-finished callback cleanup:
  - Successful legacy controller imports refresh through the `data_changed` simple refresh bridge;
    `import_finished` now only surfaces warning messages and avoids a duplicate Dataset panel
    refresh.
  - PreprocessPanel and TrainingPanel no longer subscribe to dataset `import_finished` for simple
    refresh; successful legacy imports refresh them once through dataset `data_changed`.
  - InfoPanelService no longer subscribes to dataset `import_finished`; aggregate info success
    refresh is owned by `data_changed` / `preprocess_changed`.
  - Latest aggregate-info follow-up:
    MainWindow now constructs `InfoPanelService(observe_controller_events=False)`, so product
    runtime aggregate info refresh is owned by the coordinator shared-status path instead of a
    second direct InfoPanelService observer bridge. Standalone / legacy InfoPanelService use can
    still observe controller events directly.
  - focused gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `65 passed`.
  - observer bridge gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_panel_event_bridges.py -q`
    -> `12 passed`.
  - info service gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/components/test_info_panel_service.py tests/integration/ui/test_e2e_qtbot.py::TestInfoService -q`
    -> unit `4 passed`, integration `2 passed`.
- TrainingPanel high-level callback shared-status refresh:
  - `training_started`, `config_changed`, `training_stopped`, and `history_cleared` now refresh
    aggregate info and assistant backend status after their event-specific UI updates.
  - `training_updated` remains a high-frequency live update path and is intentionally excluded.
  - focused gate:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py -q`
    -> `17 passed`.
- static / docs gates for these slices:
  - `git diff --check` -> pass.
  - `poetry run ruff check .` -> pass.
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.

This supports the claim that command-result refresh and mock / legacy fallback guardrails are
stronger than the first coordinator slice. It does not complete full command-driven UI refresh,
remove controller observer callbacks, prove Data Interpretation wizard maturity, or replace human
Windows desktop acceptance.

2026-05-05 agent mapped-tool ApplicationService boundary hardening:

- real `Study` mapped workflow tools no longer fall back to legacy real-tool execution when
  `execute_application_tool_command()` cannot construct an ApplicationService command from missing
  or unsafe arguments. Explicit UI-request tools such as `set_montage` remain on the UI
  confirmation request path.
- example covered: `apply_bandpass_filter` with missing low/high frequency while preprocessing is
  otherwise capability-enabled now returns a structured input failure and does not call the legacy
  tool.
- focused gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_mapped_tool_missing_params_does_not_use_legacy_tool -q`
  -> `1 passed`.
- related agent/tool gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `184 passed`.
- focused lint/type:
  `poetry run ruff check XBrainLab/llm/agent/controller.py tests/unit/llm/agent/test_controller.py`
  -> pass;
  `poetry run basedpyright XBrainLab/llm/agent/controller.py tests/unit/llm/agent/test_controller.py`
  -> `0 errors, 0 warnings, 0 notes`.
- Claim boundary: this hardens runtime safety for mapped tools. The formal local `121` case rerun is
  recorded in the release/thesis gate section below; neither slice proves long autonomous ChatPanel
  workflow or product acceptance.

2026-05-05 deterministic tool-call eval follow-up:

- 新增 `wrong-tool-temptation-apply-after-epoch` case：state 已有 validated safe Data
  Interpretation candidate，但 active session 已切 epoch / locked downstream state；使用者要求套用
  新資料解讀並誘惑 assistant 改 scan 新路徑時，expected behavior 是 blocked / no tool call，不可改叫
  `scan_source` 或其他替代工具硬推。
- deterministic runner：`poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  -> `118 / 118` pass。
- dashboard refresh：`poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
  -> `artifacts/agent_evals/dashboard.md`。
- focused gate：`poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py::test_deterministic_tool_call_eval_passes_and_writes_artifacts -q`
  -> `1 passed`。
- focused lint/type：`poetry run ruff check scripts/agent/evals/run_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py`
 -> pass；`poetry run basedpyright scripts/agent/evals/run_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py`
  -> `0 errors, 0 warnings, 0 notes`。
- Claim boundary at the time of this deterministic-only slice：local primary / fallback artifacts
  still needed rerun. This boundary is superseded by the next local 118-case rerun section, but the
  product-completion boundary remains unchanged.

2026-05-05 local 118-case rerun and stricter blocked-substitute scoring:

- Resource preflight：
  - model cache：`/mnt/d/workspace_v2/projects/lab/XBrainLab/XBrainLab/llm/core/models`
  - cache usage：`15.34 GB`；cache limit：`20.00 GB`；free disk 約 `158.36 GB`。
  - primary / fallback 已 cached，estimated download `0.00 GB`；沒有新增模型下載。
  - local rerun 使用 `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`，sequential 執行；fallback
    run 接近 16GB VRAM 上限，不能把這宣稱成長時間 parallel runtime capacity。
- Scorer / prompt / normalizer hardening：
  - blocked direct workflow command 可以由 verifier / capability policy 轉成 blocked response。
  - blocked intent 下的替代 tool（例如 reset / scan / configure）會保留為 tool call 並評為 failure。
  - prompt 會在 direct command blocked 時隱藏 substitute tools，只提供 blocked reason。
  - bad-load-path 類 cases 加入 absolute-path 指示：若 prompt 內有 absolute path，應呼叫 direct
    load / scan tool 並讓 backend 回 recoverable path failure，不可因路徑文字包含 `missing` /
    `bad` / `unknown` 就 ask clarification。
  - `reset_session` / `clear_session` local output variant 會 normalize 到 registered
    `clear_dataset` tool，並丟棄多餘 params。
- Focused validation：
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py::test_normalizes_workflow_command_aliases_to_registered_tools tests/unit/scripts/test_run_local_tool_call_eval.py::test_blocked_requested_step_substitute_tool_fails_score tests/unit/scripts/test_run_local_tool_call_eval.py::test_blocked_requested_direct_tool_is_scored_as_blocked_response -q`
    -> `3 passed`。
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py tests/unit/llm/agent/test_tool_call_normalizer.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> pass。
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py tests/unit/llm/agent/test_tool_call_normalizer.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/scripts/test_run_local_tool_call_eval.py`
    -> `0 errors, 0 warnings, 0 notes`。
- Full local reruns：
  - `timeout 3600s env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 160 --output-dir artifacts/agent_evals/local_primary`
    -> `microsoft/Phi-4-mini-instruct` `118 / 118`。
  - `timeout 3600s env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 160 --output-dir artifacts/agent_evals/local_fallback`
    -> `microsoft/Phi-3.5-mini-instruct` `118 / 118`。
  - `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
    -> dashboard refreshed at `artifacts/agent_evals/dashboard.md`。
- Post-change gates：
  - `git diff --check` -> pass。
  - `timeout 300s poetry run ruff check .` -> pass。
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`。
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q` ->
    `100 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `3 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py -q`
    -> `530 passed`。
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`。
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。
- Claim boundary：this supports the 118-case local tool-call benchmark claim for the saved suite.
  It does not prove Windows human desktop acceptance, mature import wizard UX, MCP HTTP /
  long-running automation, or full product completion. The apply-lock case may still parse as a
  direct blocked `apply_interpretation` command; the supported claim is that verifier / capability
  policy blocks it and unsafe substitute tools are no longer scored as pass.

2026-05-05 Data Interpretation review summary UI:

- Product/UI change:
  - `DataInterpretationPreviewDialog` no longer uses a plain text review dump for warnings,
    confirmations, blocked reasons, downstream impact, recipe trace, or format boundary.
  - The dialog now shows a structured `Review Summary` table with `Item`, `Status`, and
    `What it means` columns.
  - Visible workflow copy is now `Select source | Scan result | Preview | Confirm | Apply | Save recipe`.
  - `capture_data_interpretation_replay.py` writes `review_summary_rows` into
    `artifacts/ui/data-interpretation-replay.json`.
- Focused TDD gate:
  - Initial targeted dialog test failed because the dialog had no `review_tree` and still exposed
    `review_text`.
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `9 passed`.
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py -q`
    -> `21 passed`.
- UI-observable artifacts:
  - `timeout 300s xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; refreshed `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-applied.png`, and
    `artifacts/ui/data-interpretation-replay.json`.
  - `timeout 420s xvfb-run -a poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> failed with WSLg / Wayland maximized-state protocol error; this is not accepted as evidence.
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`; refreshed consolidated artifacts with `status=passed`,
    `required_phase_count=26`, `observed_phase_count=26`, `screenshot_count=20`, and
    `human_desktop_acceptance=not performed`.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
- Claim boundary: this supports automated UI-observable Data Interpretation wizard review polish.
 It does not prove full mature import wizard completion, Windows launcher click-through, dual
  monitor / DPI behavior, XDF / LSL stream selection, complex MAT/GDF anchor reconciliation, or
  real-data manual certification.

2026-05-05 Dataset table fit and data-entry routing follow-up:

- Product/UI change:
  - Data Interpretation preview dialog tables now use viewport-scaled interactive columns + elide
    behavior so metadata, label/event, and recipe trace tables fill the dialog panel without
    horizontal overflow. A show-time refit hook corrects first-render widths after Qt layout
    finishes.
  - `Review Summary` keeps structured rows but uses lower-contrast dark alternating rows and theme
    palette colors instead of high-contrast black/white striping.
  - Dataset panel table keeps columns interactive, records viewport/header width evidence, and
    proportionally scales all columns so loaded rows fill the main panel in both wide and narrow
    layouts.
  - Dataset visible text now distinguishes recording events (`Events (n)`) from external labels
    (`Labels (n)`) without using success-green coloring for external labels.
  - 2026-05-06 wizard selector polish keeps backend values such as `trial_type` in recipe choices
    but displays label-carrier selector text as `Trial type` / `Onset`; the `Review Summary`
    alternate row color was lowered to `#232323` to reduce striping.
  - The label-carrier table column weights were adjusted so common format names such as
    `BIDS events` remain visible in the product-width dialog while still filling the panel.
- Agent/eval change:
  - General data-entry wording such as `Load ...` and folder import requests now route to
    Data Interpretation `scan_source`; explicit legacy/direct compatibility wording still routes to
    `load_data`.
  - BIDS path / prompt hints are normalized toward `source_hint=bids`.
- Focused evidence:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py -q`
    -> previous slice `23 passed`; latest viewport-refit regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_table_sizing.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `29 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `3 passed`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; replay JSON records Dataset table headers, rows, resize modes, and column widths.
    Latest replay also records preview/remap dialog tree geometry for metadata, label carriers,
    event roles, and Review Summary: `header_length`, `viewport_width`, `column_widths`,
    `horizontal_scrollbar_max`, and `text_elide_mode`.
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> failed once with the existing WSLg / Wayland maximized-state protocol error; not used as
    acceptance evidence.
  - `artifacts/ui/data-interpretation-replay.json` shows interactive resize modes,
    `header_length == viewport_width`, proportional column widths
    `[321, 113, 150, 75, 86, 99, 150]`, and rows containing `Events (6)` / `Labels (4)`.
  - Latest dialog geometry evidence shows preview/remap metadata, label carriers, events, and review
    summary all with `horizontal_scrollbar_max=0`; example review summary widths are
    `[179, 173, 620]` with `header_length=972` and `viewport_width=972`.
  - Refreshed screenshots:
    `artifacts/ui/data-interpretation-preview.png`,
    `artifacts/ui/data-interpretation-remap.png`, and
    `artifacts/ui/data-interpretation-applied.png`.
  - Latest human-like walkthrough refresh remains passed: `26 / 26` phases, `20` screenshots,
    table geometry checked for `15` widgets with `0` findings, and human desktop acceptance still
    explicitly not performed.
  - Deterministic eval and cached local primary / fallback evals were refreshed at
    `artifacts/agent_evals/dashboard.md`; deterministic, primary, and fallback all remain
    `118 / 118`, with local roles repeated `3` times.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
- Claim boundary: this supports the automated replay condition that Dataset table columns fill the
  main panel and general import language routes through Data Interpretation. It does not prove
  mature import wizard completion, Windows human desktop acceptance, or long-running assistant /
  MCP workflow closure.

2026-05-05 Recipe reload comparison review:

- Product/UI change:
  - Reloaded recipe preview now compares saved recipe selections against the current rescan before
    validation.
  - Backend preview payload exposes `recipe_reload_summary.diff_rows` with user-facing `EEG files`,
    `Label carriers`, and `Saved choices` rows.
  - Data Interpretation wizard renders those rows in `Review Summary` instead of showing raw recipe
    data or only a generic reapplied message.
- TDD / focused evidence:
  - Backend red test initially failed because `build_interpretation_preview()` did not accept
    recipe context.
  - UI red test initially failed because `Review Summary` did not show `EEG files` reload rows.
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_review.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
    -> `16 passed`.
  - Focused `ruff check` on touched backend/UI/test files -> pass.
  - Focused `basedpyright` on touched backend/UI/test files -> `0 errors, 0 warnings, 0 notes`.
- UI-observable artifact:
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`.
  - `artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png` and
    `human-like-walkthrough.json` now show recipe reload rows for `EEG files`, `Label carriers`,
    and `Saved choices`.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `105 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
    -> `12 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
- Claim boundary: this supports automated recipe reload comparison visibility. It does not prove
  full recipe diff editing, complex conflict resolution, Windows human desktop acceptance, or mature
  import wizard closure.

2026-05-05 Recipe reload missing selected EEG blocker:

- Product/backend change:
  - If a reloaded recipe selects an EEG file that the current rescan cannot find, the interpretation
    candidate now records a blocked reason before apply.
  - Matching accepts exact path or basename so a moved but otherwise identical source tree can still
    be reviewed without false blocking.
- Focused evidence:
  - Unit red test initially failed because missing selected EEG files produced no blocked reason.
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_blocks_missing_saved_eeg_file -q`
    -> `4 passed`.
  - Focused `ruff check` on touched candidate/workflow tests -> pass.
  - Focused `basedpyright` on touched candidate/workflow tests -> `0 errors, 0 warnings, 0 notes`.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `106 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `4 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
- Claim boundary: this supports early blocking for missing saved selected EEG files. It does not yet
  resolve label carrier remapping, renamed-file ambiguity, complex anchor reconciliation, or mature
  recipe conflict editing.

2026-05-05 Recipe reload missing label/event carrier blocker:

- Product/backend change:
  - Reloaded recipes now preserve required saved label/event carriers in candidate choices.
  - If a required saved carrier is absent from the current scan, validation becomes `blocked`
    before apply, preventing silent external-label loss.
  - Matching accepts exact path or basename, consistent with saved EEG file matching.
- Focused evidence:
  - Red tests initially showed `choices_from_import_recipe()` did not expose required carriers,
    candidate validation did not block missing carriers, and reload validation stayed
    `needs_confirmation`.
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_recipe.py::test_choices_from_import_recipe_recreates_review_choices tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_blocks_missing_saved_label_carrier -q`
    -> `6 passed`.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `107 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `5 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
- Claim boundary: this supports early blocking for missing saved label/event carriers. It does not
  implement carrier remapping, renamed-carrier resolution, or anchor reconciliation UI.

2026-05-05 Recipe reload backend label-carrier remap:

- Product/backend change:
  - Candidate building now accepts explicit `label_carrier_remap` choices from saved carrier path/name
    to current scan replacement carrier.
  - Remapped carriers preserve saved label field, anchor, time model, granularity, and role choices.
  - `required_label_carriers` are checked after remap, so a deliberate replacement clears the
    missing-carrier blocker.
- Focused evidence:
  - Initial red tests showed remap still blocked on the old carrier and integration validation stayed
    `blocked`.
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py::test_build_interpretation_candidate_remaps_saved_label_carrier_choices tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_label_carrier_remap -q`
    -> `2 passed`.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `108 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
    -> `6 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
- Claim boundary at this backend slice: backend/headless remap truth was supported; user-facing
  selector evidence is covered by the following wizard remap selector slice. Complex anchor
  reconciliation remains out of scope.

2026-05-05 Recipe reload wizard EEG-file / label-carrier remap selector:

- Product/UI change:
  - Reload preview now exposes candidate replacement EEG files and label/event carriers for missing
    saved recipe paths.
  - A blocked reload dialog with complete remap choices enables `Apply Remap`, shows user-facing
    remap copy, and returns `choices.eeg_file_remap` / `choices.label_carrier_remap`.
  - If multiple candidate replacement EEG files exist, Apply remains disabled until the user picks a
    replacement; single-candidate remaps are selected automatically.
  - Dataset action re-previews and re-validates the merged recipe choices before applying the
    remapped candidate.
  - Data Interpretation replay now captures `artifacts/ui/data-interpretation-remap.png` and
    `ui_state.remap_dialog`.
- Focused evidence:
  - `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_candidate.py tests/unit/backend/application/test_data_interpretation_review.py tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_eeg_file_remap tests/integration/backend/test_application_service_workflow.py::test_reload_recipe_accepts_explicit_label_carrier_remap tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_eeg_file_remap tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_requires_each_remap_choice tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_label_carrier_remap tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_repreviews_blocked_eeg_file_remap tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_reload_interpretation_recipe_repreviews_blocked_label_carrier_remap -q`
    -> `16 passed`.
  - `poetry run ruff check ...` on touched UI/script/test files -> pass.
  - `poetry run basedpyright ...` on touched product files -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
- Post-change gates:
  - `git diff --check` -> pass.
  - `timeout 300s poetry run ruff check .` -> pass.
  - `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `109 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `473 passed`.
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q` -> `7 passed`.
- UI-observable artifact:
  - `artifacts/ui/data-interpretation-remap.png` shows EEG file and label carrier replacement
    selectors plus `Apply Remap` without contradictory blocked copy.
  - `artifacts/ui/data-interpretation-applied.png` shows the loaded Dataset table filling the main
    panel with neutral `Events (6)` / `Labels (4)` text.
- Claim boundary: this supports simple renamed EEG file / label-carrier replacement paths in
  automated PyQt replay. It is not a complete recipe conflict editor, complex anchor reconciliation
  UX, or human Windows desktop acceptance.

2026-05-05 MCP stdio adapter session boundary:

- Adapter change:
  - `MCPServer` now assigns a stable per-server stdio session id.
  - `tools/call` structuredContent includes `adapter` metadata:
    `mode=headless_mcp_stdio`, `transport=stdio`, `session_id`, and a `ui_refresh` object with
    `supported=False`.
  - stdio `train` now respects backend capability / precondition ordering before the long-running
    boundary: unready training returns backend readiness reasons such as
    `Generate datasets before training`, while enabled long-running training returns
    `long_running_job_required` with a `job_boundary` object indicating `http_job_api`, progress,
    and cancel are not available yet.
  - MCP tool output schema exposes optional `adapter` property through the same automation schema
    source.
  - `scripts/dev/capture_mcp_stdio_walkthrough.py` summary / Markdown now includes adapter mode,
    transport, session stability, UI refresh boundary, train result boundary, and whether the job
    boundary was reached.
- Validation:
  - Initial focused tests for this correction failed because stdio `train` returned
    `long_running_job_required` even when backend capability was disabled by missing data /
    dataset / model / training settings.
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py::test_stdio_mcp_reports_precondition_before_long_running_job_boundary tests/unit/mcp/test_server.py::test_stdio_mcp_blocks_enabled_long_running_commands_until_job_api_exists -q`
    -> `2 passed`.
  - `poetry run pytest --capture=sys tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py -q`
    -> `8 passed`.
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
    -> `10 passed`.
  - `poetry run ruff check XBrainLab/mcp/server.py XBrainLab/backend/application/automation.py scripts/dev/capture_mcp_stdio_walkthrough.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
    -> pass.
  - `poetry run basedpyright XBrainLab/mcp/server.py XBrainLab/backend/application/automation.py scripts/dev/capture_mcp_stdio_walkthrough.py tests/unit/mcp/test_server.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
    -> `0 errors, 0 warnings, 0 notes`.
  - `timeout 180s poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp`
    -> refreshed `artifacts/mcp/stdio-walkthrough.json` / `.md`.
  - `git diff --check` -> pass.
  - `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
- Claim boundary: this proves stdio MCP calls expose an explicit headless session/UI-refresh
  boundary, preserve backend readiness errors before job-boundary errors, and refuse synchronous
  long-running training while still using ApplicationService. It does not implement Streamable
  HTTP, authorization, long-running job progress/cancel/recovery, or desktop UI control
  certification.

2026-05-05 backend command boundary cleanup 另有可重跑 focused evidence：

- `TrainingCommandService` 承接 `configure_training`、`train`、`stop_training`、
  `clear_training_history` 和 reset-time training config clear。
- `DatasetGenerationCommandService` 承接 `generate_dataset`、`clear_datasets`、split config、
  split audit、rollback、split summary 和 dataset cleanup。
- `LifecycleCommandService` 承接 `reset_preprocess`、`reset_session`、`new_session`、
  downstream rollback 和 reset-time dependent-state clear。
- `DataCompatibilityCommandService` 承接舊 `load_data`、`attach_labels`、`import_labels` 和
  label helper，並維持 Data Interpretation recipe trace update。
- `DataTableCommandService` 承接 `update_metadata`、`apply_smart_parse` 和 `remove_files`，
  並維持 loaded-data table mutation diagnostics。
- `PreprocessCommandService` 承接 preprocessing operations 和 `create_epoch`，並維持
  `set_montage` UI confirmation boundary。
- `StateSnapshotService` / `QueryStateCommandService` 承接 state snapshot assembly 和
  `query_state` diagnostics，並維持 agent `query_state` tool surface。
- UI runtime bypass cleanup 覆蓋 Dataset direct file import 和 Preprocess reset：successful
  `LoadDataCommand` / `ResetPreprocessCommand` 不再落回 controller mutation，fallback 只保留給
  command adapter unavailable 的 mock / legacy `None` 情境。
- Legacy raw-loader boundary cleanup 覆蓋 `DatasetPanel.apply_loader()`：real `Study`
  runtime 會拒絕 direct `loader.apply(study)` 並提示使用 Data Interpretation workflow；mock /
  legacy-only path 仍保留 `_apply_legacy_loader()` adapter。Architecture compliance 新增 direct
  loader apply guard，並通過 focused unit test。
  Follow-up broad UI unit regression also passed:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q` -> `937 passed`.
- Training sidebar bypass cleanup 覆蓋 destructive dataset cleanup 和 Clear History：
  successful `ClearDatasetsCommand` / `ClearTrainingHistoryCommand` 不再落回 training controller
  mutation，Clear History 現在也有 user confirmation。
- Data Interpretation format boundary cleanup 覆蓋 focused `data_interpretation_formats.py`
  module；GDF / BIDS events / XDF-LSL capability 行為有直接 unit coverage，既有 scan capability
  boundary regression 仍通過。
- Data Interpretation metadata boundary cleanup 覆蓋 focused `data_interpretation_metadata.py`
  module；BIDS metadata resolution、filename-rule needs-confirmation、BIDS summary 和 recipe
  metadata rehydration 有直接 unit coverage，既有 scan / recipe reload regression 仍通過。
- Data Interpretation recipe boundary cleanup 覆蓋 focused `data_interpretation_recipe.py` module；
  `ImportRecipe` from-dict / write-load / applied interpretation builder 有直接 unit coverage，既有
  recipe save / reload regression 仍通過。
- Data Interpretation label carrier boundary cleanup 覆蓋 focused
  `data_interpretation_label_carriers.py` module；BIDS events user choices、choice-key
  normalization 和 existing recipe/state label-carrier regressions 仍通過。
- Data Interpretation review boundary cleanup 覆蓋 focused `data_interpretation_review.py`
  module；candidate preview serialization、safe / needs-confirmation / blocked decision boundary
  和 existing preview / validation command regressions 仍通過。
- Data Interpretation scanner boundary cleanup 覆蓋 focused `data_interpretation_scan.py`
  module；BIDS file / label / metadata discovery、XDF blocked boundary、explicit file source hint
  和 existing scan / preview / recipe regressions 仍通過。
- Data Interpretation candidate boundary cleanup 覆蓋 focused
  `data_interpretation_candidate.py` module；metadata override、event/class choices、
  label-carrier recipe trace、empty selection blocking 和 existing scan / preview / recipe
  regressions 仍通過。
- Data Interpretation session-state boundary cleanup 覆蓋 focused
  `data_interpretation_state.py` module；lifecycle stores、latest-id resolver、snapshot、clear、
  applied interpretation / recipe resolver 和 post-load label-import recipe state update 有直接 unit
  coverage，既有 Data Interpretation service regression 仍通過。Full slice gate：backend
  application regression -> `99 passed`；backend integration -> `3 passed`；agent/tool regression ->
  `468 passed`；agent integration -> `7 passed`；ruff / basedpyright / architecture compliance /
  MkDocs strict / diff check passed。
- Agent legacy data-entry prompt downgrade 覆蓋 Empty / Data Loaded / Preprocessed stage prompt
  和 Context Assembler policy intersection；`load_data` / `attach_labels` 不再作為 primary stage
  tools 曝光，backend capability policy 也不能單獨把 stage-filtered legacy tool 放回 prompt。
  Focused evidence：`tests/unit/llm/test_pipeline_state.py`、
  `tests/unit/llm/agent/test_assembler_stage.py`、`tests/unit/llm/test_confidence.py`
  -> `46 passed`；broader agent/tool gate -> `468 passed`；agent integration -> `7 passed`；
  backend application regression -> `96 passed`；backend integration -> `3 passed`；
  ruff / basedpyright / architecture compliance / MkDocs strict / diff check also passed。
- RAG prompt cleanup 覆蓋 bundled gold-set ingestion、BM25 keyword index 和 dense retriever
  formatting：含 `load_data` / `attach_labels` / `import_labels` 的 legacy examples 會被排除，
  即使舊 Qdrant collection 已存在也不會進 prompt。Focused evidence：
  `tests/unit/llm/rag/test_example_policy.py` -> `5 passed`；broader RAG / assembler gate：
  `tests/unit/llm/rag/test_example_policy.py tests/unit/test_llm_backend.py tests/unit/llm/agent/test_assembler_stage.py`
  -> `31 passed`。
- Automation / MCP legacy compatibility metadata cleanup 覆蓋
  `AutomationCommandSpec` 和 MCP `tools/list` `x_xbrainlab` metadata；`load_data` /
  `attach_labels` / `import_labels` 仍可相容呼叫，但 schema 會標示 `legacy_compatibility=True`、
  `primary_workflow=False` 並列出 Data Interpretation preferred commands。Focused evidence：
  `tests/unit/backend/application/test_automation.py` plus MCP stdio/client config regressions
  -> `12 passed`；full backend application regression -> `97 passed`；backend integration ->
  `3 passed`；agent/tool regression -> `468 passed`；agent integration -> `7 passed`；MCP
  integration -> `3 passed`；ruff / basedpyright / architecture compliance / MkDocs strict /
  diff check passed。
- focused test-first 紅燈先確認缺少
  `XBrainLab.backend.application.training_service` /
  `XBrainLab.backend.application.dataset_generation_service` /
  `XBrainLab.backend.application.lifecycle_service` /
  `XBrainLab.backend.application.data_compatibility_service` /
  `XBrainLab.backend.application.data_table_service` /
  `XBrainLab.backend.application.preprocess_service` /
  `XBrainLab.backend.application.state_service`，再以 service unit tests 驗證 model
  holder、training option snapshot、start / stop、history cleanup diagnostics、config reset
  notification、dataset split config、audit blocking、rollback、cleanup diagnostics、reset
  notification、dependent-state clearing、legacy load failure mapping、attach labels、label import
  recipe update、metadata skipped row reporting、smart parse normalization、remove-count delta、
  standard preprocess batching、core preprocessing operations、epoch creation、montage boundary、
  state snapshot construction、query diagnostics、smart-filter suggestions、Dataset direct import
  service-success no-fallback、Preprocess reset service-success no-fallback、Training re-split
  cleanup service-success no-fallback、Clear History service-success no-fallback 和 format
  capability / metadata resolution / recipe serialization / label carrier planner / review validator /
  scanner / candidate module boundaries。
- regression gate 已通過 `tests/unit/backend/application`、`tests/integration/backend`、
  `tests/unit/llm/agent tests/unit/llm/tools` 和 `tests/integration/agent`。
- UI runtime bypass slice gate 另通過：
  `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/dataset/test_panel.py -q`
  (`85 passed`)、`poetry run ruff check .`、`poetry run basedpyright`
  (`0 errors, 0 warnings, 0 notes`)、`poetry run python tests/architecture_compliance.py`
  (`Architecture compliant!`)、`poetry run mkdocs build --strict`（既有 Material warning）和
  `git diff --check`。
- Training sidebar cleanup slice gate 另通過：
  `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
  (`40 passed`)、`poetry run ruff check .`、`poetry run basedpyright`
  (`0 errors, 0 warnings, 0 notes`)、`poetry run python tests/architecture_compliance.py`
  (`Architecture compliant!`)、`poetry run mkdocs build --strict`（既有 Material warning）和
  `git diff --check`。
- Training start long-running confirmation slice gate 覆蓋 Start Training button 的 backend
  autonomy boundary：當 `train` capability requires confirmation 時會顯示使用者語言 confirmation，
  拒絕後不執行 command / controller fallback。Evidence：
  `artifacts/ui/training-start-confirmation/training-start-confirmation-dialog.png`、
  `.json`、`.md`；focused UI gate `42 passed`；backend application regression -> `97 passed`；
  backend integration -> `3 passed`；agent/tool regression -> `468 passed`；agent integration ->
  `7 passed`；ruff / basedpyright / architecture compliance / MkDocs strict / diff check passed。
  這是 automated Qt replay，不是 human desktop acceptance。
- Backend command-gate confirmation cleanup 覆蓋 long-running `train` 不再只靠 UI/agent 外層
  confirmation：unready train 仍回 precondition，backend-ready unconfirmed train 回
  `confirmation_required` 且不呼叫 training controller；confirmed train 才執行。Focused evidence：
  backend confirmation tests -> `2 passed`；agent / application surface / UI confirmation adapters ->
  `4 passed`；backend application suite -> `102 passed`；agent/tool suite -> `470 passed`；
  training UI focused suite -> `42 passed`；backend integration -> `3 passed`；agent integration ->
  `7 passed`；ruff / basedpyright / architecture compliance / MkDocs strict / diff check passed。
- Dataset source-entry UI options slice gate 覆蓋 Data Interpretation source type visibility：
  Dataset sidebar 現在有 `Interpret Data Source`、`Interpret Folder / BIDS` 和
  `Reload Import Recipe` 三個 source entry，folder/BIDS 和 recipe reload 走 Data Interpretation
  command path。Evidence：`artifacts/ui/data-source-entry-options/data-source-entry-options.png`、
  `.json`、`.md`；focused UI gate `63 passed`；backend application regression -> `99 passed`；
  backend integration -> `3 passed`；agent/tool regression -> `468 passed`；agent integration ->
  `7 passed`；ruff / basedpyright / architecture compliance / MkDocs strict / diff check passed。
  這是 automated Qt sidebar replay，不是 human desktop acceptance。
- Recipe reload capability gate slice 覆蓋 `Reload Import Recipe` UI action 的 capability source：
  recipe reload 現在讀 `reload_interpretation_recipe` capability，而不是 scan-source gate。Focused
  regression 初始紅燈顯示 disabled reload capability 仍進入 file dialog，實作後 focused gate
  `2 passed`；focused DatasetAction/sidebar gate -> `58 passed`；ruff / basedpyright /
  architecture compliance / MkDocs strict / diff check passed。
- Apply interpretation raw-edit boundary slice gate 覆蓋 Data Interpretation apply 的 active
  pipeline mutation policy：已有 epoch / generated dataset / trainer / locked raw data 時，
  `apply_interpretation` capability 會 blocked，並且 `ApplyInterpretationCommand` 不呼叫
  `dataset.import_files()` side effect。Focused evidence：
  `tests/unit/backend/application/test_application_service.py::test_apply_interpretation_blocks_after_epoch_without_import_side_effect`
  初始紅燈 `available is True`，實作後 focused gate `2 passed`；backend application regression ->
  `100 passed`；backend integration -> `3 passed`；agent/tool regression -> `468 passed`；agent
  integration -> `7 passed`；ruff / basedpyright / architecture compliance / MkDocs strict /
  diff check passed。
- Data Interpretation format boundary slice gate 另通過：
  `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
  (`5 passed`)、`poetry run pytest --capture=sys tests/unit/backend/application -q`
  (`80 passed`)、`poetry run ruff check .`、`poetry run basedpyright`
  (`0 errors, 0 warnings, 0 notes`)、`poetry run python tests/architecture_compliance.py`
  (`Architecture compliant!`)、`poetry run mkdocs build --strict`（既有 Material warning）和
  `git diff --check`。
- Data Interpretation metadata boundary slice gate 另通過：
  `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_preview_validate_requires_confirmation tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
  (`11 passed`)、`poetry run pytest --capture=sys tests/unit/backend/application -q`
  (`84 passed`)、`poetry run ruff check .`、`poetry run basedpyright`
  (`0 errors, 0 warnings, 0 notes`)、`poetry run python tests/architecture_compliance.py`
  (`Architecture compliant!`)、`poetry run mkdocs build --strict`（既有 Material warning）和
  `git diff --check`。
- Data Interpretation recipe boundary slice gate 另通過：
  `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_recipe_save_and_reload_rescans_without_apply tests/unit/backend/application/test_application_service.py::test_data_interpretation_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
  (`14 passed`)、`poetry run pytest --capture=sys tests/unit/backend/application -q`
  (`87 passed`)、`poetry run ruff check .`、`poetry run basedpyright`
  (`0 errors, 0 warnings, 0 notes`)、`poetry run python tests/architecture_compliance.py`
  (`Architecture compliant!`)、`poetry run mkdocs build --strict`（既有 Material warning）和
  `git diff --check`。
- Data Interpretation label carrier boundary slice gate 另通過：
  `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_label_carriers.py tests/unit/backend/application/test_data_interpretation_recipe.py tests/unit/backend/application/test_data_interpretation_metadata.py tests/unit/backend/application/test_data_interpretation_formats.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_choices_flow_into_recipe tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth -q`
  (`16 passed`)、`poetry run pytest --capture=sys tests/unit/backend/application -q`
  (`89 passed`)、`poetry run ruff check .`、`poetry run basedpyright`
  (`0 errors, 0 warnings, 0 notes`)、`poetry run python tests/architecture_compliance.py`
  (`Architecture compliant!`)、`poetry run mkdocs build --strict`（既有 Material warning）和
  `git diff --check`。
- 這支撐 backend handler boundary cleanup；不能擴張成 product-complete、Windows human
  acceptance、完整 Data Interpretation wizard 或 MCP long-running training claim。

仍未完成的 evidence：

- Windows Desktop launcher 真人 click-through；目前已有 automated command walkthrough，不等於
  人工桌面驗收。
- true local LLM ChatPanel 已有一輪真模型 UI 回覆 walkthrough、一輪單步 `query_state`
  tool-command walkthrough，以及兩 turn workflow walkthrough；長時間 tool-command chain 仍未完成。
- local LLM primary / fallback tool-call runner 已有 `121` thesis-candidate cases x `3`
  score report；primary / fallback 都是 `121 / 121` pass，dashboard 已列 model comparison、
  metric pass rate、case family pass rate 和 failure taxonomy。這支撐 tool-call benchmark
  evidence，但不代表 launcher / UI 產品 walkthrough 已完成。
- external EEG dataset experiment / statistical reporting 只是 pipeline support，不是 thesis 主評分。

data pipeline 文件驗證時也重跑：

- `poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
- tiny E2E pipeline smoke
  - `2 passed in 5.89s`

agent 架構文件整理時也跑：

- `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/chat/test_chat_panel.py -q`
  - `157 passed in 7.61s`

2026-05-02 UI / Agent command surface unification 後新增一組 product engineering gate：

- backend command contract：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `9 passed`
- facade/headless compatibility：
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `44 passed`
- agent command surface / controller：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `318 passed`
- UI readiness / chat / panel unit suite：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `807 passed`
- ApplicationService low-mock backend workflow:
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `2 passed`

這組 gate 只代表 backend policy / UI readiness / agent command surface 的工程可信度；
它仍不是 thesis-grade tool-call evaluation。

2026-05-04 Backend ApplicationService boundary cleanup 新增一組 architecture gate：

- Data Interpretation command coordinator / apply service focused gate：
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/backend/application/data_interpretation_apply.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py`
  - pass
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/backend/application/data_interpretation_apply.py tests/unit/backend/application/test_data_interpretation_service.py`
  - `0 errors, 0 warnings, 0 notes`
- backend command contract:
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `54 passed`
- backend integration:
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
  - `3 passed`
- agent command surface / controller:
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `466 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
  - `7 passed`
- static / docs / architecture:
  - `timeout 300s poetry run ruff check .`
  - pass
  - `timeout 300s poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `timeout 300s poetry run python tests/architecture_compliance.py`
  - `Architecture compliant!`
  - `timeout 300s poetry run mkdocs build --strict`
  - pass with existing MkDocs Material warning
  - `timeout 120s git diff --check`
  - pass

這組 gate 支撐「Data Interpretation lifecycle 已從 `ApplicationService` 拆到 focused service，
reviewed apply side effects 已拆到 apply service，且 UI / agent / MCP-facing command contract
沒有回歸」。它不能支撐整個 backend architecture closure；後續 cleanup 已另外拆出
analysis、training、dataset generation、lifecycle、data compatibility、data-table、preprocess /
epoch 和 state/query handlers。這仍不能支撐 product completion，因為 UI / agent / MCP
runtime 旁路、import wizard maturity、Windows human acceptance 和 long-running local assistant
verification 仍要另外驗證。

2026-05-05 Analysis command boundary cleanup 新增一組 architecture gate：

- test-first focused gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py -q`
  - 初始紅燈 `ModuleNotFoundError: XBrainLab.backend.application.analysis_service`
- analysis service focused/static gate：
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py`
  - pass
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py`
  - `0 errors, 0 warnings, 0 notes`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py -q`
  - `46 passed`
- backend command contract:
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `56 passed`
- backend / agent regression:
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
  - `3 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `466 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
  - `7 passed`
- static / docs / architecture:
  - `timeout 300s poetry run ruff check .`
  - pass
  - `timeout 300s poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `timeout 300s poetry run python tests/architecture_compliance.py`
  - `Architecture compliant!`
  - `timeout 300s poetry run mkdocs build --strict`
  - pass with existing MkDocs Material warning
  - `timeout 120s git diff --check`
  - pass

這組 gate 支撐「`evaluate`、`visualize`、`saliency` 和 confirmed `apply_montage` 已從
`ApplicationService` 拆到 focused analysis service，且 UI / agent-facing command contract 沒有
回歸」。它不能支撐 full visualization UI render、interactive 3D / PyVista desktop acceptance、
training lifecycle closure 或 complete backend architecture closure。

### 2026-05-02 Chat product-flow blocker

先前 gate 漏掉的 product blocker：

- normal user text path 沒有被產品級測試覆蓋。`hello` 這種不需要 tool 的普通輸入，
  必須驗證 user bubble、assistant bubble、非空內容、processing 回 idle。
- empty model response 先前可被視為「生成完成」，但 UI 沒有 visible fallback。
- tool-only successful response 可能隱藏 JSON 並直接 finalize，導致成功執行但沒有使用者可見回饋。
- worker error / local unavailable 需要在 chat transcript 中形成可理解 message，而不是只改 status。
- UI baseline 只能檢查 pixels 是否接近 approved reference，不能判斷介面是否已產品級、也不能抓
  no-response。

新的 relevant chat gate 必須至少包含：

```bash
timeout 240s scripts/dev/run_ui_pytest.sh \
  tests/unit/ui/chat/test_chat_panel.py \
  tests/unit/ui/components/test_agent_manager.py -q

timeout 180s poetry run pytest --capture=sys \
  tests/unit/llm/agent/test_controller.py \
  tests/unit/llm/agent/test_worker.py -q
```

這些測試要證明：

- normal chat response product flow 有可見 assistant bubble。
- empty response 會變 visible fallback error。
- worker error 會變 visible error。
- local unavailable first-open 會顯示原因。
- ChatPanel 結構包含簡潔 header、單句 workflow guidance、empty state、composer controls、
  disabled Retry、窄 dock bubble wrapping。

broader UI / LLM suite 仍需要跑，但不能取代上述 product-flow gate。

本輪修復後的驗證結果：

- `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `55 passed`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py -q`
  - `75 passed`
- `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `817 passed`
- `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- `timeout 120s poetry run mkdocs build --strict`
  - passed
- `timeout 60s git diff --check`
  - passed
- `timeout 360s poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS`
  - Basedpyright `0 errors`
  - UI baseline capture `PASS`

2026-05-02 product delivery UI / backend / agent slice 新增驗證：

- assistant product click-through / layout + synthetic pipeline walkthrough：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `2 passed`
- combined UI product gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
- combined agent / backend command gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/test_application_surface.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `95 passed`
- real-data IO integration:
  - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
- selected tiny pipeline smoke:
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q`
  - `2 passed`
- launcher startup smoke:
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` appeared before the expected GUI timeout.

這批測試支撐「assistant product layout、visible chat failure handling、主要 UI button path、
backend command adapter、agent mapped command result」的工程狀態。它仍不是人工 Windows
launcher click-through，也不是真 local model 長時間 UI walkthrough。

2026-05-02 local runtime first-run / query command / thesis protocol slice 新增驗證：

- local runtime first-run dialog / disabled state / cache-ready state：
  - `tests/unit/ui/dialogs/test_local_runtime_first_run_dialog.py`
  - `tests/unit/ui/components/test_agent_manager.py`
- service-backed query commands：
  - `EvaluateCommand`
  - `VisualizeCommand`
  - `SaliencyCommand`
  - `NewSessionCommand`
- split audit / thesis artifact protocol：
  - `XBrainLab/backend/dataset/split_audit.py`
  - `scripts/dev/validate_split_artifact.py`
  - `docs/validation/thesis_protocol.md`
  - `docs/validation/split_artifact_schema.json`
  - `tests/unit/backend/dataset/test_split_audit.py`
  - `tests/unit/scripts/test_validate_split_artifact.py`

這批 evidence 支撐 first-run consent、disabled / cache status UI 邏輯、service-backed
evaluation / visualization / saliency summary query、split artifact schema 與 leakage audit。
它仍不是真 local model 長時間 UI walkthrough，也不是 local LLM tool-call accuracy run。external
EEG dataset experiment 屬於 pipeline support，不是 thesis 主評分。

本輪 validation closure：

- `poetry run ruff check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
- `poetry run ruff format --check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
- `git diff --check` -> pass
- `poetry run mkdocs build --strict` -> pass
- UI product gate -> `62 passed`
- backend / split audit / config gate -> `41 passed`
- agent / facade / backend workflow gate -> `130 passed`
- deterministic eval refresh -> `21 / 21` cases passed
- full test gate:
  - `timeout 2400s poetry run pytest tests/ --deselect tests/unit/ui/test_visualization.py::TestSaliency3DEngine --tb=short -q`
  - `4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`

2026-05-02 local LLM runtime gate 已另行通過，不屬於 fast dashboard 預設 profile：

- primary model：
  - `microsoft/Phi-4-mini-instruct`
  - estimated download `7.69 GB`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- fallback model：
  - `microsoft/Phi-3.5-mini-instruct`
  - estimated download `7.64 GB`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- cache directory：`XBrainLab/llm/core/models`
- cache usage：約 `15.34 GB`
- cache policy：單模型 10GB 內、總 cache 20GB 內。
- 已刪除 Qwen cache；中國公司或中國來源模型不列入候選。

2026-05-02 launcher / startup smoke：

- `timeout 45s xvfb-run -a poetry run python run.py --model local`
- `MainWindow initialized` 出現後 timeout 結束，屬於 GUI smoke 預期結果。

2026-05-04 Windows launcher automated command walkthrough：

- 新增 `scripts/dev/capture_windows_launcher_walkthrough.py`：
  - 從 Windows `cmd.exe` 執行 Desktop `C:\Users\Administrator\Desktop\XBrainLab.cmd` smoke。
  - 從 PowerShell 執行 repo `xbrainlab_wsl_launcher.ps1` 的 `wsl` smoke，確認 stdout /
    stderr 會 mirror 到 launcher output 和 log。
  - 從同一 PowerShell launcher path 執行 `startup` smoke，經 `wsl.exe` 進 active repo 並跑
    bounded `run.py --model local` startup。
- artifact：
  - `artifacts/launcher/windows-launcher-walkthrough.json`
  - `artifacts/launcher/windows-launcher-walkthrough.md`
- artifact summary：
  - status：`passed`
  - Desktop command points to `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - `WSL_launcher_smoke_stdout` / `WSL_launcher_smoke_stderr` both observed
  - launcher logs exist under `/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/`
  - startup smoke saw `MainWindow initialized`
  - startup smoke was bounded by timeout and returned `0`
  - startup geometry diagnostics logged screen count, screen detail, splash geometry, and
    main-window geometry.
- commands:
  - `timeout 180s poetry run python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher --startup-timeout 150`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_windows_launcher_walkthrough.py -q`
  - `3 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_windows_launcher_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐 Windows Desktop command、PowerShell launcher、WSL bridge、launcher log 和
bounded startup path，也支撐 automated startup geometry diagnostics 會被寫入 launcher
stdout/log。它仍不是真人雙螢幕 Desktop click-through、packaged installer approval 或完整
release validation。

2026-05-02 product-delivery final gate：

- backend unit：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed, 3 warnings`
- backend + IO integration：
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed, 8 warnings`
- pipeline integration：
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed, 4 warnings`
- UI unit:
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - latest fast dashboard UI Unit Suite：`831 passed`
- LLM unit:
  - LLM / local settings / script unit gate：`674 passed`
- local model preflight:
  - `timeout 120s poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - `ok=True`; primary `microsoft/Phi-4-mini-instruct` already cached; estimated download `0.00 GB`;
    current / projected cache `15.34 GB`; available disk `158.54 GB`; VRAM estimate `9.0 GB`;
    license MIT
- local runtime health:
  - `timeout 300s poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - classification `gpu-ready`; prompt smoke `passed`; structured-output smoke `passed`

2026-05-02 deterministic tool-call eval baseline：

- methodology references:
  - [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)
  - [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals)
  - [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs)
- script:
  - `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
- test:
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent -q`
  - `1 passed`
- artifacts:
  - `artifacts/agent_evals/latest.json`
  - `artifacts/agent_evals/latest.md`
- deterministic baseline result:
  - total cases `21`
  - passed `21`
  - failed `0`
  - intent / tool selection / argument / state-aware / blocked / recovery /
    trajectory / runtime safety accuracy：`100%`

這是 deterministic scripted baseline，不是 local LLM performance claim。Goal 1 後續已新增
local model runner，見下方 `2026-05-04 Local LLM tool-call runner and schema gate`。

2026-05-04 Data Interpretation backend command baseline：

- 新增 backend command contract：
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `save_interpretation_recipe`
  - `reload_interpretation_recipe`
- validation coverage：
  - GDF + external label carrier scan / preview / `needs_confirmation` validation /
    confirmed apply。
  - labels-only source -> `blocked` validation，apply 不會呼叫 dataset import。
  - recipe save / reload -> reload 只重新 scan / preview / validate，不會自動 apply。
  - capability policy 覆蓋新 commands，並暴露 autonomy policy 欄位。
- commands:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `28 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/integration/backend/test_application_service_workflow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `92 passed`
  - `poetry run ruff check XBrainLab/backend/application tests/unit/backend/application/test_application_service.py scripts/agent/evals/run_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_application_service.py`
  - `0 errors, 0 warnings, 0 notes`
  - broader gates：
    - `poetry run ruff check .` -> `PASS`
    - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
    - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
    - `poetry run mkdocs build --strict` -> `PASS`

這批 evidence 只支撐 backend Data Interpretation command baseline 和 deterministic scorer
compatibility。它不支撐「UI import flow 已重做」、「agent tool taxonomy 已遷移」或
「local LLM 真實 tool-call accuracy 已驗證」。

2026-05-04 Data Interpretation agent tool surface slice：

- 新增 agent tool definitions / mock / real tools：
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `save_interpretation_recipe`
  - `reload_interpretation_recipe`
- `application_surface.py` 會把上述 tools 映射到同名 ApplicationService commands，並把
  autonomy policy 欄位帶進 `ToolAvailability.to_dict()`。
- `LLMController` 會依 backend policy 的 `requires_confirmation` / `confirmation_required`
  暫停 dynamic boundary，確認後對 `apply_interpretation` 注入 `confirmed=True`。
- `BackendFacade(study)` 重用同一個 ApplicationService，已用 agent surface test 覆蓋
  scan -> preview -> validate 連續 tool call 不遺失 lifecycle state。
- commands:
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/agent/test_controller.py -q`
  - `219 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/agent/test_verification_layer.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `286 passed`
  - `poetry run ruff check <slice files>`
  - `PASS`
  - `poetry run basedpyright <slice source files>`
  - `0 errors, 0 warnings, 0 notes`
  - broader gates:
    - `poetry run ruff check .` -> `PASS`
    - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
    - `poetry run mkdocs build --strict` -> `PASS`
    - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
    - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals_tmp_goal1_agent_surface`
      -> pass; temporary artifact directory removed.

這批 evidence 支撐 agent taxonomy / command mapping / dynamic confirmation boundary。它仍不支撐
「UI import flow 已重做」、「headless / MCP adapter 已完成」或「local LLM 真實 tool-call
accuracy 已驗證」。

2026-05-04 Dataset panel Data Interpretation entry slice：

- Dataset sidebar 主按鈕改為 `Interpret Data Source`。
- UI import action 走 `scan_source` -> `preview_interpretation` ->
  `validate_interpretation` -> `apply_interpretation`。
- 新增 preview dialog，顯示 source、metadata preview、warnings、confirmation items、
  validation decision 和 blocked reasons。
- product walkthrough synthetic `.fif` import 已通過新 dialog / apply path。
- commands:
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q`
  - `50 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/dataset tests/unit/ui/dialogs/dataset tests/unit/ui/test_ui_misc.py tests/unit/ui/test_application_capabilities.py tests/integration/ui/test_product_walkthrough.py -q`
  - `166 passed`
  - `poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `76 passed`
  - `poetry run ruff check <ui data interpretation slice files>` -> `PASS`
  - `poetry run basedpyright <ui data interpretation source files>` ->
    `0 errors, 0 warnings, 0 notes`
  - broader gates:
    - `poetry run ruff check .` -> `PASS`
    - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
    - `poetry run mkdocs build --strict` -> `PASS`
    - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
    - `git diff --check` -> `PASS`

這批 evidence 支撐 Dataset panel main import entry 的新心智模型。後續 recipe save option
和 headless / MCP-ready adapter 已補；label import 已降為 service-backed compatibility path，
且後續已整合進 Data Interpretation recipe trace。stdio MCP server baseline、stdio external-client
walkthrough artifact、Inspector release config、Inspector GUI walkthrough 和 local LLM 真實
ChatPanel walkthrough 都已另有 evidence；這個早期 gate 本身不能替代那些後續 evidence。

2026-05-04 MCP-ready automation adapter + deterministic eval expansion：

- 新增 `XBrainLab.backend.application.automation`：
  - `command_specs(service)` 產生所有 `ApplicationService` command 的 JSON schema、
    workflow taxonomy 和 live capability / autonomy policy。
  - `mcp_tool_specs(service)` 使用同一份 command schema 產生 MCP-shaped tool specs。
  - `execute_automation_payload(service, payload)` 將 JSON payload 轉 typed command，並只透過
    `ApplicationService.execute()` 執行；adapter 本身不新增 controller business logic。
- 新增 `scripts/dev/run_application_command.py`：
  - `--list-schemas` 輸出 headless command schema。
  - `--mcp-tools` 輸出 MCP-ready tool schema。
  - `--payload` / `--payload-file` 在同一個 headless `ApplicationService` session 中跑一個或多個
    command payload。
- deterministic tool-call eval：
  - cases：`54 / 54` pass。
  - multi-turn cases：`15`。
  - negative / blocked / confirmation / missing-input / recovery cases：`34 / 54`。
  - case artifact 現在保存 user command、initial state、available command summary、expected /
    actual verification result、expected state delta、parsed tool call、simulated backend result、
    visible response 和 score breakdown。
- commands:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py -q`
  - `7 passed`
  - `poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py -q`
  - `1 passed`
  - `poetry run ruff check XBrainLab/backend/application/automation.py scripts/dev/run_application_command.py scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_automation.py tests/integration/agent/test_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application/automation.py scripts/dev/run_application_command.py scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_automation.py tests/integration/agent/test_tool_call_eval.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - refreshed `artifacts/agent_evals/latest.json` and `artifacts/agent_evals/latest.md`

這批 evidence 支撐 headless / MCP-ready command schema 和 deterministic engineering
tool-call baseline。它仍不支撐「MCP server 已完成」、「local LLM 真實 tool-call accuracy 已驗證」、
或「UI-observable replay 已完成」。

2026-05-04 stdio MCP server baseline：

- 新增 `XBrainLab.mcp.server`：
  - 支援 MCP `initialize` lifecycle，回傳 `tools` capability。
  - 支援 `tools/list`，直接使用 `mcp_tool_specs(service)` 暴露同一組 command schema、
    output schema、taxonomy 和 live capability / autonomy metadata。
  - 支援 `tools/call`，在同一個 server session 中將 MCP arguments 轉成
    `execute_automation_payload()`，並只透過 `ApplicationService.execute()` 執行。
  - tool result 同時回傳 MCP `content` 和 `structuredContent`；schema / business failure 以
    `isError: true` 表達，方便 external agent self-correction。
- 新增 `scripts/dev/run_mcp_server.py` 作為 stdio server entrypoint。
- commands:
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
  - `6 passed`
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp tests/unit/backend/application/test_automation.py -q`
  - `13 passed`
  - `poetry run ruff check XBrainLab/mcp XBrainLab/backend/application/automation.py scripts/dev/run_mcp_server.py tests/unit/mcp tests/integration/mcp`
  - `PASS`
  - `poetry run basedpyright XBrainLab/mcp XBrainLab/backend/application/automation.py scripts/dev/run_mcp_server.py tests/unit/mcp tests/integration/mcp`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐「已有可啟動的 stdio MCP server baseline，且 MCP calls 不繞過
ApplicationService」。它仍不支撐外部 MCP client / Inspector walkthrough、Windows release
config、HTTP transport、或 product completion。

2026-05-04 MCP stdio external-client walkthrough：

- 新增 `scripts/dev/capture_mcp_stdio_walkthrough.py`：
  - client process 只 import Python standard-library modules。
  - prepared XBrainLab runtime 仍在 server process：`scripts/dev/run_mcp_server.py`。
  - client 透過 MCP stdio JSON-RPC 跑 `initialize`、`tools/list`、`scan_source`、
    `preview_interpretation`、`validate_interpretation`。
  - artifact 保存到 `artifacts/mcp/stdio-walkthrough.json` 和
    `artifacts/mcp/stdio-walkthrough.md`。
- artifact summary：
  - initialized：`True`
  - tool count：`28`
  - `scan_source` listed：`True`
  - `scan_source` taxonomy：`data_interpretation`
  - `scan_source` status：`ok`
  - `preview_interpretation` status：`ok`
  - `validate_interpretation` status：`ok`，visible text 為
    `Interpretation validation: needs_confirmation.`
- commands:
  - `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp`
  - wrote `artifacts/mcp/stdio-walkthrough.json` and `.md`
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
  - `7 passed`
  - `poetry run ruff check scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
  - `PASS`
  - `poetry run basedpyright scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 external stdio client 可以不安裝 XBrainLab EEG / PyQt / PyTorch client-side
dependencies，並透過 prepared XBrainLab MCP server 走同一套 ApplicationService command surface。
它本身仍不支撐 MCP Inspector GUI click-through、Windows release registration / config、HTTP
transport、long-running training tool through MCP、或 product completion；Inspector release config
和 GUI walkthrough 已由後續 artifacts 補上。

2026-05-04 MCP Inspector-style release config baseline：

- 新增 `scripts/dev/run_mcp_server_for_client.sh`：
  - 外部 MCP client / Inspector 只需要啟動這個 prepared runtime wrapper。
  - wrapper 會切回 active repo，再用 `poetry run python scripts/dev/run_mcp_server.py`
    啟動真正 server。
- 新增 `scripts/dev/write_mcp_client_config.py`：
  - 產生 `artifacts/mcp/xbrainlab-mcp.json` 和 `artifacts/mcp/xbrainlab-mcp.md`。
  - config 使用 Inspector 支援的 `mcpServers` / `type: "stdio"` / `command` / `args` 格式。
  - `default-server` 用 `bash <wrapper>`，`xbrainlab-windows-wsl` 用
    `wsl.exe bash <wrapper>`。
  - validator 明確拒絕直接把 client config 指到 client-side Python，避免把 EEG / PyQt /
    PyTorch dependencies 推給 external client。
- 新增 `tests/unit/scripts/test_write_mcp_client_config.py` 和
  `tests/integration/mcp/test_client_config.py`：
  - unit tests 驗證 config shape、server command extraction、committed artifact contract 和
    CLI regeneration。
  - integration test 讀 committed config，透過 config command 啟動 prepared runtime wrapper，
    再重跑 stdio `initialize`、`tools/list`、`scan_source`、`preview_interpretation`
    walkthrough。
- commands:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py -q`
  - `6 passed`
  - manual config walkthrough:
    `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir /tmp/xbrainlab-mcp-config-walkthrough --server-command bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
  - wrote `/tmp/xbrainlab-mcp-config-walkthrough/stdio-walkthrough.json` and `.md`
  - first official Inspector CLI attempt failed with `Connection closed` because Windows-side
    `wsl.exe` launched a non-login shell where `poetry` was not on PATH.
  - wrapper now resolves `POETRY_BIN`, `command -v poetry`, or `$HOME/.local/bin/poetry`.
  - Windows-side WSL stdio smoke:
    `timeout 10s /mnt/c/Windows/System32/wsl.exe bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
    with MCP `initialize` request -> valid JSON-RPC initialize response.
  - official Inspector CLI:
    `timeout 180s '/mnt/c/Program Files/nodejs/npx' -y @modelcontextprotocol/inspector --cli --config artifacts/mcp/xbrainlab-mcp.json --server xbrainlab-windows-wsl --method tools/list`
    -> exit `0`, `28` tools listed.
  - artifact:
    `artifacts/mcp/inspector-cli-tools-list.json` / `.md`

這批 evidence 支撐 Inspector-style release config baseline、prepared-runtime launch path 和 official
Inspector CLI `tools/list`。它本身仍不支撐 Inspector GUI click-through、Windows Desktop 真人啟動、HTTP
transport、long-running training through MCP 或 product completion；Inspector GUI baseline 已由下一段
artifact 補上。

2026-05-04 MCP Inspector GUI click-through baseline：

- script：`scripts/dev/capture_mcp_inspector_gui_walkthrough.py`
- artifact：
  - `artifacts/mcp/inspector-gui-walkthrough.json`
  - `artifacts/mcp/inspector-gui-walkthrough.md`
  - `artifacts/mcp/inspector-gui-connected.png`
- command：
  - `timeout 210s poetry run python scripts/dev/capture_mcp_inspector_gui_walkthrough.py --output-dir artifacts/mcp --timeout-seconds 150`
- result：
  - status：`passed`
  - visible Inspector state：`Connect` clicked、`Connected` visible、`Disconnect` visible、
    server `xbrainlab` visible、Tools panel visible。
  - client boundary：Inspector / Chrome run as Windows external client processes; server entry uses
    `wsl.exe bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
    to launch the prepared XBrainLab runtime.
  - visible Data Interpretation tools:
    - `scan_source` / `Scan Source`
    - `preview_interpretation` / `Preview Interpretation`
    - `validate_interpretation` / `Validate Interpretation`
    - `apply_interpretation` / `Apply Interpretation`
  - cleanup: post-run Windows `node.exe` Inspector processes and Chrome processes tied to
    XBrainLab MCP artifacts were absent.
- unit/static:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_mcp_inspector_gui_walkthrough.py -q`
  - `5 passed`
  - targeted `ruff check` / `ruff format --check` clean
  - `poetry run basedpyright scripts/dev/capture_mcp_inspector_gui_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 automated MCP Inspector GUI click-through with connected tools list and prepared
Windows WSL runtime wrapper。它仍不是 human GUI session、full MCP client certification、HTTP
transport、long-running training through MCP、Windows Desktop真人啟動或 product completion。

2026-05-04 Local LLM tool-call runner and schema gate：

- 新增 `scripts/agent/evals/run_local_tool_call_eval.py`：
  - 使用同一份 `scripts/agent/evals/run_tool_call_eval.py` case schema / scorer。
  - 接真 local model raw output，不執行 workflow command。
  - 每個 case 保存 prompt-derived state、raw output、parsed tool calls、schema verification、
    score breakdown 和 failure taxonomy。
  - `repeat_count < 3` 或 cases `< 50` 時標成 exploratory；本次 primary / fallback full run
    都是 `54` cases x `3` repeats，非 exploratory。
- `CommandParser` 現在可解析：
  - `parameters`
  - `arguments`
  - top-level `name`
  - `tool_calls` list
- `VerificationLayer` 現在可用 registered tool schema 檢查：
  - unknown / unregistered tool。
  - required parameter。
  - JSON-like type。
  - enum value。
  `LLMController` 會用 real `ToolRegistry` schema 建立 verifier，因此可在 execution 前攔下
  可解析但不可執行的 tool JSON。
- local runtime preflight：
  - primary / fallback cache 都已存在，不需下載。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
  - classification：`gpu-ready`。
- primary run：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_primary`
  - artifact：
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - result：`18 / 54` pass，pass rate `33.33%`。
  - schema-invalid tool outputs：`9`。
- fallback run：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_fallback`
  - artifact：
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - result：`20 / 54` pass，pass rate `37.04%`。
  - schema-invalid tool outputs：`6`。
- targeted validation:
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py -q`
  - `44 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_controller_integration.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `98 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py -q`
  - `383 passed`
  - `poetry run ruff check XBrainLab/llm/agent/parser.py XBrainLab/llm/agent/verifier.py XBrainLab/llm/agent/controller.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/llm/agent/parser.py XBrainLab/llm/agent/verifier.py XBrainLab/llm/agent/controller.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐「真 local LLM runner / parser / schema gate 已建立」。它明確不支撐
「local LLM tool-call accuracy thesis-ready」、「真 ChatPanel 長時間 workflow 已通過」或
「agent 可無監督完成多步 workflow」。

2026-05-04 Local assistant tool-call guardrail smoke：

- 變更範圍：
  - `CommandParser` 支援 top-level tool-call array 和 OpenAI-style function tool call。
  - `VerificationLayer` 新增 `PlaceholderArgumentValidator`，拒絕模型自造的 placeholder
    source / file / recipe path。
  - `LLMController` 新增 requested-intent boundary：最新使用者要求的 workflow command 若被
    `ApplicationService` capability policy 擋下，agent 不能改叫其他 tool 來替代。
  - `LLMController` 也把 inferred latest intent 放入 prompt context，讓 local model 不必從多輪
    history 猜下一個 workflow step。
  - local eval runner 使用同一 guardrail 語意，且成功 tool-call 的 `visible_response` 不再保存
    raw JSON tool syntax。
  - prompt / schema 補 standard preprocess、dataset split 和 state-authoritative latest-turn
    規則。
- preflight：
  - primary / fallback classification：`gpu-ready`。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
  - no download；沒有 disallowed cache candidates。
- exploratory smoke artifacts：
  - primary：
    `artifacts/agent_evals/local_primary_guardrail_smoke/local_microsoft_phi_4_mini_instruct.md`
    -> `6 / 6` pass。
  - fallback：
    `artifacts/agent_evals/local_fallback_guardrail_smoke/local_microsoft_phi_3.5_mini_instruct.md`
    -> `6 / 6` pass。
- targeted validation:
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_controller.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_assembler_stage.py -q`
  - `125 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_assembler_stage.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_definitions.py -q`
  - `150 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py -q`
  - `426 passed`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir /tmp/xbrainlab_eval_guardrails`
  - temp deterministic report written。
  - `poetry run ruff check .`
  - pass
  - `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict`
  - pass
  - `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`
  - `git diff --check`
  - pass

這批 evidence 支撐「local assistant tool-call guardrails 方向有效，且不再把 raw tool syntax
當作 visible response」。此段為 guardrail smoke 當時的結論；正式 full rerun 已由下方
normalization slice 更新。

2026-05-04 Local assistant tool-call normalization full rerun：

- 變更範圍：
  - `CommandParser` 進一步支援 command-only JSON 和 bare tool name 輸出。
  - 新增 `tool_call_normalizer`，在 verifier 前處理 local model 常見但可安全歸一的 tool
    variants：`create_epoch` -> `epoch_data`、`train` -> `start_training`、
    `get_dataset_info` -> typed `query_state`、latest-turn scan / preview / validate / apply
    substitute、BIDS source hint、subject override、dataset split defaults 和 recipe save default。
  - `query_state` agent tool 走 `ApplicationService` / `QueryStateCommand`，不再只依賴
    legacy `get_dataset_info` 心智模型。
  - placeholder validator 擋下 prose path，例如 `Please provide the absolute path...`。
  - local eval 將 backend result interpretation 納入 scoring，讓 successful load、
    confirmation-boundary validation、recoverable backend failure 不被誤判成 raw tool 成功。
- full local eval artifacts：
  - primary：
    `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
    -> `53 / 54` pass (`98.15%`)。
  - fallback：
    `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
    -> `53 / 54` pass (`98.15%`)。
  - runtime classification：primary / fallback 都是 `gpu-ready`。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
  - no download。
- targeted validation：
- `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_intent.py -q`
  - `156 passed`
  - targeted `poetry run ruff check ...`
  - pass
  - targeted `poetry run basedpyright ...`
  - `0 errors, 0 warnings, 0 notes`
- regression / docs gates：
- `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q`
  - `464 passed`
  - `poetry run ruff check .`
  - pass
  - `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict`
  - pass
  - `git diff --check`
  - pass

這批 evidence 支撐 local assistant tool-call guardrail 已從不可用的 `33%` / `37%` 區間提升到
工程 baseline 可用區間；它仍不支撐 thesis-ready claim，因為 benchmark 仍只有 `54` cases、
不是要求的 `100` thesis candidate cases，且仍有 bandpass-vs-standard preprocess 語意
failure。

2026-05-04 Local LLM tool-call thesis-candidate 100-case rerun：

- 變更範圍：
  - deterministic / local eval cases 從 `54` 擴到 `100`，覆蓋 Data Interpretation file /
    folder / BIDS / recipe、metadata choice、relative / missing path、confirmation、blocked /
    recovery、多輪 workflow、bandpass-only vs standard preprocess、dataset split、visualization /
    saliency readiness 和 query-state。
  - local parser / normalizer / verifier 補上 partial tool-name JSON、command-only JSON with
    confirmation metadata、blank / relative source path rejection、metadata choice cleanup、
    bandpass-only demotion、dataset split vs training mode normalization、epoch default window、
    visualization / saliency substitute guardrail。
  - controller requested-intent boundary 會擋下 saliency / visualization request 被模型改成
    setup / UI-route tool 的 substitute call。
- resource boundary：
  - primary / fallback model cache 已存在；本輪沒有下載模型。
  - runtime classification：primary / fallback 都是 `gpu-ready`。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
- deterministic baseline：
  - command：`poetry run python scripts/agent/evals/run_tool_call_eval.py --repeat-count 2 --output-dir artifacts/agent_evals/deterministic`
  - artifacts：
    - `artifacts/agent_evals/deterministic/latest.md`
    - full deterministic JSON is generated by the command but not tracked because it exceeds
      the repository large-file hook limit.
  - result：`100 / 100` pass (`100.00%`)。
- primary local model：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_primary`
  - artifacts：
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - result：`100 / 100` pass (`100.00%`)。
- fallback local model：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_fallback`
  - artifacts：
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - result：`100 / 100` pass (`100.00%`)。
- targeted validation:
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_intent.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_controller.py -q`
  - `166 passed`
  - targeted `poetry run ruff check ...`
  - pass
- regression / docs / architecture gates：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q`
  - `487 passed`
  - `poetry run ruff check .`
  - pass
  - `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict`
  - pass
  - `git diff --check`
  - pass
  - `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant!`

這批 evidence 支撐 thesis-candidate local tool-call benchmark：同一 `100` cases 被 deterministic
baseline、primary local model 和 fallback local model 各自以可重跑 artifact 驗證。它仍不能替代
true ChatPanel multi-turn walkthrough、Windows launcher click-through、
MCP HTTP / long-running client workflows、完整 import wizard UI 驗收或論文最終統計報告。

2026-05-04 Tool-call best-practices 117-case dashboard refresh：

- design input：
  - OpenAI Structured Outputs / function calling：schema-constrained arguments、validation、
    bounded repair。
  - Berkeley Function Calling Leaderboard：multi-turn、multi-language、multiple tool candidates、
    relevance / no-call、blocked / recovery coverage。
  - LangSmith agent trajectory evaluation：評估 tool path、arguments、state transition 和
    visible response，而不只看 final answer。
- 變更範圍：
  - prompt-facing `schema_contract.py` 以 tool taxonomy 輸出 stricter contracts，並把
    Data Interpretation 標成資料入口主線、`load_data / attach_labels` 標成 legacy compatibility。
  - `preview_interpretation.choices` 變成 structured object：selected EEG files、label carrier、
    event role、class map、anchor、subject / session / task / run。
  - controller 在 no-tool / ask-clarification intent 上可直接用使用者語言回覆，不執行 mutating
    tool。
  - parser / normalizer 支援 local model 常見 function-call variants，並修補 safe structured
    output drift；verifier 新增 nested object required / enum / type / unknown-field checks。
  - eval cases 擴到 `117`，新增 Chinese、mixed Chinese / English、ambiguous request、missing
    input、no-call、should-not-call、wrong-tool temptation、blocked command、multi-intent、
    multi-turn recovery、Data Interpretation confirmation boundary、BIDS / label ambiguity /
    subject metadata、destructive / long-running confirmation 和 EEG/BCI domain phrasing。
  - scorer 新增 tool/no-tool decision、clarification behavior、confirmation boundary、visible
    response quality、case family pass rates、failure taxonomy、worst cases 和 repeated-run
    stability。
- deterministic baseline：
  - command：`poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - artifact：`artifacts/agent_evals/latest.json` / `latest.md`
  - result：`117 / 117` pass (`100.00%`)。
- primary local model：
  - command：`poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --output-dir artifacts/agent_evals/local_primary --max-new-tokens 160`
  - artifact：`artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json` /
    `.md`
  - result：`117 / 117` pass (`100.00%`)。
- fallback local model：
  - command：`poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --output-dir artifacts/agent_evals/local_fallback --max-new-tokens 160`
  - artifact：`artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json` /
    `.md`
  - result：`117 / 117` pass (`100.00%`)。
- dashboard：
  - command：`poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
  - artifact：`artifacts/agent_evals/dashboard.md`
  - visible sections：overall model comparison、metric pass rates、family pass rates、failure
    taxonomy、worst cases、source / artifact paths、thesis claim boundary。

這批 evidence 支撐本 benchmark slice 的 thesis-candidate tool-call claim。它仍不能替代
UI-observable automated walkthrough、human Windows desktop acceptance、雙螢幕 / DPI、長時間
local model session、EEG training quality 或 product completion。

2026-05-04 UI-observable automated human-like walkthrough：

- script：`scripts/dev/capture_human_like_product_walkthrough.py`
- artifacts：
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`
  - `artifacts/ui/human-like-walkthrough/*.png` (`20` screenshots)
  - `artifacts/ui/human-like-walkthrough/walkthrough-import.recipe.json`
- coverage：
  - app startup / main window initial state / Dataset page。
  - data source selection and Data Interpretation wizard scan / preview / confirm / apply /
    save recipe / reload recipe。
  - safe / needs_confirmation / blocked decision probes。
  - preprocessing、epoch creation、dataset generation。
  - training readiness by configuring EEGNet CPU training settings without starting a long run。
  - evaluation / visualization / saliency readiness queries。
  - ChatPanel empty state、normal message、missing-input clarification、blocked command、
    successful tool result summary、narrow panel、repeated open / close。
  - reset / new session confirmation boundary and error recovery after a missing scan.
  - visible text snapshots、button enabled / disabled state、workflow state snapshots、
    command / tool transcript、user-facing transcript、CommandResult payloads、process/thread notes.
  - top-level `observable_evidence` indexes visible text、button states、workflow snapshots and
    backend state snapshots by phase；`ui_quality_review` records nonblank screenshot checks,
    forbidden visible text findings and the human-review boundary.
- observed result：
  - status：`passed`
  - phases：`26 / 26`
  - screenshots：`20`
  - human desktop acceptance：`not performed`
  - observable evidence：`26` visible text snapshots、`26` button-state snapshots、`26`
    workflow/backend snapshots.
  - UI quality review：automated checks `passed`、forbidden visible text findings `0`.
  - resource notes：Python thread count returned to `1`; Qt active thread count `0`.

這批 evidence 支撐 automated UI-observable replay 條件下主要 path 可操作。它仍不能宣稱真人
Windows desktop launcher、雙螢幕 / DPI、長時間 true local model desktop session 或 full
product completion 已完成。

2026-05-04 agent analysis-tool exposure validation：

- 變更範圍：
  - `evaluate` / `visualize` / `saliency` 新增 tool definitions、mock tools、real tools 和
    `get_all_tools()` registration。
  - `application_surface.py` 直接轉成 `EvaluateCommand`、`VisualizeCommand`、
    `SaliencyCommand`，因此 execution / blocked reason 走 `ApplicationService` capability
    policy。
  - `CommandParser` 支援三個 bare tool names；intent mapping 補上 `evaluate`。
- deterministic eval refresh：
  - command：`poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - artifact：`artifacts/agent_evals/latest.json` / `latest.md`
  - result：`100 / 100` pass (`100.00%`)。
- affected-case local LLM smoke：
  - primary command：`timeout 1200s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --case-id saliency-before-trained-block --case-id visualize-before-trained-block --case-id trained-visualize-ready-summary --case-id trained-saliency-ready-summary --case-id dataset-saliency-readiness-summary --output-dir artifacts/agent_evals/local_primary_analysis_tools`
  - primary result：`5 / 5` pass (`100.00%`)，runtime `gpu-ready`，cache `15.34 GB`，no download。
  - fallback command：`timeout 1200s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --case-id saliency-before-trained-block --case-id visualize-before-trained-block --case-id trained-visualize-ready-summary --case-id trained-saliency-ready-summary --case-id dataset-saliency-readiness-summary --output-dir artifacts/agent_evals/local_fallback_analysis_tools`
  - fallback result：`5 / 5` pass (`100.00%`)，runtime `gpu-ready`，cache `15.34 GB`，no download。
- regression gates:
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q`
  - `293 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/llm/test_parser.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q`
  - `516 passed`
  - targeted `ruff` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run ruff check .` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass

這批 evidence 支撐 analysis commands 已成為 ApplicationService-backed agent tools。它仍不支撐
ChatPanel dataset -> training -> evaluation / visualization / saliency 長鏈完成。

2026-05-04 ChatPanel local training-readiness boundary walkthrough：

- script：`scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py`
- artifact：
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-ready.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-1.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-2.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-3.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-4.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-5.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-6.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.json`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.md`
- command：
  - `timeout 900s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-readiness --timeout-seconds 840`
- result：
  - status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - cache usage：`15.34 GB`，no download
  - dataset preparation：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
    -> `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset` all `ok`
  - ChatPanel turns：`set_model` ok、`configure_training` ok、`start_training` confirmation
    observed and rejected、`visualize` ok、`saliency` ok、`evaluate` blocked with user-facing reason。
  - final state：dataset available `True`、model `EEGNet`、training option present, trainer
    `False`, training running `False`, evaluation available `False`。
  - visible assistant text clean check：no `Tool Output`, fenced JSON, traceback,
    `ApplicationService`, or `BackendFacade` markers.
- unit/static:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py -q`
  - `4 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 high-impact training confirmation boundary 與 analysis-readiness tools 的 true
ChatPanel path。它仍不支撐 actual training completion、evaluation metrics 或 saliency render。

2026-05-04 ChatPanel local controlled tiny training-completion walkthrough：

- script：`scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`
- artifact：
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-ready.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-trained.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-1.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-2.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-3.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-4.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-5.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-6.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-7.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.json`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.md`
- command：
  - `timeout 1200s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-completion --timeout-seconds 1080`
- result：
  - status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - cache usage：`15.34 GB`，no download
  - dataset preparation：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
    -> `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset` all `ok`
  - ChatPanel turns：`set_model` ok、`configure_training` ok with controlled temp `output_dir`、
    `start_training` confirmation observed and approved、training completion observed、
    `evaluate` ok、`saliency` configure ok、`visualize` ok、saliency readiness query ok。
  - final state：dataset available `True`、model `EEGNet`、training option present、trainer
    `True`、training running `False`、finished runs `1`、evaluation metrics available `True`、
    saliency configured / available `True`。
  - UI state：ChatPanel returned idle; visible assistant text stayed product-facing.
- supporting fixes validated in the same slice：
  - `configure_training` tool schema / ApplicationService mapping preserves `output_dir`。
  - saliency command normalizes flat `method` / `params` into backend-required
    `SmoothGrad` / `SmoothGrad_Squared` / `VarGrad` parameter keys。
  - `visualization` text maps to visualize intent, and saliency readiness queries drop stale
    configuration params from previous turns。
  - evaluation bar chart `tight_layout` failure degrades to warning, and missing `torchinfo`
    returns a model-summary unavailable message without logging traceback。
- unit/static/regression:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params tests/unit/backend/application/test_application_service.py::test_saliency_command_normalizes_flat_method_params tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/backend/controller/test_evaluation_controller.py -q`
  - `48 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent -q`
  - `235 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - deterministic tool-call eval refresh -> `100 / 100` pass

這批 evidence 支撐 true local ChatPanel controlled tiny training completion、post-training metrics
query 和 saliency / visualization readiness summary。它仍不等於完整 saliency / visualization
canvas render、真人 Windows launcher click-through、mature import wizard label editor 或
MCP HTTP / long-running client workflow 完成。

2026-05-04 MainWindow VisualizationPanel Matplotlib render walkthrough：

- script：`scripts/dev/capture_visualization_render_walkthrough.py`
- artifact：
  - `artifacts/ui/visualization-render/visualization-render-ready.png`
  - `artifacts/ui/visualization-render/visualization-render-saliency-map.png`
  - `artifacts/ui/visualization-render/visualization-render-spectrogram.png`
  - `artifacts/ui/visualization-render/visualization-render-topographic-map.png`
  - `artifacts/ui/visualization-render/visualization-render-3d-blocked.png`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.json`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.md`
- command：
  - `timeout 600s env QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python scripts/dev/capture_visualization_render_walkthrough.py --output-dir artifacts/ui/visualization-render --timeout-seconds 540`
- result：
  - status：`passed`
  - dataset preparation：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
    -> `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset` all `ok`
  - training/setup commands：`configure_training` model `EEGNet` ok、1 epoch CPU settings ok、
    `saliency` configure ok、`apply_montage` ok、`train` ok。
  - final state：finished runs `1`、metrics available `True`、saliency available `True`、montage
    available `True`。
  - ApplicationService `visualize` result reported `saliency map`、`spectrogram`、
    `topographic map` 和 `3D plot` available views。
  - UI render evidence：
    - `Saliency Map`：axes count `3`、image count `3`、error visible `False`、canvas visible `True`
    - `Spectrogram`：axes count `3`、image count `3`、error visible `False`、canvas visible `True`
    - `Topographic Map`：axes count `3`、image count `4`、error visible `False`、canvas visible `True`
    - `3D Plot`：blocked reason visible、`plotter_created=False`、screenshot captured。
  - offscreen capture auto-dismissed the training completion dialog `Done / All training jobs
    finished.` so the modal did not mask render state.
- unit/static:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
  - `8 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
  - `1 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization.py -q`
  - `20 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass

這批 evidence 支撐 true MainWindow VisualizationPanel post-training Matplotlib saliency renders，
並支撐 headless/offscreen 3D tab 會顯示人話 blocked reason 而不是 crash。它仍不支撐
interactive desktop 3D / PyVista render、ChatPanel UI-routing render、真人 Windows launcher
click-through、mature import wizard label editor 或 MCP HTTP / long-running client workflow 完成。

2026-05-04 PyVistaQt runtime probe：

- script:
  - `scripts/dev/probe_pyvistaqt_runtime.py`
- artifacts:
  - `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.json`
  - `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.md`
- result:
  - status `blocked`
  - environment captured `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`
  - child probe attempted a minimal `pyvistaqt.QtInteractor` + sphere render
  - stderr: X `BadWindow (invalid Window parameter)`
  - screenshot was not created
- commands:
  - direct exploratory probe first failed with the same X `BadWindow`
  - `timeout 90s poetry run python scripts/dev/probe_pyvistaqt_runtime.py --output-dir artifacts/ui/visualization-render --timeout-seconds 60`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_probe_pyvistaqt_runtime.py -q`
  - `2 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/probe_pyvistaqt_runtime.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐目前 runner session 無法驗證 interactive PyVistaQt render，因此不能把
headless 3D blocked UX 包裝成產品 3D 完成。它仍不支撐 XBrainLab 3D saliency render、真人
OpenGL desktop walkthrough 或 Windows release click-through。

2026-05-04 ChatPanel true local-model one-turn walkthrough：

- 新增 `scripts/dev/capture_chatpanel_local_walkthrough.py`：
  - 在 `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 下執行，避免模型下載或 remote path。
  - 打開真 `MainWindow` / `ChatPanel`，並用 UI composer / Send button 送出 prompt。
  - runtime path 是 `AgentManager -> LLMController -> AgentWorker -> LLMEngine -> LocalBackend`。
  - 保存 `artifacts/ui/chatpanel-local-ready.png`、
    `artifacts/ui/chatpanel-local-response.png`、
    `artifacts/ui/chatpanel-local-walkthrough.json` 和 `.md`。
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - cache usage：`15.34 GB`
  - visible user prompt：
    `In one short user-facing sentence, explain what EEG preprocessing does. Do not use tools.`
  - visible assistant response：
    `EEG preprocessing involves cleaning and organizing the raw EEG data to prepare it for further analysis.`
  - send button：`Send`
  - input enabled：`True`
  - chat / controller processing：`False`
- commands:
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown`
  - `classification: gpu-ready`，cache `15.34 GB`
  - `timeout 420s xvfb-run -a poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui --timeout-seconds 360`
  - wrote walkthrough JSON / Markdown and two screenshots。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
  - `2 passed`
  - `poetry run ruff check scripts/dev/capture_chatpanel_local_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`
  - `PASS`
  - `poetry run basedpyright scripts/dev/capture_chatpanel_local_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 true local model 可以在 ChatPanel 中產生使用者可見回覆，且 visible transcript
沒有 raw tool syntax、schema、traceback 或 debug payload。它仍不支撐 multi-turn tool-command
workflow、Windows Desktop launcher click-through、長時間 assistant 操作、完整 import wizard UI
驗收或 release closure。

2026-05-04 ChatPanel local tool-command walkthrough：

- 目的：
  - 驗證真 local model 從 ChatPanel UI composer 觸發 tool call 時，UI 會顯示產品語言回覆，
    不會把 raw tool JSON、schema、traceback 或 `Tool Output` 暴露給使用者。
- artifact：
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-ready.png`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-response.png`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.json`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - cache usage：`15.34 GB`
  - executed tool：`query_state` `ok`
  - visible assistant response：`Application state snapshot ready.`
  - send button：`Send`
  - input enabled：`True`
  - chat / controller processing：`False`
- commands:
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool --timeout-seconds 360 --prompt "Check what is ready in the current XBrainLab workflow. Use the state query tool if needed, then answer in one short sentence."`
  - wrote walkthrough JSON / Markdown and two screenshots。
  - `scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
  - `3 passed`
  - targeted `ruff` / `basedpyright`
  - clean。

這批 evidence 支撐單步 ApplicationService-backed tool execution 可以經 ChatPanel 走真 local
model path 並回到 idle。它仍不支撐多輪 tool-command chain、長時間 assistant 操作、Windows
Desktop launcher click-through 或完整 release closure。

2026-05-04 ChatPanel local two-turn workflow walkthrough：

- root cause fixed:
  - 初次 multi-turn capture 顯示 turn 1 `query_state` 成功後，完整 state JSON 被寫回
    conversation history。
  - turn 2 prompt 約 `10.7k` input tokens，local model generation timeout。
  - `LLMController._format_tool_output()` 已改為 compact feedback：保留 tool message、
    capability、`state_summary` 和 small diagnostics，移除 full `state` / `raw_result`。
- artifact：
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-ready.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-turn-1.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-turn-2.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.json`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - turn 1 executed tool：`query_state` `ok`
  - turn 2 local-model follow-up completed with no tool call
  - turn 2 input tokens dropped to about `2.46k` in run log
  - visible transcript has no raw `Tool Output`、schema、traceback or debug payload
  - UI returned idle
- commands:
  - `timeout 520s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_workflow_walkthrough.py --output-dir artifacts/ui/chatpanel-local-workflow --timeout-seconds 480`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_tool_output_history_uses_compact_state_summary tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_tool_executes -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_workflow_walkthrough.py -q`
  - `1 passed`

這批 evidence 支撐真 local ChatPanel 可以在 tool turn 後維持第二輪正常對話，並修掉 prompt
bloat timeout。它仍不支撐長時間 autonomous tool-command chain、完整資料到訓練操作或真人
Windows walkthrough。

2026-05-04 ChatPanel local Data Interpretation tool-chain walkthrough：

- root cause fixed:
  - 首次真 local-model run 中，turn 1 `scan_source` 成功，但 turn 2
    `preview_interpretation` failed with `Scan a data source before previewing interpretation.`
  - artifact final state 顯示 backend 已有 `latest_scan_id=scan-1`，所以 failure 不是
    ApplicationService lifecycle 遺失，而是 local model 傳入 schema-derived placeholder
    `scan_id`，覆蓋了 backend latest-state fallback。
  - `tool_call_normalizer` 現在只保留 backend 會真生成的 `scan-<n>` / `candidate-<n>` id；
    `latest_scan_id`、`current_candidate` 等 generated placeholder 會移除，讓
    ApplicationService 使用目前 state。
- artifact：
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-ready.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-1.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-2.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-3.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.json`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - expected tools：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
  - executed tools：all `ok`
  - final interpretation state：scan / candidate / preview / validation decision present
  - validation decision：`needs_confirmation`
  - visible transcript has no raw `Tool Output`、schema、traceback or debug payload
  - UI returned idle
- commands:
  - `timeout 620s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool-chain --timeout-seconds 580`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py -q`
  - `30 passed`
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
  - pass
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐真 local ChatPanel 可以做一段 Data Interpretation tool chain，且每 turn
只執行一個 verified ApplicationService-backed command。它仍不支撐 confirm/apply、
preprocess、epoch、dataset、training 的長鏈 autonomous workflow，也不支撐 Windows
Desktop launcher 真人 click-through。

2026-05-04 ChatPanel local import-to-dataset pipeline-chain walkthrough：

- root cause fixed:
  - `apply_standard_preprocess` 已在 agent application surface 直接 route 到
    `PreprocessCommand(operation=STANDARD)`，讓 agent path 回 `ToolCommandResult` / typed
    ApplicationService state，而不是 real-tool legacy string fallback。
  - 首次真 pipeline-chain run 在 `generate_dataset` 被 split audit 擋下：
    `Generated dataset failed split audit; fix empty splits or leakage before training.`
  - failure root cause 是 prompt 只讓 normalizer 抽出 `left` 單一 event，形成 3 epochs；trial
    split 會出現 empty validation。這個 guardrail 沒有放寬。
  - `tool_call_normalizer` 現在可從 `events left and right` 抽多個 event ids，讓 same source
    建出 6 epochs 並通過 split audit。
- artifact：
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-ready.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-1.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-2.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-3.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-4.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-5.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-6.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-7.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.json`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - expected tools：`scan_source` -> `preview_interpretation` -> `validate_interpretation` ->
    `apply_interpretation` -> `apply_standard_preprocess` -> `epoch_data` -> `generate_dataset`
  - executed tools：all `ok`
  - confirmation dialogs observed：`1`
  - final state：applied interpretation `True`、epoch available `True`、epoch count `6`、
    dataset available `True`、dataset count `1`
  - visible transcript has no raw `Tool Output`、schema、traceback or debug payload
  - UI returned idle
- commands:
  - `timeout 840s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-pipeline-chain --timeout-seconds 800`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py::test_application_tool_command_routes_standard_preprocess tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py -q`
  - `32 passed`
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py`
  - pass
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐真 local ChatPanel 可從 Data Interpretation apply confirmation 走到 dataset
ready，且每 turn 只執行一個 verified tool。它仍不支撐 model selection、training settings、
training、evaluation、saliency 的長鏈，也不支撐 Windows Desktop launcher 真人 click-through。

2026-05-04 Data Interpretation non-mocked backend workflow：

- 新增 `tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked`。
- 這條 test 會：
  - 產生 real synthetic MNE `.fif` source。
  - 跑 `scan_source` -> `preview_interpretation` -> `validate_interpretation`。
  - 驗證缺 subject / session / task / run metadata 時 decision 是 `needs_confirmation`。
  - 驗證未確認的 `apply_interpretation` 會被 `confirmation_required` 擋下。
  - 用 `confirmed=True` apply，並確認 raw state / interpretation state 更新。
  - `save_interpretation_recipe` 寫出 recipe。
  - 在新的 `ApplicationService` session 用 `reload_interpretation_recipe` 重新 scan / preview /
    validate，但不直接 apply。
  - 接續跑 normalize preprocess、epoch 和 trial-wise dataset generation，並檢查 split audit 與
    train / val / test counts。
- commands:
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `1 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py -q`
  - `38 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `3 passed`
  - `poetry run ruff check tests/integration/backend/test_application_service_workflow.py`
  - `PASS`
  - `poetry run basedpyright tests/integration/backend/test_application_service_workflow.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 backend non-mocked source -> recipe -> preprocess -> epoch -> dataset
workflow。它仍不等於 UI wizard / ChatPanel 可見行為；UI-observable replay 仍需 screenshot /
visible state / transcript artifact。

2026-05-04 Data Interpretation UI-observable replay artifact：

- 新增 `scripts/dev/capture_data_interpretation_replay.py`。
- replay 會啟動 real `MainWindow` / Dataset panel，在固定 temp source path 產生 synthetic MNE
  `.fif`，並用真 `ApplicationService` 跑 scan / preview / validate / apply。
- artifacts：
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
- replay JSON 保存：
  - transcript。
  - command result 對照。
  - visible Data Interpretation dialog state。
  - metadata preview rows。
  - dataset panel import button text / enabled state。
  - dataset table row count。
  - screenshot filenames。
- observed result：
  - dialog decision：`needs_confirmation`。
  - save recipe checkbox：`checked`。
  - unconfirmed apply：`failed / confirmation_required`。
  - confirmed apply：`ok`。
  - dataset table rows：`1`。
- command:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - exit code `0`

這批 evidence 支撐 Data Interpretation preview dialog 和 applied Dataset panel 的 UI-observable
replay。它仍不是完整真人 click-through，也尚未覆蓋 ChatPanel agent transcript。

2026-05-05 Data Interpretation / Dataset table geometry gate：

- scripts:
  - `scripts/dev/capture_data_interpretation_replay.py`
  - `scripts/dev/capture_human_like_product_walkthrough.py`
- artifacts:
  - `artifacts/ui/data-interpretation-replay.json`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`
- observed result:
  - Data Interpretation replay Dataset table: `header_length=993`, `viewport_width=994`,
    `horizontal_scrollbar_max=0`.
  - Data Interpretation preview/remap metadata, label carrier, event role, and Review Summary
    tree states all record `horizontal_scrollbar_max=0` and `text_elide_mode=ElideRight`.
  - Human-like walkthrough status: `passed`; table geometry review checked `15` table/tree widgets
    with `0` findings.
  - Human-like walkthrough loaded Dataset table: `header_length=509`, `viewport_width=510`,
    `horizontal_scrollbar_max=0`.
- commands:
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
    -> exit `0`.
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`.
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_table_sizing.py -q`
    -> `34 passed`.

這批 evidence 支撐 automated PyQt replay 條件下 Dataset 主表和 Data Interpretation wizard
tables 會填滿容器且不產生水平外溢。它仍不能替代 human desktop acceptance、Windows launcher
click-through、雙螢幕 / DPI 或完整 Data Interpretation embedded label editor 驗收。

2026-05-04 Data Interpretation wizard review hardening：

- `DataInterpretationPreviewDialog` 已從單層 preview modal 硬化為第一版 wizard review surface：
  - title：`Interpret Data Source`
  - visible steps at that slice：`Scan -> Preview -> Validate -> Confirm -> Apply -> Save recipe`
    （2026-05-05 UI polish 已改為 `Select source | Scan result | Preview | Confirm | Apply | Save recipe`）
  - source/readiness group：source path、source kind、file count、label carrier count、BIDS status
  - metadata preview：file / subject / session / task / run
  - labels/events/recipe trace：label carriers、event roles、class map，或 no-carrier boundary
  - review notes at that slice：warnings、confirmations、blocked reasons、downstream impact、
    recipe trace（2026-05-05 UI polish 已改為 structured `Review Summary` table）
  - action button：`Confirm and Apply` for `needs_confirmation`；blocked decision disables apply and
    recipe save。
- replay artifact refreshed:
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 Data Interpretation UI 已比 baseline preview 更接近 import wizard review
surface。下一個 slice 已補 first-pass metadata / class-map review editor；它仍不支撐
format-specific label editor、all-format manual compatibility matrix 或真人 click-through。

2026-05-04 Data Interpretation metadata / class-map editor slice：

- backend:
  - `PreviewInterpretationCommand(choices=...)` 現在可接
    `metadata_overrides`、`class_map`、`event_roles`。
  - metadata override 會把欄位標成 `source=user_override`、`decision=safe`，並寫入
    `metadata_override:<field>` recipe trace。
  - `AppliedInterpretation` / `ImportRecipe` 會保存 `event_roles` 和 `class_map`。
- UI:
  - `DataInterpretationPreviewDialog` 的 metadata review cells 可編輯 subject / session /
    task / run。
  - class map rows 可編輯 meaning。
  - `get_result()` 回傳 review `choices`；Dataset action 會在 apply 前 re-preview /
    re-validate，再套用新的 candidate。
- replay artifact refreshed:
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON 顯示 `review_choices.metadata_overrides`：`S01`、`session-01`、
    `motor-imagery`，且 reviewed preview / apply path 保留 `metadata_override` recipe trace。
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `49 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `37 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `1 passed`

這批 evidence 支撐 first-pass metadata override / class-map review editor 已進入 Data
Interpretation recipe flow。它仍不支撐 format-specific label column / MAT variable / anchor
editor、label import 內嵌 wizard、完整真人 click-through 或全格式 compatibility matrix。

2026-05-04 Data Interpretation label carrier review slice：

- backend:
  - `InterpretationCandidate` / `InterpretationPreview` now expose `label_carrier_plan` /
    `label_carrier_preview` for MAT, CSV / TSV, BIDS `events.tsv`, and TXT carriers.
  - `PreviewInterpretationCommand(choices=...)` accepts `label_carrier_choices` with
    `label_field`, `anchor`, `time_model`, and `granularity`.
  - `AppliedInterpretation` / `ImportRecipe` save the reviewed `label_carrier_plan`, and
    recipe trace records `choices:label_carriers`.
- UI:
  - `DataInterpretationPreviewDialog` now shows editable label carrier review rows for
    carrier, format, label field / MAT variable, anchor, time model, and granularity.
  - `get_result()` returns edited label carrier choices, and Dataset action already
    re-previews / re-validates those choices before applying.
- replay artifact refreshed:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON shows visible `label_carrier_rows` with `trial_type` / `onset` /
    `seconds` / `trial`, and applied interpretation saves the same reviewed plan.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `33 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `50 passed`
  - `poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/service.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/backend/application/test_application_service.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/service.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/backend/application/test_application_service.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 first-pass format-specific label carrier review 已進入 Data Interpretation
wizard，包含 MAT variable / anchor recipe evidence 和 UI-observable BIDS-events / TSV label
column / anchor evidence。它仍不支撐完整 post-load label import 內嵌 wizard、全格式人工
compatibility matrix 或真人 click-through。

2026-05-04 Data Interpretation role review slice：

- UI:
  - `DataInterpretationPreviewDialog` now tracks editable event-role rows and returns
    `choices.event_roles` when the user changes an event role.
  - label carrier review rows gained a visible `Role` column; `get_result()` now returns
    carrier `role` along with target, label field, anchor, time model, and granularity.
- backend evidence:
  - `ApplicationService` recipe test now asserts reviewed label carrier role and event role flow
    into `AppliedInterpretation` / `ImportRecipe`, and recipe trace records
    `choices:event_roles`.
- replay artifact refreshed:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON visible row:
    `events.tsv -> sub-01_task-mi_run-2_raw.fif -> BIDS events -> trial_type -> onset -> seconds -> trial -> class cue labels`
  - replay JSON `review_choices.event_roles.trial_type` is `class cue`.
- TDD evidence:
  - focused UI test first failed because `event_roles` was missing from dialog choices.
  - focused UI test first failed because carrier `role` was missing from `label_carrier_choices`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `8 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
  - `1 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `43 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 Data Interpretation wizard 可讓使用者確認 event role 與 label carrier role，
並把這些語意保存到 recipe choices / backend recipe。它仍不是完整 post-load label import
內嵌 editor、raw trigger selector、全格式 real-data certification 或真人 click-through。

2026-05-04 Data Interpretation label carrier selector UI：

- UI:
  - label carrier review columns for label field, anchor, time model, granularity, and role now use
    `QComboBox` selectors instead of requiring free-form cell typing.
  - selector display text is user-facing for controlled values, e.g. `Seconds`, `Trial`, and
    `Class cue labels`.
  - `get_result()` reads combo `itemData` so recipe choices still carry backend values such as
    `seconds`, `trial`, and `class cue labels`.
- TDD evidence:
  - focused selector test first failed because label/anchor/time/granularity/role cells had no
    combo widgets.
- replay artifact refreshed:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON visible row:
    `events.tsv -> sub-01_task-mi_run-2_raw.fif -> BIDS events -> trial_type -> onset -> Seconds -> Trial -> Class cue labels`
  - replay JSON recipe choices still use `time_model=seconds` and `granularity=trial`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `9 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
  - `1 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 import wizard label carrier review 的使用性改善：使用者不再需要手打主要
review 欄位。它仍不是完整 embedded post-load label import editor、raw trigger selector、
全格式 real-data certification 或真人 click-through。

2026-05-05 Data Interpretation event role selector UI：

- UI:
  - event role review rows now use `QComboBox` selectors instead of editable free-text cells.
  - selector display text is user-facing (`Class cue`, `Time anchor`, etc.) while `get_result()`
    still returns backend recipe values such as `class cue`.
- replay artifact refreshed:
  - `timeout 300s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON `ui_state.dialog.event_rows` now includes
    `trial_type -> event role -> Class cue`.
  - replay JSON `review_choices.event_roles.trial_type` is `class cue`.
- consolidated UI-observable walkthrough refreshed:
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md`
  - summary remains `26 / 26` phases and `20 / 20` nonblank screenshots, with
    `human_desktop_acceptance=not performed`.
- targeted gates:
  - focused UI test first failed because event-role rows were still editable even after a combo
    widget was installed.
  - script unit test first failed because replay code had no helper that could operate the event
    role selector.
  - human-like walkthrough helper test first failed because the consolidated walkthrough still used
    the old `item.setText()` path and did not update the selector-backed recipe.
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py tests/integration/ui/test_product_walkthrough.py -q`
  - `23 passed`
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.

這批 evidence 支撐 event role review 已從任意文字輸入收斂成可辨識 selector，且 automated
UI replay 會實際操作 selector 並保存 visible row。它仍不是完整 raw trigger selector、
complex anchor reconciliation、Windows human acceptance 或全格式 real-data certification。

2026-05-05 Data Interpretation event display polish：

- UI:
  - visible event-role item names now use user-facing text such as `Label carrier`, `Onset`,
    `Duration`, and `Trial type` instead of exposing source/internal keys like `label_carrier`.
  - the group title is now `Label and Event Interpretation`; recipe trace remains in the structured
    `Review Summary` table.
  - backend choice keys are still preserved for recipe replay and command compatibility.
- TDD evidence:
  - focused UI test first failed because visible event-role rows still exposed
    `label_carrier` / `trial_type`.
  - group-title assertion first failed because the dialog still displayed
    `Labels, Events, and Recipe Trace`.
  - replay helper test first failed because it still searched the visible event row by raw
    `trial_type` instead of the source-field tooltip after UI humanization.
- replay artifact refreshed:
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-remap.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - screenshot review shows the visible event rows as `Label carrier`, `Onset`, `Duration`, and
    `Trial type`.
  - replay JSON `dialog.event_rows` records `Label carrier`; backend payloads still keep
    `label_carrier`.
- targeted gates:
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q`
  - `31 passed`
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.

這批 evidence 支撐 Data Interpretation preview 不再把 `label_carrier` 這類 internal-looking key
當成第一層可見文字。它仍不是 full mature import wizard editor、raw trigger selector、Windows
human acceptance 或全格式 real-data certification。

2026-05-05 Data Interpretation decision copy polish：

- UI:
  - top-level wizard status now uses user-facing workflow copy:
    `Review and confirm these choices before applying.` / `Ready to apply.`
  - blocked recipe reload states now ask for replacement EEG or label/event carrier files instead
    of leading with `Validation ... remap` language.
  - backend decision values such as `safe`, `needs_confirmation`, and `blocked` remain unchanged.
- TDD evidence:
  - focused decision-copy test first failed because the dialog still rendered
    `Validation needs confirmation before applying.`
  - full dialog suite then failed on two remaining assertions that were still bound to old remap
    copy.
- replay artifact refreshed:
  - `QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-remap.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - screenshot review shows `Review and confirm these choices before applying.`
  - replay JSON `visible_text` contains the same copy and no `Validation needs` match.
- targeted gates:
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `18 passed`
  - `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
  - `21 passed`
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.

這批 evidence 支撐 Data Interpretation wizard 的頂部狀態不再把 backend validation wording 當成
主要 instruction。它仍不是 full wizard UX completion、Windows human acceptance 或完整
blocked-state redesign。

2026-05-05 Data Interpretation recipe reload rehydration：

- backend:
  - `ReloadInterpretationRecipeCommand` now rebuilds candidate choices from the saved
    `ImportRecipe`: selected EEG files, metadata overrides, label carrier choices, event roles,
    and class map.
  - `ImportRecipe.write_json()` now writes a trailing newline, avoiding regenerated artifact
    EOF-only diffs.
- TDD evidence:
  - recipe unit test first failed because `choices_from_import_recipe` did not exist.
  - non-mocked backend workflow first failed because reload candidate choices only contained
    `recipe_id` and lost metadata / event role / class map choices.
  - recipe writer newline test first failed because JSON was written without a trailing newline.
- UI-observable artifact:
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py`
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` shows reload candidate
    choices for `metadata_overrides`, `label_carrier_choices`, `event_roles`, and
    `selected_eeg_files`.
  - reload candidate recipe trace includes `choices:metadata_overrides`,
    `choices:event_roles`, and `choices:label_carriers`.
  - `artifacts/ui/human-like-walkthrough/07-recipe-reloaded.png` is now the reload preview dialog,
    and phase notes include `Reloaded recipe / Reapplied`.
  - summary remains `26 / 26` phases and `20` screenshots, with
    `human_desktop_acceptance=not performed`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_data_interpretation_recipe.py -q`
  - `4 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `1 passed`
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.

這批 evidence 支撐 recipe reload 會重新套用 saved interpretation choices 後再 preview /
validate，且 wizard review summary 會顯示 reload summary。它仍不是完整 user-facing recipe diff
UI，也不是 human desktop acceptance。

2026-05-04 Dataset Add Labels compatibility guard：

- UI/action:
  - `DatasetSidebar.update_sidebar()` disables `Add Labels to Loaded Data` when no data is loaded
    and uses tooltip text `Interpret a data source before adding labels.`
  - the same button is disabled while the dataset is locked by downstream edits.
  - `DatasetActionHandler.import_label()` checks backend `ImportLabelsCommand` capability before
    opening the compatibility dialog.
  - `_get_target_files_for_import()` now warns immediately when the dataset table has no rows,
    instead of asking whether to apply labels to all files.
- replay artifact refreshed:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-replay.json`
  - empty dataset sidebar evidence:
    `Add Labels to Loaded Data`, enabled `False`, tooltip `Interpret a data source before adding labels.`
  - applied dataset sidebar evidence:
    enabled `True`, tooltip `Add labels to loaded data and update the current recipe trace.`
- TDD evidence:
  - focused sidebar tests first failed because the button remained enabled for locked / empty states.
  - focused action tests first failed because no-data and capability-block guards were missing.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_dataset_sidebar.py -q`
  - `54 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/panels/dataset/actions.py XBrainLab/ui/panels/dataset/sidebar.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 post-load label compatibility path 不再在 empty / blocked state 裡鼓勵舊
attach-label 心智模型。它仍不是完整 embedded Data Interpretation label editor。

2026-05-06 Dataset inline metadata fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_edit_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- Regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `88 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset UI fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` inline Dataset metadata fallback refusal showing product language
instead of escaping. It does not prove complete Dataset desktop acceptance or command-driven UI
refresh closure.

2026-05-06 Preprocess operation fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_filtering_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing because no product blocked warning was shown.
- Regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
  -> `26 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess -q`
  -> `48 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Architecture guard adjustment:
  `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_controller_fallback_guard_allows_named_legacy_wrapper tests/unit/test_architecture_compliance.py::test_controller_fallback_guard_flags_direct_mutation_in_missing_result tests/unit/test_architecture_compliance.py::test_direct_controller_mutation_guard_allows_named_legacy_wrapper_call -q`
  -> `3 passed`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` -> `32 passed`;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Preprocess UI fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` preprocess operation fallback refusal showing operation-specific blocked
warnings. It does not prove long-running preprocessing performance or memory behavior.

2026-05-06 Direct Load compatibility fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_refuses_real_study_direct_load_fallback -q`
  -> `1 passed` after failing because no product blocked warning was shown.
- DatasetActionHandler regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `73 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` direct-load compatibility fallback refusal showing a product warning
instead of trying controller import fallback or surfacing as generic import error. It does not make
direct `load_data` the product data-entry model.

2026-05-06 Smart Parse filename fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_refuses_real_study_filename_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- DatasetActionHandler regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `72 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Smart Parse filename-query fallback refusal showing a product warning
instead of reading stale controller filenames. It does not prove Dataset page desktop acceptance or
complete all DatasetActionHandler fallback cleanup.

2026-05-06 Label Import fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing because the fallback refusal was displayed as generic `Failed: ...`.
- DatasetActionHandler regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `71 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Label Import fallback refusal showing a product warning instead of a
generic critical failure. It does not prove Dataset page desktop acceptance or complete all
DatasetActionHandler fallback cleanup.

2026-05-06 Smart Parse apply fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- DatasetActionHandler regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `70 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Smart Parse apply fallback refusal showing a product warning instead of
an escaped legacy fallback exception. It does not prove Dataset page desktop acceptance or complete
all DatasetActionHandler fallback cleanup.

2026-05-06 Metadata Update fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- DatasetActionHandler regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `69 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Metadata Update fallback refusal showing a product warning instead of an
escaped legacy fallback exception. It does not prove Dataset page desktop acceptance or complete
all DatasetActionHandler fallback cleanup.

2026-05-06 Remove Files fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- DatasetActionHandler regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  -> `68 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Remove Files fallback refusal showing a product warning instead of an
escaped legacy fallback exception. It does not prove Dataset page desktop acceptance or complete
all DatasetActionHandler fallback cleanup.

2026-05-06 Data Splitting context query-none boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_refuses_real_study_query_none_dialog_context -q`
  -> `1 passed` after failing because the dialog opened.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `42 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training command-truth slice, not a release / thesis benchmark
  update.

This supports real `Study` Data Splitting context query-none blocking before dialog creation. It
does not prove full Data Splitting desktop acceptance or complete all TrainingSidebar query/fallback
cleanup.

2026-05-06 Start Training fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on missing blocked warning.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `41 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Start Training fallback refusal showing a product warning instead of a
generic critical error wrapper. It does not prove long-running training desktop acceptance or
complete all TrainingSidebar fallback cleanup.

2026-05-06 Training Settings fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `40 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Training Settings fallback refusal showing a product warning instead of
an escaped legacy fallback exception. It does not prove Training Settings desktop acceptance or
complete all TrainingSidebar fallback cleanup.

2026-05-06 Model Selection fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `39 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Model Selection fallback refusal showing a product warning instead of
an escaped legacy fallback exception. It does not prove Training Settings desktop acceptance or
complete all TrainingSidebar fallback cleanup.

2026-05-06 Data Splitting clear fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_refuses_real_study_clear_none_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `38 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Clear Datasets fallback refusal showing a product warning instead of
an escaped legacy fallback exception. It does not prove Data Splitting desktop acceptance or
complete all TrainingSidebar fallback cleanup.

2026-05-06 Generate Dataset apply fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_refuses_real_study_generate_none_controller_fallback -q`
  -> `1 passed` after failing on escaped legacy fallback exception.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `37 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Generate Dataset fallback refusal showing a product warning instead of
an escaped legacy fallback exception. It does not prove Data Splitting desktop acceptance or
complete all TrainingSidebar fallback cleanup.

2026-05-06 Channel Selection apply fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_refuses_real_study_apply_none_controller_fallback -q`
  -> `1 passed` after failing on missing blocked warning.
- DatasetSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
  -> `14 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Channel Selection apply fallback refusal showing a product warning
instead of a generic critical error wrapper. It does not prove Channel Selection desktop
acceptance or complete all DatasetSidebar fallback cleanup.

2026-05-06 Dataset Clear fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on missing blocked warning.
- DatasetSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
  -> `13 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Dataset fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Clear Dataset fallback refusal showing a product warning instead of a
generic critical error wrapper. It does not prove desktop reset/new-session acceptance or complete
all DatasetSidebar fallback cleanup.

2026-05-06 Preprocess Reset fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on generic critical reset failure.
- PreprocessSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
  -> `25 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Preprocess fallback language slice, not a release / thesis
  benchmark update.

This supports real `Study` Reset Preprocess fallback refusal showing a product warning instead of
a generic critical error wrapper. It does not prove long-running preprocessing desktop acceptance
or complete all PreprocessSidebar fallback cleanup.

2026-05-06 Clear History fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on generic `Warning` / `Error clearing history`.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `36 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Full fast gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice, not a release / thesis
  benchmark update; primary/fallback x3 remains reserved for the formal gate after resource
  preflight.

This supports real `Study` Clear History fallback refusal showing a product warning instead of a
generic error wrapper. It does not prove long-running training desktop acceptance or complete all
TrainingSidebar fallback cleanup.

2026-05-06 Stop Training fallback warning boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_refuses_real_study_controller_fallback -q`
  -> `1 passed` after failing on escaped `LegacyControllerFallbackUnavailableError`.
- TrainingSidebar regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar -q`
  -> `35 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`.
- Static / docs / backend / agent gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training fallback language slice.

This supports real `Study` Stop Training fallback refusal showing a product warning instead of a
raw runtime exception. It does not prove long-running training desktop acceptance or complete all
TrainingSidebar fallback cleanup.

2026-05-06 Visualization average stale-selection fallback boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_refuses_real_study_query_none_average_fallback -q`
  -> `1 passed` after failing on stale `VisualizationController.get_averaged_record()` before the
  fix.
- Visualization regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
  -> `66 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
  -> `0 errors`.
- Static / docs / backend / agent gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Visualization render fallback boundary slice.

This supports real `Study` Visualization stale Average selections showing the existing no-average
message instead of reading stale controller averaged records. It does not prove full Visualization
UX, saliency/canvas screenshot acceptance, or human desktop acceptance.

2026-05-06 Evaluation stale-selection fallback boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_refuses_real_study_query_none_metric_fallback -q`
  -> `1 passed` after initially exposing unstable `last_application_query` state in the same
  stale-selection path.
- Evaluation regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_ui_structure_refactored.py -q`
  -> `13 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py`
  -> `0 errors`.
- Static / docs / backend / agent gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Evaluation render fallback boundary slice.

This supports real `Study` Evaluation stale average/summary selections clearing safely instead of
reading stale controller pooled metrics or summaries. It does not prove full Evaluation UX or human
desktop acceptance.

2026-05-06 Training history query-none render fallback boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py::test_training_panel_refuses_real_study_query_none_controller_history -q`
  -> `1 passed` after failing on stale `TrainingController.get_formatted_history()` before the fix.
- Training panel regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/training/test_training_panel.py tests/unit/ui/test_panel_event_bridges.py -q`
  -> `33 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/training/panel.py tests/unit/ui/training/test_training_panel.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/training/panel.py`
  -> `0 errors`.
- Static / docs / backend / agent gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Training render fallback boundary slice.

This supports real `Study` training-history query-none fallback clearing to empty display instead
of reading stale controller history. It does not prove Training UX, long-running training soak, or
human desktop acceptance.

2026-05-06 Visualization query-none render fallback boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_visualization_panel_redesign.py::test_visualization_panel_refuses_real_study_query_none_controller_fallback -q`
  -> `1 passed` after failing on stale `VisualizationController.get_trainers()` before the fix.
- Visualization regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
  -> `65 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/visualization/panel.py tests/unit/ui/test_visualization_panel_redesign.py`
  -> `0 errors`.
- Static / docs / backend / agent gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Visualization render fallback boundary slice.

This supports real `Study` Visualization panel query-none fallback keeping empty controls instead
of reading stale controller trainers. It does not prove full Visualization UX, saliency/canvas
screenshot acceptance, or human desktop acceptance.

2026-05-06 Evaluation query-none render fallback boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py::test_evaluation_panel_refuses_real_study_query_none_controller_fallback -q`
  -> `1 passed` after failing on stale `EvaluationController.get_plans()` before the fix.
- Evaluation regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_evaluation_panel_redesign.py tests/unit/ui/test_ui_structure_refactored.py -q`
  -> `12 passed`.
- Focused lint/type/architecture:
  `poetry run ruff check XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/evaluation/panel.py tests/unit/ui/test_evaluation_panel_redesign.py`
  -> `0 errors`;
  `poetry run python tests/architecture_compliance.py` -> pass.
- Static / docs / backend / agent gate:
  `git diff --check` -> pass;
  `poetry run ruff check .` -> pass;
  `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `poetry run python tests/architecture_compliance.py` -> pass;
  `poetry run mkdocs build --strict` -> pass;
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Evaluation render fallback boundary slice.

This supports real `Study` Evaluation panel query-none fallback rendering no-data instead of stale
controller plans. It does not prove full Evaluation UX or human desktop acceptance.

2026-05-06 Visualization fallback refusal product warning：

- Focused gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_export_saliency_refuses_real_study_query_none_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_apply_none_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_refuses_real_study_controller_fallback tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_apply_none_refuses_real_study_controller_fallback -q`
  -> `5 passed` after red failures where fallback refusal escaped as an exception.
- Visualization regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization_panel_coverage.py tests/unit/ui/test_visualization.py -q`
  -> `64 passed`.
- Focused lint/type/architecture:
  `poetry run ruff check XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/visualization/control_sidebar.py tests/unit/ui/visualization/test_control_sidebar.py`
  -> `0 errors`;
  `poetry run python tests/architecture_compliance.py` -> pass.
- Static / docs / backend / agent gate:
  `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
  `poetry run mkdocs build --strict`, and
  `poetry run pytest --capture=sys tests/integration/backend -q` all passed
  (`7` backend tests);
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate Visualization UI fallback language slice.

This supports real `Study` Montage / Saliency Settings / Export Saliency fallback refusal showing
product warnings rather than raw exceptions. It does not prove full Visualization UX, desktop 3D
acceptance, or saliency workflow completion.

2026-05-06 Preprocess render query-none fallback boundary：

- Focused red/fixed gates:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess/test_preprocess_panel.py::test_update_panel_refuses_real_study_query_none_controller_fallback tests/unit/ui/preprocess/test_preprocess_plotter.py::test_plot_sample_data_refuses_real_study_query_none_controller_fallback -q`
  -> `2 passed` after failing on stale controller list/readiness reads before the fix.
- Preprocess regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/preprocess tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar -q`
  -> `73 passed`.
- Focused lint/type/architecture:
  `poetry run ruff check XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/preprocess/panel.py XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_plotter.py`
  -> `0 errors`;
  `poetry run python tests/architecture_compliance.py` -> pass.
- Static / docs / backend / agent gate:
  `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
  `poetry run mkdocs build --strict`, and
  `poetry run pytest --capture=sys tests/integration/backend -q` all passed
  (`7` backend tests);
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate UI render fallback boundary slice.

This supports real `Study` Preprocess panel/plotter query-none fallback refusing stale controller
list reads. It does not prove long-run plotting memory stability or complete all UI refresh debt.

2026-05-06 Dataset/Preprocess query-unavailable fallback boundary：

- Focused red/fixed gates:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_refuses_real_study_query_none_controller_fallback tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_refuses_real_study_query_none_controller_fallback -q`
  -> `2 passed` after failing on stale controller list reads before the fix.
- Sidebar regressions:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
  -> `37 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/preprocess/test_preprocess_plotter.py tests/unit/ui/preprocess/test_data_query.py -q`
  -> `31 passed`.
- Focused lint/type/architecture:
  `poetry run ruff check XBrainLab/ui/panels/preprocess/sidebar.py XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/preprocess/sidebar.py XBrainLab/ui/panels/dataset/sidebar.py tests/unit/ui/test_sidebars_and_components.py`
  -> `0 errors`;
  `poetry run python tests/architecture_compliance.py` -> pass.
- Static / docs / backend / agent gate:
  `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
  `poetry run mkdocs build --strict`, and
  `poetry run pytest --capture=sys tests/integration/backend -q` all passed
  (`7` backend tests);
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate UI fallback boundary slice.

This supports the safety boundary that real `Study` Channel Selection / Epoching dialog source
fallbacks will block rather than read stale controller lists if the service query path unexpectedly
returns no result. It does not prove all controller read fallbacks are gone.

2026-05-06 DatasetPanel query-none render fallback boundary：

- Focused red/fixed gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_update_panel_refuses_real_study_query_none_controller_fallback -q`
  -> failed as expected on stale `DatasetController.get_loaded_data_list()` read before the fix,
  then `1 passed`.
- Dataset / replay regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
  -> `35 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
  -> pass;
  `poetry run basedpyright XBrainLab/ui/panels/dataset/panel.py tests/unit/ui/dataset/test_panel.py`
  -> `0 errors`.
- Local eval:
  not run. This was a fast dev gate UI render-truth cleanup.

This supports real `Study` Dataset table refresh refusing stale controller list reads when the
service query path unexpectedly returns no result. It does not prove all Dataset render fallbacks,
UI refresh debt, or human desktop acceptance are complete.

2026-05-06 Stale render fallback architecture guard：

- New static guard:
  - `check_ui_controller_render_fallbacks()` flags direct controller render reads inside
    `result is None` branches unless the read is inside `run_legacy_controller_fallback()`.
  - Covered methods include data lists, preprocess lists, training history, evaluation plans,
    visualization trainers, montage channel defaults, saliency params, and related render payloads.
- Focused red/fixed gate:
  `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py::test_controller_render_fallback_guard_flags_stale_read_in_missing_result tests/unit/test_architecture_compliance.py::test_controller_render_fallback_guard_allows_explicit_legacy_wrapper -q`
  -> failed before the guard existed, then `2 passed`.
- Architecture regression:
  `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q` -> `34 passed`;
  `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`.
- Focused lint/type:
  `poetry run ruff check tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
  -> pass;
  `poetry run basedpyright tests/architecture_compliance.py tests/unit/test_architecture_compliance.py`
  -> `0 errors`.
- Static / docs / backend / agent gate:
  `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
  `poetry run mkdocs build --strict`, `poetry run pytest --capture=sys tests/integration/backend -q`,
  and
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  all passed; backend integration `7 passed`, agent/tool gate `20 passed`.
- Local eval:
  not run. This was a static architecture guard under the fast dev gate.

This prevents one class of stale UI render fallback regression. It does not prove the UI refresh
coordinator is fully command-driven or that every controller read has been eliminated.

2026-05-06 Dataset label target fallback boundary：

- Focused gate:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_real_study_refuses_controller_target_fallback -q`
  -> `1 passed`.
- Regression:
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_import_label.py -q`
  -> `105 passed`.
- Focused lint/type:
  `poetry run ruff check XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> pass；
  `poetry run basedpyright XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py`
  -> `0 errors` and `.basedpyright/baseline.json` dropped by one suppressed
  `DatasetActionHandler` optional-controller issue.
- Static / architecture / docs gate:
  `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
  `poetry run python tests/architecture_compliance.py`, and `poetry run mkdocs build --strict`
  all passed.
- Backend / agent regression:
  `poetry run pytest --capture=sys tests/integration/backend -q` -> `7 passed`;
  `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `20 passed`.
- Local eval:
  not run. This was a fast dev gate UI fallback boundary slice; full primary / fallback x3 local
  eval remains release / thesis gate only and requires VRAM / disk / cache preflight.

This supports real `Study` label target selection refusing stale
`DatasetController.get_loaded_data_list()` when selected Dataset table rows do not carry
`UserRole` data. It does not make post-load label import the primary data-entry workflow or a
mature import wizard.

2026-05-05 Dataset Smart Parse capability follow-up：

- UI/action:
  - `DatasetActionHandler.open_smart_parser()` now checks backend `apply_smart_parse` capability
    before opening `SmartParserDialog`.
  - Empty real `Study` state shows the shared backend reason
    `Load raw data before applying smart parse.` instead of opening a metadata mutation dialog.
- targeted gates:
  - focused red + success path:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_uses_backend_capability tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_success -q`
    -> `2 passed`.
  - Dataset action/panel regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py -q`
    -> `60 passed`.
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.

這批 evidence 支撐 Smart Parse UI preflight 與 backend capability policy 對齊。它仍不是完整
UI mutating-path audit 或 human desktop acceptance。

2026-05-05 Dataset Remove Files capability follow-up：

- UI/action:
  - `_remove_files()` now checks backend `remove_files` capability before showing the destructive
    confirmation dialog.
  - Empty real `Study` state shows the shared backend reason
    `Load raw data before removing files.` instead of asking the user to confirm a blocked action.
- targeted gates:
  - focused red + compatibility paths:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files_uses_backend_capability_before_confirm tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_remove_files tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_context_menu_remove -q`
    -> `3 passed`.
  - Dataset action/panel regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py -q`
    -> `61 passed`.
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.

這批 evidence 支撐 context-menu Remove Files UI preflight 與 backend capability policy 對齊。它
仍不是完整 UI mutating-path audit 或 human desktop acceptance。

2026-05-05 Dataset Batch Metadata capability follow-up：

- UI/action:
  - `_batch_set()` now checks backend `update_metadata` capability before opening the Subject /
    Session input dialog.
  - Empty real `Study` state shows the shared backend reason
    `Load raw data before updating metadata.` instead of asking for metadata that cannot be applied.
- targeted gates:
  - focused red + compatibility paths:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_uses_backend_capability_before_prompt tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_batch_set_session tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_context_menu_session -q`
    -> `3 passed`.
  - Dataset action/panel regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_panel.py -q`
    -> `62 passed`.
  - focused `ruff check` -> pass.
  - focused `basedpyright` -> `0 errors, 0 warnings, 0 notes`.

這批 evidence 支撐 context-menu batch metadata UI preflight 與 backend capability policy 對齊。它
仍不是完整 UI mutating-path audit 或 human desktop acceptance。

2026-05-05 Montage dialog capability follow-up：

- UI/action:
  - `AgentManager.open_montage_picker_dialog()` now checks backend `apply_montage` capability
    before opening `PickMontageDialog` for real `Study` paths.
  - Empty real `Study` state shows the shared backend reason
    `Create epochs before applying a montage.` instead of opening a dialog or relying only on a
    local epoch-data guard.
  - Accepted montage on real `Study` goes through `ApplyMontageCommand`; UI-side preprocess
    controller fallback remains only for mock / legacy non-Study compatibility.
- targeted gates:
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker -q`
    -> `5 passed`.
  - AgentManager UI regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep -q`
    -> `48 passed`.
  - backend command handler regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_montage_command_routes_confirmed_positions tests/unit/backend/application/test_analysis_service.py -q`
    -> `3 passed`.

這批 evidence 支撐 montage dialog blocked / success path 與 backend capability policy 對齊。它仍
不是完整 visualization UI product acceptance、interactive desktop render 驗收或 Windows human
desktop click-through。

2026-05-06 AgentManager montage fallback warning：

- UI/action:
  - `AgentManager.open_montage_picker_dialog()` now catches legacy fallback refusal when a real
    `Study` `ApplyMontageCommand` unexpectedly returns no service result.
  - The real `Study` path shows `Montage setup blocked: ...`, does not call
    `PreprocessController.apply_montage()`, and does not add `Montage Confirmed`.
  - Mock / legacy non-`Study` compatibility still keeps the old controller fallback.
- targeted gates:
  - Red/focused:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py::TestMontagePicker::test_real_study_montage_refuses_controller_fallback -q`
    -> failed as expected before the fix, then `1 passed`.
  - AgentManager regression:
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui/test_agent_manager_coverage.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_ui_misc.py::TestAgentManagerDeep -q`
    -> `83 passed`.
  - Quality gate:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, `poetry run mkdocs build --strict`,
    `poetry run pytest --capture=sys tests/integration/backend -q`, and
    `QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/integration/agent/test_tool_call_eval.py -q`
    all passed; backend integration `7 passed`, agent/tool gate `20 passed`.
- local eval:
  - not run. This was a fast dev gate UI fallback-language slice; primary/fallback x3 remains
    reserved for formal release / thesis evidence after resource preflight.

This supports the assistant montage confirmation missing-result boundary showing a product blocked
status instead of an escaped exception. It does not prove full ChatPanel recovery UX, Windows
desktop acceptance, or all remaining controller fallback cleanup.

2026-05-05 Visualization sidebar montage capability follow-up：

- UI/action:
  - `ControlSidebar.set_montage()` now checks backend `apply_montage` capability before opening
    `PickMontageDialog` for real `Study` paths.
  - Empty real `Study` state shows `Create epochs before applying a montage.` from backend
    capability policy.
  - Real `Study` success path uses `ApplyMontageCommand`; stale controller-local
    `has_epoch_data()` no longer blocks an otherwise enabled backend command.
- targeted gates:
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_blocked_by_backend_capability tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_montage_real_study_uses_application_service -q`
    -> `2 passed`.
  - Visualization sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_dialogs_extra.py::TestControlSidebar -q`
    -> `10 passed`.
  - backend command handler regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_montage_command_routes_confirmed_positions tests/unit/backend/application/test_analysis_service.py -q`
    -> `3 passed`.

這批 evidence 支撐 Visualization sidebar montage blocked / success path 與 backend capability
policy 對齊。它仍不是完整 visualization UI product acceptance 或 desktop render 驗收。

2026-05-05 Training clear-history capability follow-up：

- UI/action:
  - `TrainingSidebar.clear_history()` now checks backend `clear_training_history` capability before
    showing the destructive confirmation dialog for real `Study` paths.
  - Empty real `Study` state shows `No training history is available to clear.` from backend
    capability policy, and does not ask the user to confirm an impossible cleanup.
  - mock / legacy non-Study tests keep the existing controller-local `is_training()` guard and
    fallback behavior.
- targeted gates:
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_clear_history_uses_backend_capability_before_confirm -q`
    -> `1 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `43 passed`.
  - backend training command regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py tests/unit/backend/application/test_application_service.py::test_clear_datasets_and_training_history_commands_route_cleanup tests/unit/backend/application/test_application_service.py::test_evaluate_and_clear_history_block_when_trainer_has_no_plan_history tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `6 passed`.

這批 evidence 支撐 destructive clear-history UI boundary 與 backend capability policy 對齊。它仍
不是完整 training UI / long-running training human acceptance。

2026-05-05 Reset preprocessing capability follow-up：

- UI/action:
  - `PreprocessSidebar.reset_preprocess()` now checks backend `reset_preprocess` capability instead
    of reusing the `preprocess` capability through `check_data_loaded()`.
  - Empty real `Study` state shows `Load raw data before resetting preprocessing.` before any
    confirmation prompt.
  - Epoched / preprocessing-locked real `Study` path can still execute `ResetPreprocessCommand`
    when backend `reset_preprocess` is enabled, instead of being blocked by the edit-preprocess
    policy.
- targeted gates:
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_uses_reset_capability_when_preprocess_locked tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_reset_preprocess_blocked_by_reset_capability_before_confirm -q`
    -> `2 passed`.
  - Preprocess sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess/test_preprocess_panel.py -q`
    -> `31 passed`.
  - backend lifecycle regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_lifecycle_service.py tests/unit/backend/application/test_application_service.py::test_reset_preprocess_command_clears_downstream_training_plan tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `5 passed`.

這批 evidence 支撐 reset-preprocess lifecycle UI boundary 與 backend capability policy 對齊。它
仍不是完整 reset / new-session human desktop acceptance。

2026-05-05 Training configuration dialog capability follow-up：

- UI/action:
  - `TrainingSidebar.select_model()` and `TrainingSidebar.training_setting()` now check backend
    `configure_training` capability before opening model / training-settings dialogs for real
    `Study` paths.
  - Real backend training-running state shows `Stop training before changing training
    configuration.` and does not open configuration dialogs, even if controller-local
    `is_training()` is stale.
  - mock / legacy non-Study paths keep the existing controller-local compatibility guard.
- targeted gates:
  - focused red + dialog gate:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_select_model_uses_backend_configure_capability_before_dialog tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_training_setting_uses_backend_configure_capability_before_dialog -q`
    -> `2 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `45 passed`.
  - backend configure-training smoke:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py::test_training_service_configures_model_and_options tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes tests/unit/backend/application/test_application_service.py::test_capability_policy_covers_all_declared_commands -q`
    -> `3 passed`.

這批 evidence 支撐 training configuration dialogs 與 backend capability policy 對齊。它仍不是完整
training setup UX 或 long-running training acceptance。

2026-05-05 Stop training capability follow-up：

- UI/action:
  - `TrainingSidebar.stop_training()` now checks backend `stop_training` capability for real
    `Study` paths.
  - Real backend running state still executes `StopTrainingCommand` even if controller-local
    `is_training()` is stale false.
  - Empty / not-running real `Study` state shows `No training run is active.` and does not call the
    command layer.
- targeted gates:
  - focused red + command path:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_uses_backend_capability_when_controller_stale tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_stop_training_blocked_by_backend_capability_before_command -q`
    -> `2 passed`.
  - Training sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q`
    -> `47 passed`.
  - backend stop-training smoke:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_training_service.py::test_training_service_start_stop_and_clear_history tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes tests/unit/backend/application/test_application_service.py::test_capability_policy_covers_all_declared_commands -q`
    -> `3 passed`.

這批 evidence 支撐 stop-training UI action 與 backend capability policy 對齊。它仍不是完整
long-running training human acceptance。

2026-05-05 Dataset inline metadata capability follow-up：

- UI/action:
  - `DatasetPanel.update_panel()` now reads backend `update_metadata` capability and renders
    Subject / Session cells read-only with the shared blocked reason when raw metadata editing is
    blocked.
  - `DatasetPanel.on_item_changed()` also preflights `update_metadata` capability, so programmatic
    item changes cannot bypass the visible editability state.
  - mock / legacy non-Study paths keep the existing editable table and controller fallback.
- targeted gates:
  - focused red + editability:
    `poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py::test_dataset_panel_metadata_cells_use_backend_update_capability -q`
    -> `1 passed`.
  - Dataset panel / action regression:
    `poetry run pytest --capture=sys tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_panel_minimal.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
    -> `65 passed`.
  - backend metadata command regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_data_table_service.py tests/unit/backend/application/test_application_service.py::test_metadata_update_command_routes_through_service tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `6 passed`.

這批 evidence 支撐 dataset inline metadata editability 與 backend capability policy 對齊。它仍不是
完整 Data Interpretation wizard editor 或 full dataset table UX acceptance。

2026-05-05 Visualization saliency settings capability follow-up：

- UI/action:
  - `ControlSidebar.set_saliency()` now checks backend `saliency` capability before opening
    `SaliencySettingDialog` for real `Study` paths.
  - Empty real `Study` state shows the shared saliency readiness reason instead of opening a
    settings dialog that cannot be applied.
  - mock / legacy non-Study paths keep the existing dialog and controller fallback behavior.
- targeted gates:
  - focused red + dialog gate:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py::test_sidebar_set_saliency_blocked_by_backend_capability -q`
    -> `1 passed`.
  - Visualization sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/visualization/test_control_sidebar.py tests/unit/ui/test_dialogs_extra.py::TestControlSidebar -q`
    -> `11 passed`.
  - backend saliency command regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py::test_visualize_and_saliency_commands_return_typed_query_payloads tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes -q`
    -> `5 passed`.

這批 evidence 支撐 Visualization sidebar saliency settings dialog 與 backend capability policy
對齊。它仍不是完整 saliency workflow UX 或 visualization desktop render acceptance。

2026-05-05 Dataset clear-session capability follow-up：

- UI/action:
  - `DatasetSidebar.clear_dataset()` now reads backend `reset_session` capability before deciding
    whether a destructive confirmation prompt is needed.
  - Empty real `Study` state no longer asks for confirmation before the no-op reset-session path.
  - mock / legacy non-Study paths keep the existing confirmation and controller fallback.
- targeted gates:
  - focused red + confirmation boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_clear_dataset_uses_reset_session_capability_before_confirm -q`
    -> `1 passed`.
  - Dataset sidebar regression:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar tests/unit/ui/dataset/test_panel.py::test_dataset_panel_clear_dataset tests/unit/ui/dataset/test_panel_minimal.py -q`
    -> `10 passed`.
  - backend lifecycle regression:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_lifecycle_service.py tests/unit/backend/application/test_application_service.py::test_blocked_query_and_lifecycle_commands_still_return_result_envelopes tests/unit/backend/application/test_application_service.py::test_capability_policy_covers_all_declared_commands -q`
    -> `5 passed`.

這批 evidence 支撐 Dataset clear action 與 backend reset-session confirmation policy 對齊。它仍
不是完整 reset/new-session human desktop acceptance。

2026-05-05 Data Interpretation recipe save capability follow-up：

- UI/action:
  - `DatasetActionHandler._save_interpretation_recipe()` now checks backend
    `save_interpretation_recipe` capability before opening the file-save dialog.
  - Label import recipe trace updates skip the `Save Updated Recipe` confirmation when backend
    capability says saving is blocked; the success message stays at session-trace scope.
  - mock / legacy non-Study paths keep the existing file dialog and command fallback behavior.
- targeted gates:
  - focused red + capability boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_save_interpretation_recipe_uses_backend_capability_before_file_dialog tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_offer_label_recipe_save_skips_confirmation_when_save_blocked -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 recipe save UI confirmation boundary 與 backend capability policy 對齊。它仍
不是完整 import wizard recipe UX acceptance。

2026-05-05 Training data-splitting capability follow-up：

- backend/action:
  - `generate_dataset` capability now blocks while training is running.
  - `clear_datasets` capability now blocks while training is running and command execution no
    longer clears datasets in that state.
- UI/action:
  - `TrainingSidebar.split_data()` checks backend `generate_dataset` capability before opening
    `DataSplittingDialog` on real `Study` paths.
  - Existing dataset replacement remains allowed only when the sole generate blocker is the active
    dataset/trainer replacement boundary and backend `clear_datasets` is enabled.
  - mock / legacy non-Study paths keep the existing controller-local checks and fallback behavior.
- targeted gates:
  - focused backend red + policy boundary:
    `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_generate_dataset_blocks_while_training_is_running tests/unit/backend/application/test_application_service.py::test_clear_datasets_blocks_while_training_is_running -q`
    -> first run failed, implementation run passed.
  - focused UI red + replacement boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_uses_backend_generate_capability_before_dialog tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_split_data_allows_backend_replacement_boundary -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 Training data-splitting UI gate 與 backend dataset-generation capability policy
對齊。它仍不是完整 long-running training workflow 或 resource cleanup acceptance。

2026-05-05 Dataset Smart Parse source-of-truth follow-up：

- UI/action:
  - `DatasetActionHandler.open_smart_parser()` now treats backend `apply_smart_parse` capability as
    the real `Study` source of truth before opening `SmartParserDialog`.
  - Controller-local `is_locked()` / `has_data()` checks are limited to mock / legacy non-Study
    compatibility paths.
  - Controller fallback execution remains limited to `execute_application_command() is None`.
- targeted gates:
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_open_smart_parser_prefers_backend_capability_over_stale_controller -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 Smart Parse dialog gate 不再被 stale controller state 蓋過 backend
capability truth。它仍不是完整 metadata editor 或 Data Interpretation wizard UX acceptance。

2026-05-05 Dataset Channel Selection source-of-truth follow-up：

- UI/action:
  - `DatasetSidebar.open_channel_selection()` now treats backend `preprocess` capability as the
    real `Study` source of truth before confirmation and `ChannelSelectionDialog`.
  - Controller-local `has_data()` / `is_locked()` checks are limited to mock / legacy non-Study
    compatibility paths.
  - Controller fallback execution remains limited to `execute_application_command() is None`.
- targeted gates:
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_open_channel_selection_prefers_backend_capability_over_stale_controller -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 Channel Selection dialog gate 不再被 stale controller state 蓋過 backend
capability truth。它仍不是完整 preprocessing UX 或 Data Interpretation wizard acceptance。

2026-05-05 Data Interpretation source-entry source-of-truth follow-up：

- UI/action:
  - `DatasetActionHandler.import_data()` now treats backend `scan_source` capability as the real
    `Study` source of truth before the main file source dialog.
  - `DatasetActionHandler._can_start_interpretation()` does the same for folder/BIDS source import
    and other source-entry flows that pass a backend capability.
  - Controller-local `is_locked()` checks are limited to mock / legacy non-Study compatibility
    paths.
- targeted gates:
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_prefers_backend_scan_capability_over_stale_controller tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_folder_prefers_backend_scan_capability_over_stale_controller -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 file / folder Data Interpretation source entry 不再被 stale controller lock state
蓋過 backend capability truth。它仍不是完整 Data Interpretation wizard UX 或 human desktop import
acceptance。

2026-05-05 Preprocess helper source-of-truth follow-up：

- UI/action:
  - `PreprocessSidebar.check_lock()` and `check_data_loaded()` now treat backend `preprocess`
    capability as the real `Study` source of truth for shared preprocessing action gates.
  - Controller-local `is_epoched()` / `has_data()` checks are limited to mock / legacy non-Study
    compatibility paths.
- targeted gates:
  - focused red + stale-controller boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_lock_prefers_backend_capability_over_stale_controller tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_check_data_loaded_prefers_backend_capability_over_stale_controller -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 Preprocess shared helper gates 不再被 stale controller state 蓋過 backend
capability truth。它仍不是完整 preprocessing workflow UI acceptance 或 signal/thread lifecycle
validation。

2026-05-05 Dataset sidebar visible capability follow-up：

- UI/action:
  - `DatasetSidebar.update_sidebar()` now reads live `scan_source`,
    `reload_interpretation_recipe`, and `apply_smart_parse` capabilities for visible button
    enabled / tooltip state.
  - Smart Parse is disabled with the backend blocked reason on an empty real `Study`.
  - Stale controller lock no longer changes real `Study` source-entry / recipe reload tooltips when
    backend capability allows those actions.
- targeted gates:
  - focused red + visible-state boundary:
    `poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_uses_backend_smart_parse_capability tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar::test_update_sidebar_prefers_backend_capabilities_over_stale_lock -q`
    -> first run failed, implementation run passed.
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
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 Dataset sidebar visible state 與 backend capability policy 對齊。它仍不是完整
Dataset page visual design pass 或 UI-observable walkthrough acceptance。

2026-05-05 Dataset sidebar replay artifact refresh：

- replay/action:
  - Added reusable replay helpers for Dataset sidebar button text / enabled / tooltip state.
  - `artifacts/ui/data-interpretation-replay.json` now records all Dataset sidebar buttons for both
    empty and applied dataset phases.
- targeted gates:
  - replay helper:
    `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py -q`
    -> `2 passed`.
  - replay + Dataset sidebar regression:
    `poetry run pytest --capture=sys tests/unit/scripts/test_capture_data_interpretation_replay.py tests/unit/ui/test_sidebars_and_components.py::TestDatasetSidebar -q`
    -> `12 passed`.
  - UI-observable replay artifact:
    `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
    -> exit `0`; refreshed `artifacts/ui/data-interpretation-replay.json`.
  - artifact evidence:
    empty Smart Parse enabled `false` with tooltip `Load raw data before applying smart parse.`;
    applied Smart Parse enabled `true` with tooltip `Auto-extract Subject/Session from filenames`.
  - required backend/agent gates:
    `poetry run pytest --capture=sys tests/unit/backend/application -q`
    -> `104 passed`.
    `poetry run pytest --capture=sys tests/integration/backend -q`
    -> `3 passed`.
    `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
    -> `470 passed`.
    `poetry run pytest --capture=sys tests/integration/agent -q`
    -> `7 passed`.
  - full quality gates:
    `git diff --check`, `poetry run ruff check .`, `poetry run basedpyright`,
    `poetry run python tests/architecture_compliance.py`, and
    `poetry run mkdocs build --strict` passed. MkDocs emitted the existing Material warning only.

這批 evidence 支撐 UI-observable replay artifact 現在保留 Dataset sidebar button visible state。
它仍不是完整 human desktop acceptance 或 full Data Interpretation wizard visual redesign。

2026-05-04 Data Interpretation format capability boundary slice：

- backend:
  - `ScanResult` / `InterpretationCandidate` / `InterpretationPreview` / `AppliedInterpretation` /
    `ImportRecipe` now carry `format_capabilities`.
  - Scan reports review boundaries for GDF, EDF / BDF, EEGLAB `.set`, BrainVision `.vhdr` /
    `.vmrk`, MNE FIF, MAT labels, CSV / TSV labels, BIDS `events.tsv`, TXT labels, and XDF / LSL.
  - XDF / LSL is explicit `blocked` with a user-facing stream-selection unavailable reason; mixed
    folders with supported EEG keep importing the supported source while warning that blocked
    sources are not applied.
- UI:
  - At that slice, `DataInterpretationPreviewDialog` review notes included a `Format capabilities`
    section and converted internal statuses such as `needs_review` into visible text like
    `needs review`; this is superseded by the 2026-05-05 `Review Summary` table.
- replay artifact refreshed:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON then used `review_notes`; current replay JSON uses `review_summary_rows`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `34 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `51 passed`
  - targeted `ruff` / `basedpyright` clean.

這批 evidence 支撐 import wizard 不再把特殊格式當成泛泛 label/event warning；使用者可以看到
哪些格式已可載入但需要語意確認，哪些格式目前 blocked。它仍不是 full manual compatibility
matrix 或 XDF stream parser implementation。

2026-05-04 Data Interpretation generated format capability matrix：

- artifacts:
  - `artifacts/data_interpretation/format-capability-matrix.json`
  - `artifacts/data_interpretation/format-capability-matrix.md`
- generator:
  - `scripts/dev/report_data_interpretation_format_matrix.py`
  - 透過 live `ApplicationService.execute(ScanSourceCommand)`、
    `PreviewInterpretationCommand`、`ValidateInterpretationCommand` 產生 matrix，而不是從 docs
    hard-code 產品 claim。
- coverage:
  - `13` rows across `9` synthetic scan fixtures。
  - 覆蓋 GDF、EDF、BDF、EEGLAB SET、BrainVision VHDR、BrainVision VMRK、MNE FIF、MAT labels、
    CSV labels、TSV labels、BIDS `events.tsv`、TXT labels、XDF / LSL stream export。
  - statuses 覆蓋 `supported`、`needs_review`、`context`、`blocked`。
  - validation decisions 覆蓋 `safe`、`needs_confirmation`、`blocked`。
- tests / commands:
  - TDD failure: initial focused test failed with
    `ModuleNotFoundError: No module named 'scripts.dev.report_data_interpretation_format_matrix'`。
  - CLI JSON purity failure: initial CLI test failed because `Study initialized` logs polluted
    stdout before JSON。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
  - `4 passed`
  - targeted `ruff check` / `ruff format --check` for the reporter and tests -> pass.
  - `poetry run basedpyright scripts/dev/report_data_interpretation_format_matrix.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/dev/report_data_interpretation_format_matrix.py --write-artifacts`
  - wrote both matrix artifacts.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐 Data Interpretation format capability boundary 已有可重跑 artifact，並證明
XDF / LSL 目前是 blocked user-facing boundary。它仍不支撐 XDF / LSL stream parser、
raw-event-anchor-specific MAT/GDF alignment、或全格式 real-data manual certification。

2026-05-04 Data Interpretation reviewed MAT sample-anchor apply slice：

- backend:
  - `load_label_file()` now accepts reviewed MAT `label_field` + `anchor`.
  - When a MAT anchor is provided, the loader returns an MNE-style event array:
    `[sample_index, 0, class_label]`.
  - `apply_interpretation` now treats reviewed MAT plans with `time_model=sample_index`,
    `granularity=trial`, selected label/anchor, and confirmed class map as `anchored` label apply.
  - The apply path uses `apply_labels_batch`, records `label_import:anchored:<n>`, and keeps the
    applied interpretation / recipe trace updated.
- tests:
  - TDD failures:
    - focused label loader test first returned the plain class labels instead of MNE event rows.
    - focused ApplicationService test first returned `label_apply.status=skipped`.
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader_coverage.py::TestLoadMat::test_mat_uses_selected_label_and_sample_anchor_as_events tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sample_anchor_label_carrier -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sample_anchor_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label -q`
  - `35 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `43 passed`
  - targeted `ruff check` / `ruff format --check` clean.
  - `poetry run basedpyright XBrainLab/backend/load_data/label_loader.py XBrainLab/backend/application/service.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐 reviewed MAT + sample-index anchor 的窄版 GDF/MAT external-label apply path。
它仍不支撐任意 raw trigger selection、non-sample timestamp conversion、複雜 anchor
reconciliation、XDF stream parser 或 full real-data manual certification。

2026-05-04 Data Interpretation timestamp label apply slice：

- backend:
  - `load_label_file()` now accepts reviewed `label_field` and `anchor` selections.
  - MAT loading can use a selected MAT variable instead of heuristic selection.
  - CSV / TSV / BIDS events loading can use selected label and anchor columns to produce
    timestamp-style labels.
  - `apply_interpretation` now auto-applies labels only for the narrow safe path:
    one loaded EEG file, one reviewed timestamp CSV / TSV / BIDS events carrier, confirmed
    interpretation, and time model `seconds` / `relative_time`.
  - Successful apply records `label_apply` diagnostics, updates applied interpretation
    `label_imports`, and appends `label_import:timestamp:<n>` to recipe trace.
- replay artifact refreshed:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON shows `label_apply.status=applied`, one timestamp label import record, and
    `label_import:timestamp:1` in recipe trace.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `60 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `51 passed`
  - targeted `ruff` clean.
  - targeted `basedpyright` clean; `.basedpyright/baseline.json` refreshed with one fewer baseline error.

這批 evidence 支撐 reviewed timestamp label carrier 已從 recipe-only 進入 Data Interpretation
apply path。下一個 slice 已補 reviewed MAT / TXT trial-order sequence auto-apply；仍不支撐
raw-event-anchor-specific GDF/MAT alignment、多檔 label mapping、XDF stream parser 或完整
post-load label import 內嵌 wizard。

2026-05-04 Data Interpretation MAT/TXT sequence label apply slice：

- backend:
  - `apply_interpretation` now also auto-applies the narrow sequence path:
    one loaded EEG file, one reviewed MAT / TXT trial-order carrier, confirmed class map, and
    trial granularity.
  - This path uses `load_label_file(label_field=...)`, then existing `apply_labels_legacy()`, and
    records `label_import:legacy:<n>` in the recipe trace.
- targeted gate:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier -q`
  - `2 passed`

這批 evidence 支撐 reviewed MAT trial-order labels 不再只是 recipe plan。它仍不支撐需要選 raw
event anchor 的 GDF/MAT alignment、多檔 label mapping 或 full manual compatibility matrix。

2026-05-04 Data Interpretation shared state snapshot propagation：

- backend:
  - `InterpretationStateSnapshot` now exposes `label_carrier_plan`,
    `format_capabilities`, `event_roles`, and `class_map`.
  - `ApplicationService._interpretation_snapshot()` sources those fields from applied
    interpretation first, then candidate / preview / scan state.
- automation / agent:
  - `query_state` returns the same interpretation review truth in diagnostics.
  - `execute_automation_payload()` includes the fields in its serialized state envelope,
    which is the MCP / headless path.
  - `execute_application_tool_command(..., "query_state", ...)` surfaces the same fields
    through the agent ApplicationService-backed tool surface.
- TDD evidence:
  - initial focused regression failed because `InterpretationStateSnapshot` had no
    `label_carrier_plan` attribute.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth tests/unit/backend/application/test_automation.py::test_execute_automation_payload_state_contains_interpretation_review_truth tests/unit/llm/tools/test_application_surface.py::test_query_state_tool_surfaces_interpretation_review_truth -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `61 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.

這批 evidence 支撐 UI / recipe 已確認的 import truth 不再停留在 backend JSON 或 wizard
內部；agent、headless automation 和 MCP-shaped envelope 可讀到同一份狀態。它仍不支撐 mature
embedded label import wizard、多檔 label mapping、raw-event-anchor-specific GDF/MAT alignment、
真人 Windows click-through、interactive desktop 3D 或 MCP HTTP / long-running client workflow。

2026-05-04 Data Interpretation multi-file timestamp label mapping：

- backend:
  - Reviewed timestamp carriers can now auto-apply to multiple loaded EEG files when each raw
    file has exactly one matching CSV / TSV / BIDS events carrier by normalized stem.
  - Existing single-file behavior remains unchanged: one target and one reviewed carrier can
    apply directly even when stems do not match.
  - Ambiguous multi-file cases such as one generic `events.tsv` for two loaded files are skipped
    with a reason instead of applying the same labels to multiple files.
- TDD evidence:
  - initial positive regression failed with `label_apply.status=skipped`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier -q`
  - `4 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `63 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.

這批 evidence 支撐 BIDS-style per-run timestamp labels 的 safe multi-file backend path。它仍不支撐
generic folder-level `events.tsv` disambiguation、multi-file MAT / TXT sequence mapping、
raw-event-anchor-specific GDF / MAT alignment、embedded label wizard UI 或真人 click-through。

2026-05-04 Data Interpretation multi-file sequence label mapping：

- backend:
  - Reviewed MAT / TXT trial-order sequence carriers can now auto-apply to multiple loaded EEG
    files when every raw file has exactly one matching carrier by normalized stem.
  - Sequence mapping calls existing `apply_labels_legacy()` once per matched target file, so
    per-file label sequences are not concatenated or shared across files.
  - Ambiguous multi-file cases such as one generic `labels.mat` for two loaded files are skipped
    with a reason instead of distributing labels by guesswork.
- TDD evidence:
  - initial positive regression failed with `label_apply.status=skipped`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `65 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.

這批 evidence 支撐 per-file MAT/TXT trial-order label sequences 的 safe multi-file backend path。
它仍不支撐 generic label disambiguation、raw-event-anchor-specific GDF / MAT alignment、embedded
label wizard UI 或真人 click-through。

2026-05-04 Data Interpretation label carrier matched-EEG UI slice：

- UI:
  - `DataInterpretationPreviewDialog` label carrier table now includes a `Matched EEG` column.
  - Single-file direct match and multi-file unique stem match show the target EEG file name.
  - Ambiguous multi-file carrier rows show `Needs review`.
  - Label carrier choices still return `label_field`, `anchor`, `time_model`, and `granularity`
    from the shifted editable columns.
- UI-observable replay:
  - command: `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - artifacts:
    - `artifacts/ui/data-interpretation-preview.png`
    - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON `label_carrier_rows` shows:
    `product_replay_events.tsv -> product_replay_raw.fif`.
  - replay JSON still shows reviewed `trial_type` / `onset` / `seconds` / `trial` choices and
    `label_apply.status=applied`.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `52 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.

這批 evidence 支撐 import wizard 對 label carrier mapping 的使用者可見性。它仍不是完整 embedded
post-load label import wizard，也不支撐 raw-event-anchor-specific MAT/GDF alignment 或真人
click-through。

2026-05-04 Data Interpretation manual generic label target mapping:

- backend:
  - Label carrier choices now accept `target_file` and preserve it as
    `selected_target_file` in `label_carrier_plan`.
  - Reviewed generic timestamp carriers such as folder-level `events.tsv` can be applied to a
    user-selected loaded EEG file instead of being skipped as ambiguous.
  - Reviewed generic MAT / TXT trial-order carriers such as `labels.mat` can likewise be
    applied to a user-selected loaded EEG file through the legacy sequence label path.
  - If no target is selected, the previous ambiguous skip behavior remains.
- UI:
  - The editable `Matched EEG` column now contributes `target_file` to
    `label_carrier_choices` when the user changes it from `Needs review`.
  - The replay artifact was refreshed to show generic `events.tsv` mapped to
    `sub-01_task-mi_run-2_raw.fif`.
- UI-observable replay:
  - command: `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - artifact:
    - `artifacts/ui/data-interpretation-preview.png`
    - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON `label_carrier_rows` shows:
    `events.tsv -> sub-01_task-mi_run-2_raw.fif`.
  - replay JSON `review_choices.label_carrier_choices` includes `target_file`.
  - replay JSON `label_apply` shows `status=applied`, `success_count=1`, and target file
    `sub-01_task-mi_run-2_raw.fif`.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `7 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
  - `4 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `67 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `54 passed`
  - targeted `ruff`, `ruff format --check`, and production `basedpyright` clean.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `git diff --check` -> pass.

這批 evidence 支撐 generic label carrier disambiguation 的第一個 embedded wizard path。它仍不支撐
raw-event-anchor-specific GDF / MAT alignment、all-format manual compatibility matrix、post-load
label import full editor、或真人 click-through。

2026-05-04 Data Interpretation label target selector UX:

- UI:
  - Ambiguous label carrier rows now render a `QComboBox` in the `Matched EEG` column.
  - The selector options are `Needs review` plus scanned EEG file names.
  - `get_result()` reads the selector value, so the same `target_file` choice flows into
    preview / apply.
- UI-observable replay:
  - `tree_rows()` now reads cell-widget text, so replay JSON records the visible selector value.
  - refreshed replay still shows `events.tsv -> sub-01_task-mi_run-2_raw.fif`.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_manual_label_target_mapping -q`
  - `1 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `7 passed`
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - exit `0`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `54 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label -q`
  - `2 passed`
  - targeted `ruff`, `ruff format --check`, and production `basedpyright` clean.

這批 evidence 支撐 generic carrier target mapping 的使用者操作不再依賴手打欄位。它仍不是完整
post-load label import full editor、all-format manual compatibility matrix 或真人 click-through。

2026-05-04 post-load label import target context slice：

- UI:
  - `ImportLabelDialog` title is now `Add Labels to Loaded Data`.
  - The dialog accepts selected target files and shows which loaded EEG file(s) will receive
    labels.
  - The dialog tells the user that a successful import updates the current import recipe trace
    when a data interpretation is active.
  - `DatasetActionHandler.import_label()` passes selected target files into the dialog.
- TDD evidence:
  - initial focused tests failed because `ImportLabelDialog` had no `target_files` argument and
    `DatasetActionHandler` did not pass target context.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py::test_import_label_dialog_shows_target_context tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_passes_target_context_to_dialog -q`
  - `2 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_ui_misc.py::TestImportLabelDialog -q`
  - `83 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - production `basedpyright` for touched UI files clean.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.

這批 evidence 支撐 compatibility label import flow 的 target visibility and recipe-impact wording。
它仍不是完整 embedded label wizard，也沒有取代 Data Interpretation source-level import flow。

2026-05-04 Data Interpretation recipe save UI path：

- Preview dialog 新增 `Save recipe after applying` checkbox，blocked decision 會 disabled。
- Dataset panel apply 成功後，若使用者勾選保存 recipe，UI 會呼叫
  `SaveInterpretationRecipeCommand`；若使用者選擇路徑，recipe 寫入該 JSON 檔，否則保留在
  backend session。
- commands:
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q`
  - `46 passed`
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 UI import flow 的 recipe save option。後續 label import trace integration
已補；舊 label import 仍是 `Add Labels to Loaded Data` compatibility UI，尚未成為完整 import
wizard label/recipe editor。

2026-05-04 label import recipe trace integration：

- `ImportRecipe` / `AppliedInterpretation` 新增 `label_imports`，並在成功
  `ImportLabelsCommand` 後保存：
  - label carriers。
  - target files / file mapping。
  - selected event names。
  - class map。
  - success count。
- `ApplicationStateSnapshot.interpretation` 現在暴露 `label_carriers`、`label_import_count` 和
  `label_imports`，供 UI / agent / MCP / scorer 讀同一份 recipe trace。
- Dataset panel 的 `Add Labels to Loaded Data` 成功後，若 backend 回報 recipe trace 更新，UI 會
  用使用者語言提示並可保存更新後 recipe。
- commands:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_import_labels_updates_applied_interpretation_recipe_trace tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `74 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `36 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
  - `66 passed`
  - targeted `ruff` / `basedpyright` clean。

這批 evidence 支撐 label import 不再只停在 raw controller label mutation，而會進入 Data
Interpretation recipe trace。它仍不支撐成熟 import wizard label editor、UI screenshot replay
或真人 click-through。

## Automated Evidence vs Product Evidence

| Evidence | 目前能證明 | 不能證明 |
| --- | --- | --- |
| startup smoke | `MainWindow` 能初始化 | assistant dock 打開後可用、可回覆、可讀 |
| local prompt smoke | local backend 能對最小 prompt 回文字 | UI chat flow 已接上、streaming 不被吃掉、錯誤可見 |
| structured-output smoke | 模型可按 prompt 產出 tool JSON | agent 在真 UI 中能穩定選 tool、解釋 blocked reason |
| deterministic eval | case schema / scoring / scripted policy 正確 | local LLM 真實 tool-call 成功率 |
| local tool-call eval | 真 primary / fallback local model raw output 能被 parser / verifier / scorer 審計 | 真 UI ChatPanel multi-turn / tool-command workflow |
| UI baseline | approved screenshots 沒有大幅 pixel drift | UI 是否產品級、是否能互動、是否 no-response |
| product walkthrough smoke | assistant layout / panel navigation / synthetic EEG button path 可重跑 | 真 launcher 人工體驗、完整訓練品質、所有 dialog / query action |
| split artifact audit | train/validation/test indices 和 subject/session leakage 可審計 | classification quality 或 thesis conclusion |
| UI unit tests | signal / slot 和 widget state 有 regression protection | 真人 click-through 完整體驗 |

未來不能再只用 deterministic eval 或 dashboard PASS 宣稱 assistant product gate 完成。
assistant product gate 至少要包含 user-visible normal chat flow、blocked command feedback、
local unavailable feedback 和 launcher click-through evidence。

## Clean Dashboard 判定

fast quality dashboard 的 clean 判定不是只看 script 有沒有跑完。

目前專案採用的 clean 定義是：

1. `artifacts/quality/latest.json` 的 `overall_status` 必須是 `pass`。
2. `checks[*].status` 必須全部是 `pass`。
3. `artifacts/quality/latest.md` 的 summary table 不應有 `FAIL` 或 `WARN`。
4. `workspace` 必須是目前 active repo：
   - `/mnt/d/workspace_v2/projects/lab/XBrainLab`
5. `generated_at` 必須是本次驗證時間，不是舊 artifact。

腳本內部的 overall 規則是：

- 任何 check 是 `fail` -> overall 是 `fail`
- 沒有 `fail`，但有 `warn` -> overall 是 `warn`
- 全部都是 `pass` -> overall 才是 `pass`

因此「clean」比「command exit 0」更嚴格：我們要的是 overall `PASS`，不是只有 script 沒崩潰。

## 驗證層級

| 層級 | 用途 |
| --- | --- |
| unit tests | 保護局部行為和 regression。 |
| integration tests | 驗證 UI/backend/data pipeline 的跨模組行為。 |
| real-data tests | 驗證實際 EEG format / fixture path。 |
| UI baselines | 驗證核心 UI 畫面沒有明顯漂移。 |
| quality dashboard | 快速整合健康檢查。 |
| thesis validation | 將工程 evidence 映射到研究 claim。 |

## Mock-heavy Test 判讀

目前測試確實偏 mock-heavy。

快速掃描結果：

- test files：`254`
- 含 `MagicMock` / `Mock` / `patch` / `monkeypatch` / `mocker` 的 test files：`144`
- unit test files：`214`
- mock-heavy unit test files：`124`
- integration test files：`33`
- 含 mock 的 integration test files：`17`

這代表目前測試比較擅長抓：

- API contract 變了。
- UI signal / slot wiring 斷了。
- controller method 沒被呼叫。
- 錯誤處理、狀態切換、參數 normalization 出現 regression。
- dashboard 這類 fast gate 裡已納入的啟動、UI baseline、IO slice 壞掉。

目前比較不擅長抓：

- 真實使用者 workflow 的長鏈路錯誤。
- 真實 Qt event timing / thread race。
- 真實 LLM local runtime、GPU、model cache、tool-call output。
- controller -> manager -> data pipeline 的完整 side effect。
- 長時間訓練、真實資料集 reproducibility。
- thesis-grade tool-call validation。

所以 test health 的判讀是：

- daily regression floor：尚可。
- end-to-end confidence：中等偏弱。
- agent runtime confidence：低。
- thesis validation confidence：低。

要提升可信度，不是刪掉 mocks，而是補少量高價值 non-mocked path：

- real `Study` + real controllers 的 backend workflow tests。
- UI button-driven acceptance tests。
- local-only assistant runtime smoke。
- public fixture pipeline smoke。
- thesis validation matrix。

## Pipeline Validation 分層

完整 pipeline 要測，但不要只靠一個超大的測試。

目前採用四層判斷：

| 層級 | 要回答的問題 | 代表 evidence |
| --- | --- | --- |
| fast dashboard | repo 今天是否健康？ | lint、type、startup、UI、real-data IO |
| tiny E2E pipeline smoke | `dataset -> train -> evaluate` 是否能閉環？ | 小資料、CPU、1-2 epoch、metrics 不壞 |
| public fixture pipeline smoke | 真實 EEG 來源是否能走到 training smoke？ | public event-rich fixtures |
| scientific validation | 結果是否可重現且支撐 thesis claim？ | 固定 protocol、baseline、統計與 threat analysis |

### Tiny E2E Pipeline Clean 定義

tiny E2E pipeline clean 不是追求高 accuracy，而是確認流程正確：

1. dataset 能提供 training / validation / test split。
2. model args 和資料 shape 對得上。
3. CPU one-epoch 或 two-epoch training 能跑完。
4. loss / accuracy 等 metrics 存在且範圍合理。
5. evaluation record 存在。
6. 檔案輸出要被 patch 或寫到受控目錄，不能污染 workspace。

### 目前已跑過的 Pipeline Evidence

`2026-05-01` targeted pipeline smoke：

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

首次結果：

- `2 passed in 7.54s`

data pipeline 文件驗證重跑結果：

- `2 passed in 5.89s`

這代表 tiny train/evaluate 和 Study facade train cycle 有基本閉環證據。

但它仍不代表：

- 所有 real EEG source 都能完整 training。
- training result 可重現。
- thesis claim 已成立。
- local LLM / agent runtime 的完整互動式產品流程已驗證。

## Thesis Protocol

thesis-grade validation protocol 目前放在：

```text
docs/validation/thesis_protocol.md
docs/validation/split_artifact_schema.json
```

核心定位：

- 論文要仔細驗證的是 agent tool-call accuracy，不是 EEG 訓練準確率。
- EEG data / split / training / evaluation 驗證只支撐產品 workflow 和 domain task sanity。
- 不可把 train/evaluate accuracy、split audit 或 external dataset runner 當作 agent thesis
  主結果。

tool-call thesis evidence 核心要求：

- 固定 benchmark cases。
- 同一 cases 接 deterministic baseline 與 local LLM primary / fallback runner。
- 比對 intent、tool / no-tool decision、tool selection、parameters、state transition、
  clarification behavior、blocked-command handling、confirmation boundary、error recovery、
  runtime safety、trajectory 和 user-visible response。
- 產生 machine-readable report、human-readable summary 和 dashboard。

目前最新 evidence：

- deterministic cases：`121`
- deterministic baseline：`121 / 121`
- primary local model：`121 / 121` x `3`
- fallback local model：`121 / 121` x `3`
- dashboard：`artifacts/agent_evals/dashboard.md`

EEG pipeline support 要求：

- dataset source 分層：checked-in fixtures、public fixtures、external thesis datasets。
- split protocol 明確標記 `trial-wise`、`session-wise` 或 `subject-wise`。
- train / validation / test indices 必須保存，且 validation 必須從 test 之外的 remaining data 產生。
- 若報告 EEG model sanity，metrics 至少包含 accuracy、balanced accuracy、macro F1、AUC、confusion matrix。
- baseline、config、logs、model summary、environment info 必須和 split artifact 一起保存。

目前 code support：

```bash
poetry run pytest --capture=sys \
  tests/unit/backend/dataset/test_split_audit.py \
  tests/unit/scripts/test_validate_split_artifact.py -q

poetry run python scripts/dev/validate_split_artifact.py artifacts/thesis/splits.json
```

這只代表 EEG split protocol 與 artifact audit 能重跑；正式 thesis evidence 目前已有 local
LLM tool-call runner、repeat runs、score report、dashboard 和 failure taxonomy。external dataset
runner、baseline comparison 和 statistical reporting 是 pipeline support，不是 tool-call thesis 主指標。

## Agent Runtime Validation

assistant product runtime 目前是 local-only。

這代表目前 validation 重點是：

- local model cache 是否存在。
- local transformer runtime 是否能在目標 GPU 上載入。
- GPU / CPU fallback 是否可預期。
- local generation timeout / stop / model reload 是否穩定。
- local model tool-call output 是否能穩定被 parser / verifier 接住。
- legacy remote settings 是否會 migrate / fail closed，而不是 instantiate remote backend。

目前已驗證：

- local model catalog、preflight、cache policy、health check 已落地。
- primary / fallback model cache 已存在且通過 CUDA prompt / structured-output smoke。
- `LLMConfig`、`LLMEngine`、`AgentWorker` 對 `api` / `gemini` legacy selection 會轉回 local
  或 fail closed；`reinitialize_agent("Gemini")` 不會建立 remote backend。
- product package 已移除 remote backend modules；architecture compliance 會掃 product code 中的
  remote backend class / key env path。
- model settings dialog 已收斂為 local-only UI；default dependencies 不包含 remote SDK。
- local runtime smoke 尚未納入 fast dashboard 預設 profile。
- local tool-call eval dashboard 已納入 validation artifact，但不能替代 UI-observable automated
  walkthrough 或 human desktop acceptance。

Gemini/API 不再列為未來產品驗證目標，也不是 product execution mode。若未來需要歷史比較，
必須放在 optional legacy fixture，不可由 product code import。

## Agent Tool-Call Scoring

thesis evidence 需要一套可重跑的 agent tool-call 評分工具。

這套工具應：

- 使用固定 benchmark cases。
- 驗證 LLM proposed tool call，而不是只看自然語言回答。
- 比對 expected intent、tool name、parameters、required state 和 expected result。
- 記錄 backend execution 是否成功，以及 state 是否如預期改變。
- 對 validation failure / self-correction 做分項評分。
- 產生 machine-readable report 和 human-readable summary。

目前 score 維度：

- intent accuracy。
- tool or no-tool decision accuracy。
- tool selection accuracy。
- parameter accuracy。
- state-transition accuracy。
- clarification behavior。
- blocked-command handling。
- confirmation-boundary handling。
- trajectory quality。
- visible response quality。
- runtime safety。
- error-recovery accuracy。
- repeated local-model stability。

2026-05-05 recipe remap schema/eval refresh:

- Shared schema: `PreviewInterpretationCommand.choices` now uses
  `data_interpretation_choice_schema.py` in both agent tool definitions and
  `backend.application.automation.command_specs()` / MCP tool specs.
- Coverage added: deterministic suite now includes explicit recipe reload
  `choices.eeg_file_remap`, explicit `choices.label_carrier_remap`, and a missing remap target
  clarification/no-call boundary.
- Artifact: `artifacts/agent_evals/latest.json` / `.md` refreshed with repeat count `3`,
  `121 / 121` deterministic pass, recipe_reload family `3 / 3`, and no failures.
  `artifacts/agent_evals/dashboard.md` now shows deterministic, primary local, and fallback local
  all on the same `121` cases with `100%` pass and `100%` repeated-run stability.
- Focused tests:
  `env QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/backend/application/test_automation.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `277 passed`.
- Claim boundary: this refresh supports a thesis-candidate local tool-call benchmark claim for this
  saved `121` case suite. It still does not prove full UI usability, Windows launcher coverage,
  mature import wizard completion, MCP HTTP / long-running jobs, or product completion.

2026-05-05 local 121-case scorer / normalizer hardening:

- Hardened local output handling for recipe-remap alias tools, missing remap targets, stale preview
  source paths, string-shaped metadata overrides, unrequested label-review noise, generated task/run
  prefixes, missing test split ratios, bandpass frequency aliases, and policy-reason subset blocked
  replies.
- Focused final gate:
  `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent/test_tool_call_eval.py -q`
  -> `134 passed`.
- Broad LLM / agent gate:
  `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/integration/agent -q`
  -> `529 passed`.
- Quality gates:
  `git diff --check` -> pass;
  `timeout 300s poetry run ruff check .` -> pass;
  `timeout 300s poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
  `timeout 300s poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`;
  `timeout 300s poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.

2026-05-05 local 121-case release/thesis gate rerun:

- Rerun purpose:
  - Update the formal benchmark artifact after agent mapped-tool command-surface hardening.
  - This is a release / thesis evidence gate, not the default gate for small verifier, normalizer,
    prompt, case wording, or UI refresh changes.
- Deterministic artifact:
  - `artifacts/agent_evals/latest.json` / `.md` -> `121 / 121`.
- Primary local artifact:
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
  - `microsoft/Phi-4-mini-instruct`, repeat count `3`, `121 / 121`, stability `100%`.
  - The run first wrote to the eval root by mistake; the artifact was moved into
    `local_primary/` without rerunning the model, and its path metadata was corrected.
- Fallback local artifact:
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
  - `microsoft/Phi-3.5-mini-instruct`, repeat count `3`, `121 / 121`, stability `100%`.
- Dashboard:
  - `poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
    -> `artifacts/agent_evals/dashboard.md` shows deterministic / primary / fallback all on the
    same `121` cases with `100%` pass and `100%` repeated-run stability.
- Resource pressure:
  - resource artifact:
    `artifacts/agent_evals/local-eval-resource-pressure-2026-05-05.md` /
    `artifacts/agent_evals/local-eval-resource-pressure-2026-05-05.json`.
  - observed fallback pressure on RTX 5070 Ti 16GB:
    `15764 MiB` used, `232 MiB` free, GPU util `99%`, process elapsed `38:40`,
    approximate fallback wall time about `41 min`.
  - claim boundary: fallback full x3 is high-pressure release/thesis evidence, not a routine
    development gate. Future local eval must run resource preflight and prefer deterministic /
    changed cases / primary subsets unless updating a formal benchmark claim.

2026-05-05 local eval CLI resource guard:

- Implementation:
  - `scripts/agent/evals/run_local_tool_call_eval.py` now calls a resource preflight before loading
    `LLMEngine`.
  - The preflight records selected case count, gate type, model role, repeat count, cache usage,
    available disk, estimated model VRAM, and the first `nvidia-smi` GPU memory row.
  - A repeat-`3` full local gate with high VRAM pressure is blocked before model startup and writes
    `resource_preflight.json` / `.md` into the requested output directory.
- Focused gate:
  `poetry run pytest --capture=sys tests/unit/scripts/test_run_local_tool_call_eval.py -q`
  -> `37 passed`.
- Claim boundary:
  this prevents accidental full local x3 runs under obvious VRAM pressure. It does not prove local
  model accuracy, long-run stability, or release/thesis evidence by itself.

舊 `scripts/agent/benchmarks/*` 可以作為歷史參考，但不能直接視為新的 thesis evidence。新的 scoring system 需要對齊 local-only runtime、State Manager、Verification Layer 和未來 Application Service / Command API。

## 目前優先驗證

1. Product delivery 主線優先：backend -> UI -> agent -> local LLM -> desktop launcher。
2. UI / agent command surface 統一後，補對應 backend、UI、agent regression tests。
3. Local LLM runtime 需要 health check、prompt smoke、structured-output / tool-call smoke 和 fallback evidence。
4. Desktop launcher 需要 startup smoke 與 missing local LLM 不閃退證據。
5. Tool-call eval / thesis evidence 只在產品主線穩定後開始。
6. Split artifact protocol 已建立，但它是 EEG pipeline support，不是 thesis 主評分。
7. scoring system 可重跑後，再收集 tool-call thesis validation evidence matrix。
8. Local LLM validation 只驗證符合選型限制的非中國模型；Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等不作為候選。

## 注意事項

- dashboard PASS 不是論文結論。
- training smoke 不是完整 reproducibility。
- local-only public fixtures 要和 checked-in baseline 分開標示。
- 每個 thesis claim 最後都應該能對到 command、test、artifact、experiment、score report 或文獻。
- `dev,test,docs` 是目前已驗證的標準 group；local LLM smoke 已另行驗證，但尚未納入 fast dashboard 預設 profile。
- assistant 是 local-only product runtime；Gemini/API key flow 不是必驗路線，相關 product code path
  已移除或由 architecture guard 阻擋回歸。
