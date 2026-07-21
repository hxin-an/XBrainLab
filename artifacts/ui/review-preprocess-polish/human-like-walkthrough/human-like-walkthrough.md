# Human-Like Product Walkthrough

- status: `passed`
- run ID: `20260721T024748Z-4885b2f4`
- generated at: `2026-07-21T02:49:09.611431+00:00`
- Git revision: `2df053d291f5dc584b7ef197215c9f061b56dd85`
- working tree dirty: `True`
- screenshot hashes: `45`
- failure reason: none
- claim boundary: Automated UI-observable PyQt replay; not human Windows desktop acceptance. Assistant states use AgentManager and Qt signals with a deterministic controller, not direct ChatController injection. This is product-surface evidence, not local-model or tool-call correctness evidence. Windows launcher click-through, dual-monitor/DPI behavior, and long real local-model desktop sessions remain human verification.
- evidence contract: `13`
- assistant driver: `agent_manager_qt_signals`
- source fingerprint: `df1e091819c6afb231aa39baaaa9d88e211c1cd2c2245bd810f9314f2e195b0b`
- elapsed seconds: `81.362`
- source: `<walkthrough_source>`

## Pass / Fail

- passed: `True`
- phases: `42` / `42`
- screenshots: `44`
- human desktop acceptance: `not performed`
- resource smoke passed: `True`
- current RSS growth: `552464` KB / limit `1200000` KB
- max RSS high-water growth: `613304` KB

## Screenshots

- main_initial: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/01-main-initial.png`
- dataset_page: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/02-dataset-page.png`
- source_selection: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/02-dataset-page.png`
- wizard_preview: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/04-interpretation-preview.png`
- wizard_metadata: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/05-interpretation-metadata.png`
- wizard_confirm: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/05-interpretation-match-labels.png`
- wizard_review: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/05-interpretation-review-import.png`
- applied: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/06-interpretation-applied.png`
- recipe_reloaded: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/07-recipe-reloaded.png`
- recipe_reapplied: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/07-recipe-reapplied.png`
- preprocess_loaded: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/08a-preprocessing-loaded.png`
- preprocess: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/08-preprocessing.png`
- preprocess_locked: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/08b-preprocessing-locked.png`
- dataset_ready: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/09-dataset-ready.png`
- training_readiness: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/10-training-readiness.png`
- analysis_readiness: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11-analysis-readiness.png`
- visualization_readiness: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11b-visualization-readiness.png`
- assistant_idle_setup: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11z-assistant-setup-required.png`
- assistant_idle_setup_full_window: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11z1-assistant-setup-required-full-window.png`
- assistant_loading: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12a-assistant-loading.png`
- assistant_loading_full_window: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12a1-assistant-loading-full-window.png`
- assistant_failed: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12b-assistant-failed.png`
- assistant_failed_full_window: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12b1-assistant-failed-full-window.png`
- assistant_settings: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12b1-assistant-settings.png`
- assistant_recovery_loading: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12b2-assistant-recovery-loading.png`
- assistant_ready: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12c-assistant-ready.png`
- assistant_ready_full_window: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12c1-assistant-ready-full-window.png`
- assistant_empty: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12-assistant-empty.png`
- assistant_normal: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/13-assistant-normal.png`
- assistant_processing: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/13a-assistant-processing.png`
- assistant_idle: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/13b-assistant-idle.png`
- assistant_clarification: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/14-assistant-clarification.png`
- assistant_blocked: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/15-assistant-blocked.png`
- assistant_blocked_full_window: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/15a-assistant-blocked-full-window.png`
- assistant_success: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16-assistant-success.png`
- assistant_error: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16a-assistant-error.png`
- assistant_cancelled: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16b-assistant-cancelled.png`
- assistant_confirmation_card: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16b1-assistant-confirmation-card.png`
- assistant_confirmed: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16c-assistant-confirmed.png`
- assistant_handoff: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16d-assistant-existing-ui-handoff.png`
- assistant_narrow: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/17-assistant-narrow.png`
- assistant_narrow_full_window: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/17a-assistant-narrow-full-window.png`
- reset_boundary: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/18-reset-boundary.png`
- error_recovery: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/19-error-recovery.png`
- eval_dashboard: `artifacts/ui/review-preprocess-polish/human-like-walkthrough/20-eval-dashboard.png`

## UI Quality Review

- automated checks passed: `True`
- phase snapshot coverage: `True`
- forbidden visible text findings: `0`
- human review boundary: This is automated UI-observable evidence. It does not replace a human desktop review of Windows launcher, dual-monitor/DPI, or long local-model sessions.
- table geometry passed: `True`
- checked table/tree widgets: `28`
- table geometry findings: `0`
- clipped row findings: `0`
- chat geometry passed: `True`
- checked ChatPanel phases: `11`
- chat geometry findings: `0`
- assistant processing contract passed: `True`
- processing status: `Preparing your request`; visible `True`; fits `True`
- processing action: `Stop`; visible `True`; enabled `True`
- stopping state: `stopping`; cancelability `stopping`
- composer enabled while processing: `False`
- assistant runtime passed: `True`
- assistant full dock passed: `True`
- assistant notices passed: `True`
- assistant signal path passed: `True`
- assistant error sanitization passed: `True`
- assistant backend claims passed: `True`
- assistant interactions passed: `True`
- assistant settings recovery passed: `True`

## Observable Evidence

- visible text snapshots: `42` phases
- button states: `42` phases
- workflow/backend snapshots: `42` phases
- UI geometry snapshots: `9` phases
- ChatPanel geometry snapshots: `11` phases
- assistant processing snapshots: `1` phases
- assistant runtime snapshots: `6` phases
- assistant full-dock snapshots: `18` phases
- assistant signal-path snapshots: `18` phases

## Phases

- `app_startup` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/01-main-initial.png`
- `main_window_initial_state` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/02-dataset-page.png`
- `data_source_selection` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/02-dataset-page.png`
- `data_interpretation_select_source` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/02-dataset-page.png`
- `data_interpretation_scan_result` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/04-interpretation-preview.png`
- `data_interpretation_preview` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/05-interpretation-metadata.png`
- `data_interpretation_confirm_metadata_labels` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/05-interpretation-match-labels.png`
- `data_interpretation_review_and_import` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/05-interpretation-review-import.png`
- `data_interpretation_decisions` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/06-interpretation-applied.png`
- `data_interpretation_apply` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/06-interpretation-applied.png`
- `data_interpretation_save_recipe` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/06-interpretation-applied.png`
- `data_interpretation_reload_recipe` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/07-recipe-reloaded.png`
- `data_interpretation_reapply_recipe` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/07-recipe-reapplied.png`
- `preprocessing_loaded` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/08a-preprocessing-loaded.png`
- `preprocessing` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/08-preprocessing.png`
- `preprocessing_locked` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/08b-preprocessing-locked.png`
- `epoch_creation` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/09-dataset-ready.png`
- `dataset_generation` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/09-dataset-ready.png`
- `training_readiness` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/10-training-readiness.png`
- `evaluation_visualization_saliency_readiness` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11-analysis-readiness.png`
- `visualization_readiness` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11b-visualization-readiness.png`
- `assistant_runtime_idle` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/11z-assistant-setup-required.png`
- `assistant_runtime_loading` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12a-assistant-loading.png`
- `assistant_runtime_failed` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12b-assistant-failed.png`
- `assistant_runtime_recovery_loading` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12b2-assistant-recovery-loading.png`
- `assistant_runtime_ready` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12c-assistant-ready.png`
- `assistant_empty_state` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12-assistant-empty.png`
- `assistant_repeated_open_close` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/12-assistant-empty.png`
- `assistant_normal_message` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/13-assistant-normal.png`
- `assistant_processing_state` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/13a-assistant-processing.png`
- `assistant_idle_after_stop` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/13b-assistant-idle.png`
- `assistant_missing_input_clarification` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/14-assistant-clarification.png`
- `assistant_blocked_command` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/15-assistant-blocked.png`
- `assistant_successful_tool_result` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16-assistant-success.png`
- `assistant_sanitized_error` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16a-assistant-error.png`
- `assistant_confirmation_cancelled` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16b-assistant-cancelled.png`
- `assistant_confirmation_confirmed` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16c-assistant-confirmed.png`
- `assistant_existing_ui_handoff` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/16d-assistant-existing-ui-handoff.png`
- `assistant_narrow_panel` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/17-assistant-narrow.png`
- `reset_new_session_boundary` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/18-reset-boundary.png`
- `error_recovery` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/19-error-recovery.png`
- `eval_dashboard_report` -> `artifacts/ui/review-preprocess-polish/human-like-walkthrough/20-eval-dashboard.png`

## User-Facing Transcript

- user: Continue evaluation in the existing app view.
- assistant: Evaluation is open in the main window. Review results there.
- user: Preview the selected data again.
- assistant: I need a source scan before previewing. I scanned the selected source again.

## Command / Tool Transcript

- `scan_source`: `ok` - Scanned source and found 1 EEG file(s).
- `preview_interpretation`: `ok` - Interpretation preview ready.
- `validate_interpretation`: `ok` - Interpretation validation: blocked.
- `preview_interpretation`: `ok` - Interpretation preview ready.
- `validate_interpretation`: `ok` - Interpretation validation: needs_confirmation.
- `apply_interpretation`: `failed` - apply_interpretation requires confirmation.
- `apply_interpretation`: `ok` - Applied interpretation and loaded 1 file(s). Imported reviewed labels for 1 file(s).
- `save_interpretation_recipe`: `ok` - Interpretation recipe saved.
- `reload_interpretation_recipe`: `ok` - Interpretation recipe reloaded for review.
- `apply_interpretation`: `ok` - Applied interpretation and loaded 1 file(s). Imported reviewed labels for 1 file(s).
- `preprocess`: `ok` - Standard preprocessing applied. Normalization using z-score is queued for per-epoch application during epoch creation.
- `create_epoch`: `ok` - Created epochs from 0.0s to 0.51s.
- `generate_dataset`: `ok` - Generated 1 dataset(s).
- `configure_training`: `ok` - Training configured.
- `train`: `ok` - Training completed.
- `evaluate`: `ok` - Evaluation summary ready.
- `visualize`: `ok` - Visualization summary ready.
- `saliency`: `ok` - Saliency summary ready.
- `new_session`: `failed` - new_session requires confirmation.
- `query_state`: `ok` - Results available: 1 EEG file loaded. Next: Review results.
- `new_session`: `failed` - new_session requires confirmation.
- `new_session`: `ok` - New session started.
- `preview_interpretation`: `failed` - Scan a data source before previewing interpretation.
- `scan_source`: `ok` - Scanned source and found 2 EEG file(s).

## Resource Notes

- smoke checked: `True`
- smoke passed: `True`
- boundary: Coarse process smoke only: current RSS catches large retained-memory regressions, while max RSS is recorded as a high-water diagnostic and does not prove the absence of leaks.
- start: threads `1`, qt active `0`, current rss `726532` KB, max rss `726532` KB
- before_close: threads `2`, qt active `0`, current rss `1279952` KB, max rss `1339836` KB
- after_close: threads `2`, qt active `0`, current rss `1278996` KB, max rss `1339836` KB

## Remaining Human Verification

- Windows desktop launcher click-through
- dual-monitor and DPI behavior
- long real local-model desktop session
