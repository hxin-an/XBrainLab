# Human-Like Product Walkthrough

- status: `passed`
- run ID: `20260723T143000Z-a8890360`
- generated at: `2026-07-23T14:31:12.025892+00:00`
- Git revision: `ae37d2dc2f321228bf5c3692f21695ff080574ad`
- working tree dirty: `True`
- screenshot hashes: `45`
- failure reason: none
- claim boundary: Automated UI-observable PyQt replay; not human Windows desktop acceptance. Assistant states use AgentManager and Qt signals with a deterministic controller, not direct ChatController injection. This is product-surface evidence, not local-model or tool-call correctness evidence. Windows launcher click-through, dual-monitor/DPI behavior, and long real local-model desktop sessions remain human verification.
- evidence contract: `13`
- assistant driver: `agent_manager_qt_signals`
- source fingerprint: `4b5771bf1631a4281953cdd26869e7b60019d158b04664feab40141f6d897834`
- elapsed seconds: `71.199`
- source: `<walkthrough_source>`
- recipe: `/tmp/xbrainlab-assistant-human-final4/walkthrough-import.recipe.json`

## Pass / Fail

- passed: `True`
- phases: `42` / `42`
- screenshots: `44`
- human desktop acceptance: `not performed`
- resource smoke passed: `True`
- current RSS growth: `405540` KB / limit `1200000` KB
- max RSS high-water growth: `470500` KB

## Screenshots

- main_initial: `/tmp/xbrainlab-assistant-human-final4/01-main-initial.png`
- dataset_page: `/tmp/xbrainlab-assistant-human-final4/02-dataset-page.png`
- source_selection: `/tmp/xbrainlab-assistant-human-final4/02-dataset-page.png`
- wizard_preview: `/tmp/xbrainlab-assistant-human-final4/04-interpretation-preview.png`
- wizard_metadata: `/tmp/xbrainlab-assistant-human-final4/05-interpretation-metadata.png`
- wizard_confirm: `/tmp/xbrainlab-assistant-human-final4/05-interpretation-match-labels.png`
- wizard_review: `/tmp/xbrainlab-assistant-human-final4/05-interpretation-review-import.png`
- applied: `/tmp/xbrainlab-assistant-human-final4/06-interpretation-applied.png`
- recipe_reloaded: `/tmp/xbrainlab-assistant-human-final4/07-recipe-reloaded.png`
- recipe_reapplied: `/tmp/xbrainlab-assistant-human-final4/07-recipe-reapplied.png`
- preprocess_loaded: `/tmp/xbrainlab-assistant-human-final4/08a-preprocessing-loaded.png`
- preprocess: `/tmp/xbrainlab-assistant-human-final4/08-preprocessing.png`
- preprocess_locked: `/tmp/xbrainlab-assistant-human-final4/08b-preprocessing-locked.png`
- dataset_ready: `/tmp/xbrainlab-assistant-human-final4/09-dataset-ready.png`
- training_readiness: `/tmp/xbrainlab-assistant-human-final4/10-training-readiness.png`
- analysis_readiness: `/tmp/xbrainlab-assistant-human-final4/11-analysis-readiness.png`
- visualization_readiness: `/tmp/xbrainlab-assistant-human-final4/11b-visualization-readiness.png`
- assistant_idle_setup: `/tmp/xbrainlab-assistant-human-final4/11z-assistant-setup-required.png`
- assistant_idle_setup_full_window: `/tmp/xbrainlab-assistant-human-final4/11z1-assistant-setup-required-full-window.png`
- assistant_loading: `/tmp/xbrainlab-assistant-human-final4/12a-assistant-loading.png`
- assistant_loading_full_window: `/tmp/xbrainlab-assistant-human-final4/12a1-assistant-loading-full-window.png`
- assistant_failed: `/tmp/xbrainlab-assistant-human-final4/12b-assistant-failed.png`
- assistant_failed_full_window: `/tmp/xbrainlab-assistant-human-final4/12b1-assistant-failed-full-window.png`
- assistant_settings: `/tmp/xbrainlab-assistant-human-final4/12b1-assistant-settings.png`
- assistant_recovery_loading: `/tmp/xbrainlab-assistant-human-final4/12b2-assistant-recovery-loading.png`
- assistant_ready: `/tmp/xbrainlab-assistant-human-final4/12c-assistant-ready.png`
- assistant_ready_full_window: `/tmp/xbrainlab-assistant-human-final4/12c1-assistant-ready-full-window.png`
- assistant_empty: `/tmp/xbrainlab-assistant-human-final4/12-assistant-empty.png`
- assistant_normal: `/tmp/xbrainlab-assistant-human-final4/13-assistant-normal.png`
- assistant_processing: `/tmp/xbrainlab-assistant-human-final4/13a-assistant-processing.png`
- assistant_idle: `/tmp/xbrainlab-assistant-human-final4/13b-assistant-idle.png`
- assistant_clarification: `/tmp/xbrainlab-assistant-human-final4/14-assistant-clarification.png`
- assistant_blocked: `/tmp/xbrainlab-assistant-human-final4/15-assistant-blocked.png`
- assistant_blocked_full_window: `/tmp/xbrainlab-assistant-human-final4/15a-assistant-blocked-full-window.png`
- assistant_success: `/tmp/xbrainlab-assistant-human-final4/16-assistant-success.png`
- assistant_error: `/tmp/xbrainlab-assistant-human-final4/16a-assistant-error.png`
- assistant_cancelled: `/tmp/xbrainlab-assistant-human-final4/16b-assistant-cancelled.png`
- assistant_confirmation_card: `/tmp/xbrainlab-assistant-human-final4/16b1-assistant-confirmation-card.png`
- assistant_confirmed: `/tmp/xbrainlab-assistant-human-final4/16c-assistant-confirmed.png`
- assistant_handoff: `/tmp/xbrainlab-assistant-human-final4/16d-assistant-existing-ui-handoff.png`
- assistant_narrow: `/tmp/xbrainlab-assistant-human-final4/17-assistant-narrow.png`
- assistant_narrow_full_window: `/tmp/xbrainlab-assistant-human-final4/17a-assistant-narrow-full-window.png`
- reset_boundary: `/tmp/xbrainlab-assistant-human-final4/18-reset-boundary.png`
- error_recovery: `/tmp/xbrainlab-assistant-human-final4/19-error-recovery.png`
- eval_dashboard: `/tmp/xbrainlab-assistant-human-final4/20-eval-dashboard.png`

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

- `app_startup` -> `/tmp/xbrainlab-assistant-human-final4/01-main-initial.png`
- `main_window_initial_state` -> `/tmp/xbrainlab-assistant-human-final4/02-dataset-page.png`
- `data_source_selection` -> `/tmp/xbrainlab-assistant-human-final4/02-dataset-page.png`
- `data_interpretation_select_source` -> `/tmp/xbrainlab-assistant-human-final4/02-dataset-page.png`
- `data_interpretation_scan_result` -> `/tmp/xbrainlab-assistant-human-final4/04-interpretation-preview.png`
- `data_interpretation_preview` -> `/tmp/xbrainlab-assistant-human-final4/05-interpretation-metadata.png`
- `data_interpretation_confirm_metadata_labels` -> `/tmp/xbrainlab-assistant-human-final4/05-interpretation-match-labels.png`
- `data_interpretation_review_and_import` -> `/tmp/xbrainlab-assistant-human-final4/05-interpretation-review-import.png`
- `data_interpretation_decisions` -> `/tmp/xbrainlab-assistant-human-final4/06-interpretation-applied.png`
- `data_interpretation_apply` -> `/tmp/xbrainlab-assistant-human-final4/06-interpretation-applied.png`
- `data_interpretation_save_recipe` -> `/tmp/xbrainlab-assistant-human-final4/06-interpretation-applied.png`
- `data_interpretation_reload_recipe` -> `/tmp/xbrainlab-assistant-human-final4/07-recipe-reloaded.png`
- `data_interpretation_reapply_recipe` -> `/tmp/xbrainlab-assistant-human-final4/07-recipe-reapplied.png`
- `preprocessing_loaded` -> `/tmp/xbrainlab-assistant-human-final4/08a-preprocessing-loaded.png`
- `preprocessing` -> `/tmp/xbrainlab-assistant-human-final4/08-preprocessing.png`
- `preprocessing_locked` -> `/tmp/xbrainlab-assistant-human-final4/08b-preprocessing-locked.png`
- `epoch_creation` -> `/tmp/xbrainlab-assistant-human-final4/09-dataset-ready.png`
- `dataset_generation` -> `/tmp/xbrainlab-assistant-human-final4/09-dataset-ready.png`
- `training_readiness` -> `/tmp/xbrainlab-assistant-human-final4/10-training-readiness.png`
- `evaluation_visualization_saliency_readiness` -> `/tmp/xbrainlab-assistant-human-final4/11-analysis-readiness.png`
- `visualization_readiness` -> `/tmp/xbrainlab-assistant-human-final4/11b-visualization-readiness.png`
- `assistant_runtime_idle` -> `/tmp/xbrainlab-assistant-human-final4/11z-assistant-setup-required.png`
- `assistant_runtime_loading` -> `/tmp/xbrainlab-assistant-human-final4/12a-assistant-loading.png`
- `assistant_runtime_failed` -> `/tmp/xbrainlab-assistant-human-final4/12b-assistant-failed.png`
- `assistant_runtime_recovery_loading` -> `/tmp/xbrainlab-assistant-human-final4/12b2-assistant-recovery-loading.png`
- `assistant_runtime_ready` -> `/tmp/xbrainlab-assistant-human-final4/12c-assistant-ready.png`
- `assistant_empty_state` -> `/tmp/xbrainlab-assistant-human-final4/12-assistant-empty.png`
- `assistant_repeated_open_close` -> `/tmp/xbrainlab-assistant-human-final4/12-assistant-empty.png`
- `assistant_normal_message` -> `/tmp/xbrainlab-assistant-human-final4/13-assistant-normal.png`
- `assistant_processing_state` -> `/tmp/xbrainlab-assistant-human-final4/13a-assistant-processing.png`
- `assistant_idle_after_stop` -> `/tmp/xbrainlab-assistant-human-final4/13b-assistant-idle.png`
- `assistant_missing_input_clarification` -> `/tmp/xbrainlab-assistant-human-final4/14-assistant-clarification.png`
- `assistant_blocked_command` -> `/tmp/xbrainlab-assistant-human-final4/15-assistant-blocked.png`
- `assistant_successful_tool_result` -> `/tmp/xbrainlab-assistant-human-final4/16-assistant-success.png`
- `assistant_sanitized_error` -> `/tmp/xbrainlab-assistant-human-final4/16a-assistant-error.png`
- `assistant_confirmation_cancelled` -> `/tmp/xbrainlab-assistant-human-final4/16b-assistant-cancelled.png`
- `assistant_confirmation_confirmed` -> `/tmp/xbrainlab-assistant-human-final4/16c-assistant-confirmed.png`
- `assistant_existing_ui_handoff` -> `/tmp/xbrainlab-assistant-human-final4/16d-assistant-existing-ui-handoff.png`
- `assistant_narrow_panel` -> `/tmp/xbrainlab-assistant-human-final4/17-assistant-narrow.png`
- `reset_new_session_boundary` -> `/tmp/xbrainlab-assistant-human-final4/18-reset-boundary.png`
- `error_recovery` -> `/tmp/xbrainlab-assistant-human-final4/19-error-recovery.png`
- `eval_dashboard_report` -> `/tmp/xbrainlab-assistant-human-final4/20-eval-dashboard.png`

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
- start: threads `1`, qt active `0`, current rss `726216` KB, max rss `726216` KB
- before_close: threads `2`, qt active `0`, current rss `1128900` KB, max rss `1196716` KB
- after_close: threads `2`, qt active `0`, current rss `1131756` KB, max rss `1196716` KB

## Remaining Human Verification

- Windows desktop launcher click-through
- dual-monitor and DPI behavior
- long real local-model desktop session
