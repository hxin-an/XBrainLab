# Human-Like Product Walkthrough

- status: `passed`
- run ID: `20260730T010124Z-28a37f18`
- generated at: `2026-07-30T01:02:33.704864+00:00`
- Git revision: `c851f6f01c0aba83dde7e9187b31f015293f7ecc`
- working tree dirty: `True`
- screenshot hashes: `45`
- failure reason: none
- claim boundary: Automated UI-observable PyQt replay; not human Windows desktop acceptance. Assistant states use AgentManager and Qt signals with a deterministic controller, not direct ChatController injection. This is product-surface evidence, not local-model or tool-call correctness evidence. Windows launcher click-through, dual-monitor/DPI behavior, and long real local-model desktop sessions remain human verification.
- evidence contract: `15`
- assistant driver: `agent_manager_qt_signals`
- source fingerprint: `692cb0e7c5a8d501af4a920cf3b192a570335f765d050b6d2e17fcfe7a3d1329`
- elapsed seconds: `69.403`
- source: `<walkthrough_source>`
- recipe: `artifacts/ui/assistant-product-v1-human-like-final/walkthrough-import.recipe.json`

## Pass / Fail

- passed: `True`
- phases: `42` / `42`
- screenshots: `45`
- human desktop acceptance: `not performed`
- resource smoke passed: `True`
- current RSS growth: `531192` KB / limit `1200000` KB
- max RSS high-water growth: `555020` KB

## Screenshots

- main_initial: `artifacts/ui/assistant-product-v1-human-like-final/01-main-initial.png`
- dataset_page: `artifacts/ui/assistant-product-v1-human-like-final/02-dataset-page.png`
- source_selection: `artifacts/ui/assistant-product-v1-human-like-final/03-source-selection.png`
- wizard_preview: `artifacts/ui/assistant-product-v1-human-like-final/04-interpretation-preview.png`
- wizard_metadata: `artifacts/ui/assistant-product-v1-human-like-final/05-interpretation-metadata.png`
- wizard_confirm: `artifacts/ui/assistant-product-v1-human-like-final/05-interpretation-match-labels.png`
- wizard_review: `artifacts/ui/assistant-product-v1-human-like-final/05-interpretation-review-import.png`
- applied: `artifacts/ui/assistant-product-v1-human-like-final/06-interpretation-applied.png`
- recipe_reloaded: `artifacts/ui/assistant-product-v1-human-like-final/07-recipe-reloaded.png`
- recipe_reapplied: `artifacts/ui/assistant-product-v1-human-like-final/07-recipe-reapplied.png`
- preprocess_loaded: `artifacts/ui/assistant-product-v1-human-like-final/08a-preprocessing-loaded.png`
- preprocess: `artifacts/ui/assistant-product-v1-human-like-final/08-preprocessing.png`
- preprocess_locked: `artifacts/ui/assistant-product-v1-human-like-final/08b-preprocessing-locked.png`
- dataset_ready: `artifacts/ui/assistant-product-v1-human-like-final/09-dataset-ready.png`
- training_readiness: `artifacts/ui/assistant-product-v1-human-like-final/10-training-readiness.png`
- analysis_readiness: `artifacts/ui/assistant-product-v1-human-like-final/11-analysis-readiness.png`
- visualization_readiness: `artifacts/ui/assistant-product-v1-human-like-final/11b-visualization-readiness.png`
- assistant_idle_setup: `artifacts/ui/assistant-product-v1-human-like-final/11z-assistant-setup-required.png`
- assistant_idle_setup_full_window: `artifacts/ui/assistant-product-v1-human-like-final/11z1-assistant-setup-required-full-window.png`
- assistant_loading: `artifacts/ui/assistant-product-v1-human-like-final/12a-assistant-loading.png`
- assistant_loading_full_window: `artifacts/ui/assistant-product-v1-human-like-final/12a1-assistant-loading-full-window.png`
- assistant_failed: `artifacts/ui/assistant-product-v1-human-like-final/12b-assistant-failed.png`
- assistant_failed_full_window: `artifacts/ui/assistant-product-v1-human-like-final/12b1-assistant-failed-full-window.png`
- assistant_settings: `artifacts/ui/assistant-product-v1-human-like-final/12b1-assistant-settings.png`
- assistant_recovery_loading: `artifacts/ui/assistant-product-v1-human-like-final/12b2-assistant-recovery-loading.png`
- assistant_ready: `artifacts/ui/assistant-product-v1-human-like-final/12c-assistant-ready.png`
- assistant_ready_full_window: `artifacts/ui/assistant-product-v1-human-like-final/12c1-assistant-ready-full-window.png`
- assistant_empty: `artifacts/ui/assistant-product-v1-human-like-final/12-assistant-empty.png`
- assistant_normal: `artifacts/ui/assistant-product-v1-human-like-final/13-assistant-normal.png`
- assistant_processing: `artifacts/ui/assistant-product-v1-human-like-final/13a-assistant-processing.png`
- assistant_idle: `artifacts/ui/assistant-product-v1-human-like-final/13b-assistant-idle.png`
- assistant_clarification: `artifacts/ui/assistant-product-v1-human-like-final/14-assistant-clarification.png`
- assistant_blocked: `artifacts/ui/assistant-product-v1-human-like-final/15-assistant-blocked.png`
- assistant_blocked_full_window: `artifacts/ui/assistant-product-v1-human-like-final/15a-assistant-blocked-full-window.png`
- assistant_success: `artifacts/ui/assistant-product-v1-human-like-final/16-assistant-success.png`
- assistant_error: `artifacts/ui/assistant-product-v1-human-like-final/16a-assistant-error.png`
- assistant_cancelled: `artifacts/ui/assistant-product-v1-human-like-final/16b-assistant-cancelled.png`
- assistant_confirmation_card: `artifacts/ui/assistant-product-v1-human-like-final/16b1-assistant-confirmation-card.png`
- assistant_confirmed: `artifacts/ui/assistant-product-v1-human-like-final/16c-assistant-confirmed.png`
- assistant_handoff: `artifacts/ui/assistant-product-v1-human-like-final/16d-assistant-existing-ui-handoff.png`
- assistant_narrow: `artifacts/ui/assistant-product-v1-human-like-final/17-assistant-narrow.png`
- assistant_narrow_full_window: `artifacts/ui/assistant-product-v1-human-like-final/17a-assistant-narrow-full-window.png`
- reset_boundary: `artifacts/ui/assistant-product-v1-human-like-final/18-reset-boundary.png`
- error_recovery: `artifacts/ui/assistant-product-v1-human-like-final/19-error-recovery.png`
- eval_dashboard: `artifacts/ui/assistant-product-v1-human-like-final/20-eval-dashboard.png`

## UI Quality Review

- automated checks passed: `True`
- phase snapshot coverage: `True`
- forbidden visible text findings: `0`
- human review boundary: This is automated UI-observable evidence. It does not replace a human desktop review of Windows launcher, dual-monitor/DPI, or long local-model sessions.
- table geometry passed: `True`
- checked table/tree widgets: `32`
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
- UI geometry snapshots: `10` phases
- ChatPanel geometry snapshots: `11` phases
- assistant processing snapshots: `1` phases
- assistant runtime snapshots: `6` phases
- assistant full-dock snapshots: `18` phases
- assistant signal-path snapshots: `18` phases

## Phases

- `app_startup` -> `artifacts/ui/assistant-product-v1-human-like-final/01-main-initial.png`
- `main_window_initial_state` -> `artifacts/ui/assistant-product-v1-human-like-final/02-dataset-page.png`
- `data_source_selection` -> `artifacts/ui/assistant-product-v1-human-like-final/03-source-selection.png`
- `data_interpretation_select_source` -> `artifacts/ui/assistant-product-v1-human-like-final/03-source-selection.png`
- `data_interpretation_scan_result` -> `artifacts/ui/assistant-product-v1-human-like-final/04-interpretation-preview.png`
- `data_interpretation_preview` -> `artifacts/ui/assistant-product-v1-human-like-final/05-interpretation-metadata.png`
- `data_interpretation_confirm_metadata_labels` -> `artifacts/ui/assistant-product-v1-human-like-final/05-interpretation-match-labels.png`
- `data_interpretation_review_and_import` -> `artifacts/ui/assistant-product-v1-human-like-final/05-interpretation-review-import.png`
- `data_interpretation_decisions` -> `artifacts/ui/assistant-product-v1-human-like-final/06-interpretation-applied.png`
- `data_interpretation_apply` -> `artifacts/ui/assistant-product-v1-human-like-final/06-interpretation-applied.png`
- `data_interpretation_save_recipe` -> `artifacts/ui/assistant-product-v1-human-like-final/06-interpretation-applied.png`
- `data_interpretation_reload_recipe` -> `artifacts/ui/assistant-product-v1-human-like-final/07-recipe-reloaded.png`
- `data_interpretation_reapply_recipe` -> `artifacts/ui/assistant-product-v1-human-like-final/07-recipe-reapplied.png`
- `preprocessing_loaded` -> `artifacts/ui/assistant-product-v1-human-like-final/08a-preprocessing-loaded.png`
- `preprocessing` -> `artifacts/ui/assistant-product-v1-human-like-final/08-preprocessing.png`
- `preprocessing_locked` -> `artifacts/ui/assistant-product-v1-human-like-final/08b-preprocessing-locked.png`
- `epoch_creation` -> `artifacts/ui/assistant-product-v1-human-like-final/09-dataset-ready.png`
- `dataset_generation` -> `artifacts/ui/assistant-product-v1-human-like-final/09-dataset-ready.png`
- `training_readiness` -> `artifacts/ui/assistant-product-v1-human-like-final/10-training-readiness.png`
- `evaluation_visualization_saliency_readiness` -> `artifacts/ui/assistant-product-v1-human-like-final/11-analysis-readiness.png`
- `visualization_readiness` -> `artifacts/ui/assistant-product-v1-human-like-final/11b-visualization-readiness.png`
- `assistant_runtime_idle` -> `artifacts/ui/assistant-product-v1-human-like-final/11z-assistant-setup-required.png`
- `assistant_runtime_loading` -> `artifacts/ui/assistant-product-v1-human-like-final/12a-assistant-loading.png`
- `assistant_runtime_failed` -> `artifacts/ui/assistant-product-v1-human-like-final/12b-assistant-failed.png`
- `assistant_runtime_recovery_loading` -> `artifacts/ui/assistant-product-v1-human-like-final/12b2-assistant-recovery-loading.png`
- `assistant_runtime_ready` -> `artifacts/ui/assistant-product-v1-human-like-final/12c-assistant-ready.png`
- `assistant_empty_state` -> `artifacts/ui/assistant-product-v1-human-like-final/12-assistant-empty.png`
- `assistant_repeated_open_close` -> `artifacts/ui/assistant-product-v1-human-like-final/12-assistant-empty.png`
- `assistant_normal_message` -> `artifacts/ui/assistant-product-v1-human-like-final/13-assistant-normal.png`
- `assistant_processing_state` -> `artifacts/ui/assistant-product-v1-human-like-final/13a-assistant-processing.png`
- `assistant_idle_after_stop` -> `artifacts/ui/assistant-product-v1-human-like-final/13b-assistant-idle.png`
- `assistant_missing_input_clarification` -> `artifacts/ui/assistant-product-v1-human-like-final/14-assistant-clarification.png`
- `assistant_blocked_command` -> `artifacts/ui/assistant-product-v1-human-like-final/15-assistant-blocked.png`
- `assistant_successful_tool_result` -> `artifacts/ui/assistant-product-v1-human-like-final/16-assistant-success.png`
- `assistant_sanitized_error` -> `artifacts/ui/assistant-product-v1-human-like-final/16a-assistant-error.png`
- `assistant_confirmation_cancelled` -> `artifacts/ui/assistant-product-v1-human-like-final/16b-assistant-cancelled.png`
- `assistant_confirmation_confirmed` -> `artifacts/ui/assistant-product-v1-human-like-final/16c-assistant-confirmed.png`
- `assistant_existing_ui_handoff` -> `artifacts/ui/assistant-product-v1-human-like-final/16d-assistant-existing-ui-handoff.png`
- `assistant_narrow_panel` -> `artifacts/ui/assistant-product-v1-human-like-final/17-assistant-narrow.png`
- `reset_new_session_boundary` -> `artifacts/ui/assistant-product-v1-human-like-final/18-reset-boundary.png`
- `error_recovery` -> `artifacts/ui/assistant-product-v1-human-like-final/19-error-recovery.png`
- `eval_dashboard_report` -> `artifacts/ui/assistant-product-v1-human-like-final/20-eval-dashboard.png`

## User-Facing Transcript

- user: Continue evaluation in the existing app view.
- assistant: Evaluation is open in the main window. Review results there.
- user: Preview the selected data again.
- assistant: I scanned the selected source and prepared the import preview.

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
- `preview_interpretation`: `ok` - Interpretation preview ready.

## Resource Notes

- smoke checked: `True`
- smoke passed: `True`
- boundary: Coarse process smoke only: current RSS catches large retained-memory regressions, while max RSS is recorded as a high-water diagnostic and does not prove the absence of leaks.
- start: threads `1`, qt active `0`, current rss `727016` KB, max rss `727016` KB
- after_analysis: threads `1`, qt active `0`, current rss `1103528` KB, max rss `1123376` KB
- after_assistant: threads `3`, qt active `0`, current rss `1263180` KB, max rss `1276912` KB
- before_close: threads `3`, qt active `0`, current rss `1265136` KB, max rss `1282036` KB
- after_close: threads `3`, qt active `0`, current rss `1258208` KB, max rss `1282036` KB

## Remaining Human Verification

- Windows desktop launcher click-through
- dual-monitor and DPI behavior
- long real local-model desktop session
