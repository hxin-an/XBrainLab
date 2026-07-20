# Human-Like Product Walkthrough

- status: `passed`
- run ID: `20260720T195350Z-5c9a5186`
- generated at: `2026-07-20T19:55:11.070246+00:00`
- Git revision: `73d257f9be3f35aa565fa3d98e59637ce8f1c48f`
- working tree dirty: `True`
- screenshot hashes: `43`
- failure reason: none
- claim boundary: Automated UI-observable PyQt replay; not human Windows desktop acceptance. Assistant states use AgentManager and Qt signals with a deterministic controller, not direct ChatController injection. This is product-surface evidence, not local-model or tool-call correctness evidence. Windows launcher click-through, dual-monitor/DPI behavior, and long real local-model desktop sessions remain human verification.
- evidence contract: `13`
- assistant driver: `agent_manager_qt_signals`
- source fingerprint: `5bb71cf1013f7281c2c100052cb5afc0b476f219f0b8bd8dbf3937a10f6ba934`
- elapsed seconds: `79.863`
- source: `<walkthrough_source>`
- recipe: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/walkthrough-import.recipe.json`

## Pass / Fail

- passed: `True`
- phases: `40` / `40`
- screenshots: `42`
- human desktop acceptance: `not performed`
- resource smoke passed: `True`
- current RSS growth: `545176` KB / limit `1200000` KB
- max RSS high-water growth: `610168` KB

## Screenshots

- main_initial: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/01-main-initial.png`
- dataset_page: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/02-dataset-page.png`
- source_selection: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/02-dataset-page.png`
- wizard_preview: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/04-interpretation-preview.png`
- wizard_metadata: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/05-interpretation-metadata.png`
- wizard_confirm: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/05-interpretation-match-labels.png`
- wizard_review: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/05-interpretation-review-import.png`
- applied: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/06-interpretation-applied.png`
- recipe_reloaded: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/07-recipe-reloaded.png`
- recipe_reapplied: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/07-recipe-reapplied.png`
- preprocess: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/08-preprocessing.png`
- dataset_ready: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/09-dataset-ready.png`
- training_readiness: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/10-training-readiness.png`
- analysis_readiness: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11-analysis-readiness.png`
- visualization_readiness: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11b-visualization-readiness.png`
- assistant_idle_setup: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11z-assistant-setup-required.png`
- assistant_idle_setup_full_window: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11z1-assistant-setup-required-full-window.png`
- assistant_loading: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12a-assistant-loading.png`
- assistant_loading_full_window: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12a1-assistant-loading-full-window.png`
- assistant_failed: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12b-assistant-failed.png`
- assistant_failed_full_window: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12b1-assistant-failed-full-window.png`
- assistant_settings: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12b1-assistant-settings.png`
- assistant_recovery_loading: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12b2-assistant-recovery-loading.png`
- assistant_ready: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12c-assistant-ready.png`
- assistant_ready_full_window: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12c1-assistant-ready-full-window.png`
- assistant_empty: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12-assistant-empty.png`
- assistant_normal: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/13-assistant-normal.png`
- assistant_processing: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/13a-assistant-processing.png`
- assistant_idle: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/13b-assistant-idle.png`
- assistant_clarification: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/14-assistant-clarification.png`
- assistant_blocked: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/15-assistant-blocked.png`
- assistant_blocked_full_window: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/15a-assistant-blocked-full-window.png`
- assistant_success: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16-assistant-success.png`
- assistant_error: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16a-assistant-error.png`
- assistant_cancelled: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16b-assistant-cancelled.png`
- assistant_confirmation_card: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16b1-assistant-confirmation-card.png`
- assistant_confirmed: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16c-assistant-confirmed.png`
- assistant_handoff: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16d-assistant-existing-ui-handoff.png`
- assistant_narrow: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/17-assistant-narrow.png`
- assistant_narrow_full_window: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/17a-assistant-narrow-full-window.png`
- reset_boundary: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/18-reset-boundary.png`
- error_recovery: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/19-error-recovery.png`
- eval_dashboard: `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/20-eval-dashboard.png`

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

- visible text snapshots: `40` phases
- button states: `40` phases
- workflow/backend snapshots: `40` phases
- UI geometry snapshots: `9` phases
- ChatPanel geometry snapshots: `11` phases
- assistant processing snapshots: `1` phases
- assistant runtime snapshots: `6` phases
- assistant full-dock snapshots: `18` phases
- assistant signal-path snapshots: `18` phases

## Phases

- `app_startup` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/01-main-initial.png`
- `main_window_initial_state` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/02-dataset-page.png`
- `data_source_selection` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/02-dataset-page.png`
- `data_interpretation_select_source` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/02-dataset-page.png`
- `data_interpretation_scan_result` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/04-interpretation-preview.png`
- `data_interpretation_preview` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/05-interpretation-metadata.png`
- `data_interpretation_confirm_metadata_labels` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/05-interpretation-match-labels.png`
- `data_interpretation_review_and_import` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/05-interpretation-review-import.png`
- `data_interpretation_decisions` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/06-interpretation-applied.png`
- `data_interpretation_apply` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/06-interpretation-applied.png`
- `data_interpretation_save_recipe` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/06-interpretation-applied.png`
- `data_interpretation_reload_recipe` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/07-recipe-reloaded.png`
- `data_interpretation_reapply_recipe` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/07-recipe-reapplied.png`
- `preprocessing` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/08-preprocessing.png`
- `epoch_creation` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/09-dataset-ready.png`
- `dataset_generation` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/09-dataset-ready.png`
- `training_readiness` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/10-training-readiness.png`
- `evaluation_visualization_saliency_readiness` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11-analysis-readiness.png`
- `visualization_readiness` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11b-visualization-readiness.png`
- `assistant_runtime_idle` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/11z-assistant-setup-required.png`
- `assistant_runtime_loading` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12a-assistant-loading.png`
- `assistant_runtime_failed` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12b-assistant-failed.png`
- `assistant_runtime_recovery_loading` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12b2-assistant-recovery-loading.png`
- `assistant_runtime_ready` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12c-assistant-ready.png`
- `assistant_empty_state` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12-assistant-empty.png`
- `assistant_repeated_open_close` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/12-assistant-empty.png`
- `assistant_normal_message` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/13-assistant-normal.png`
- `assistant_processing_state` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/13a-assistant-processing.png`
- `assistant_idle_after_stop` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/13b-assistant-idle.png`
- `assistant_missing_input_clarification` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/14-assistant-clarification.png`
- `assistant_blocked_command` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/15-assistant-blocked.png`
- `assistant_successful_tool_result` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16-assistant-success.png`
- `assistant_sanitized_error` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16a-assistant-error.png`
- `assistant_confirmation_cancelled` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16b-assistant-cancelled.png`
- `assistant_confirmation_confirmed` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16c-assistant-confirmed.png`
- `assistant_existing_ui_handoff` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/16d-assistant-existing-ui-handoff.png`
- `assistant_narrow_panel` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/17-assistant-narrow.png`
- `reset_new_session_boundary` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/18-reset-boundary.png`
- `error_recovery` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/19-error-recovery.png`
- `eval_dashboard_report` -> `/mnt/d/workspace_v2/projects/lab/xbrainlab/artifacts/ui/human-like-walkthrough-runs/current/20-eval-dashboard.png`

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
- start: threads `1`, qt active `0`, current rss `725284` KB, max rss `725284` KB
- before_close: threads `2`, qt active `0`, current rss `1269852` KB, max rss `1335452` KB
- after_close: threads `2`, qt active `0`, current rss `1270460` KB, max rss `1335452` KB

## Remaining Human Verification

- Windows desktop launcher click-through
- dual-monitor and DPI behavior
- long real local-model desktop session
